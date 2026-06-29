"""`museum_project`: declare isolated, daemonless inner Bazel builds across a
matrix of environments x platforms x commands.

A *project* pins a source tarball and a set of toolchain overlays, then names the
environments it targets (see //builds:environments.bzl) and its `build`/`test`
specs. museum_project crosses those, emitting one `bazel run`-nable goal per
runnable cell, named `<command>_<env>_<os>_<arch>`:

    load("//builds:defs.bzl", "build_spec", "museum_project", "test_spec")
    load("//builds:environments.bzl", "LOCAL", "RBE")
    load("//builds:overlays.bzl", "HERMETIC_LLVM")

    museum_project(
        name = "cxx",
        source_archive = "@cxx_archive//file",
        strip_prefix = "cxx-1.0.194",
        toolchains = [HERMETIC_LLVM],          # applied to every goal
        environments = [LOCAL, RBE],
        build = build_spec(targets = ["//:cxx", "//:core"]),
        test = test_spec(targets = ["//..."]),
    )

    # then, on this macOS host:
    #   bazel run //builds/cxx:build_local_darwin_arm64
    #   bazel run //builds/cxx:test_local_darwin_arm64
    #   bazel run //builds/cxx:build_rbe_linux_amd64
    #   bazel run //builds/cxx:test_rbe_linux_amd64
    #   bazel run //builds/cxx:build_local_darwin_arm64 -- //:cxx   (override targets)

Only *runnable* cells are emitted: `rbe` only lists the platforms it has
executors for, and `local` goals are gated on the host matching their platform
(so `*_local_linux_amd64` is inert on this Mac and live on the linux VM).
"""

load("@rules_python//python:defs.bzl", "py_binary")
load("//tools/fetch:extension.bzl", "DEFAULT_INNER_BAZEL_VERSION")
load(":clients.bzl", "clients_for")
load(":overlays.bzl", "HERMETIC_LLVM")
load(":platforms.bzl", "PLATFORMS")

# Per-OS+CPU selection of the pinned inner Bazel binary (data dep + runfiles
# path), for a given inner Bazel version. We key on os *and* cpu because the
# official release binaries differ per platform: a cpu-only select would, e.g.,
# match the linux arm64 binary on a macOS arm64 host. The config settings are
# defined in //builds:BUILD.bazel; the repos come from //tools/fetch.
def _inner_bazel_data(version):
    vtag = version.replace(".", "_")
    return select({
        "//builds:linux_amd64": ["@inner_bazel_{}_linux_amd64//file".format(vtag)],
        "//builds:linux_arm64": ["@inner_bazel_{}_linux_arm64//file".format(vtag)],
        "//builds:darwin_amd64": ["@inner_bazel_{}_darwin_amd64//file".format(vtag)],
        "//builds:darwin_arm64": ["@inner_bazel_{}_darwin_arm64//file".format(vtag)],
    })

def _inner_bazel_arg(version):
    vtag = version.replace(".", "_")
    return select({
        "//builds:linux_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_amd64//file)".format(vtag)],
        "//builds:linux_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_arm64//file)".format(vtag)],
        "//builds:darwin_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_amd64//file)".format(vtag)],
        "//builds:darwin_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_arm64//file)".format(vtag)],
    })

# The injected RBE platform package (one platform() per os/arch). pin_platform
# environments append this and point the platform flags at //museum_rbe:<plat>.
_RBE_PLATFORMS_FILE = "//tools/buildrunner/overlays:rbe_platforms.BUILD.bazel"
_RBE_PLATFORMS_DEST = "museum_rbe/BUILD.bazel"

# Flags applied to every goal regardless of command/env: make the output tree
# self-describing by naming directories after the actual target platform (rather
# than the legacy --cpu mnemonic, which otherwise leaks the host's identity).
_COMMON_FLAGS = ["--experimental_platform_in_output_dir"]

# Sensible defaults per command so `bazel test` shows failures and keeps going
# (so we see how many targets pass). Specs/overlays can override via later flags.
_COMMAND_DEFAULT_FLAGS = {
    "test": [
        "--test_output=errors",
        "--keep_going",
        # Pin a UTF-8 locale for test actions: hermetic and reproducible, and it
        # fixes JVM sun.jnu.encoding so tests touching Unicode file paths pass
        # regardless of the host's locale.
        "--test_env=LC_ALL=C.UTF-8",
        "--test_env=LANG=C.UTF-8",
    ],
}

def build_spec(targets, flags = [], exclude_on = {}, emit_artifacts = True):
    """The `build` command for a project: what to build, plus extra flags.

    Args:
      targets: default build target patterns.
      flags: extra flags for the inner `bazel build`.
      exclude_on: dict env-name -> target patterns to *additionally* exclude in
        that environment (e.g. a target that only builds with a host toolchain a
        given environment lacks).
      emit_artifacts: default True — after a successful build, copy each target's
        outputs into `<build_root>/artifacts/` and write an `artifacts.json`
        manifest (target -> files with sha256). Read from the build's event
        stream, so it never forces a rebuild. Set False to opt a project out.
    """
    return struct(
        command = "build",
        targets = targets,
        flags = flags,
        exclude_on = exclude_on,
        emit_artifacts = emit_artifacts,
    )

def test_spec(targets, flags = [], exclude_on = {}):
    """The `test` command for a project.

    Args:
      targets: default test target patterns (may include negative patterns).
      flags: extra flags for the inner `bazel test`.
      exclude_on: dict env-name -> list of target patterns to *additionally*
        exclude in that environment (e.g. tests that only fail under RBE because
        the executor runs as root or lacks the host timezone database).
    """
    return struct(command = "test", targets = targets, flags = flags, exclude_on = exclude_on)

def _dedupe(items):
    seen = {}
    out = []
    for it in items:
        if it not in seen:
            seen[it] = True
            out.append(it)
    return out

def _emit_goal(project_id, source_archive, strip_prefix, toolchains, env, plat, spec, client, visibility, bcr_module = None):
    goal_name = "{}_{}_{}_{}".format(spec.command, env.name, client.name, plat.name)
    bazel_version = client.bazel_version

    overlays = toolchains + env.overlays
    appends = []  # (label, dest)
    writes = []  # (label, dest)
    patch_labels = []
    overlay_flags = []
    header_envs = []
    tools = []  # (binary_label, name)
    for ov in overlays:
        appends += ov.appends
        writes += ov.writes
        patch_labels += ov.patches
        overlay_flags += ov.build_flags
        header_envs += ov.remote_header_envs
        tools += getattr(ov, "tools", [])

    # Pin the explicit execution+target platform for remote environments.
    platform_flags = []
    if env.pin_platform:
        appends = appends + [(_RBE_PLATFORMS_FILE, _RBE_PLATFORMS_DEST)]
        plat_label = "//museum_rbe:" + plat.name
        platform_flags = [
            "--platforms=" + plat_label,
            "--extra_execution_platforms=" + plat_label,
            # Pin the host platform too, so host/exec tool resolution (and the
            # legacy --host_cpu) follows the executor rather than the orchestrator
            # — otherwise a host tool built for the orchestrator (e.g. a darwin
            # buildifier) gets shipped to a linux executor and fails to run.
            "--host_platform=" + plat_label,
        ]

    args = [
        "--name={}__{}".format(project_id, goal_name),
        "--command=" + spec.command,
    ]
    if bcr_module:
        # No source tarball: synthesize a root module that bazel_dep()s the BCR
        # module and build/test its @name//... targets (the registry resolves
        # source + patches + MODULE.bazel; overlays still append as usual).
        args.append("--bcr-module=" + bcr_module)
    else:
        args.append("--source-archive=$(rlocationpath {})".format(source_archive))
        if strip_prefix:
            args.append("--strip-prefix=" + strip_prefix)

    # Container environments (MINIMG) run the inner bazel inside a minimal image
    # instead of on the host; the runner bind-mounts the build root + inner bazel.
    if getattr(env, "container_image", None):
        args.append("--container-image=" + env.container_image)

    # Opt-in: copy this build's outputs out + write an artifacts.json manifest.
    if getattr(spec, "emit_artifacts", False):
        args.append("--emit-artifacts")

    for label, dest in appends:
        args.append("--append=$(rlocationpath {})={}".format(label, dest))
    for label, dest in writes:
        args.append("--write=$(rlocationpath {})={}".format(label, dest))
    for label in patch_labels:
        args.append("--patch=$(rlocationpath {})".format(label))
    for env_spec in header_envs:
        args.append("--remote-header-env=" + env_spec)
    for tool_label, tool_name in tools:
        args.append("--tool=$(rlocationpath {})={}".format(tool_label, tool_name))

    all_flags = (
        _COMMAND_DEFAULT_FLAGS.get(spec.command, []) +
        overlay_flags +
        platform_flags +
        env.platform_flags.get(plat.name, []) +
        _COMMON_FLAGS +
        spec.flags
    )
    for flag in all_flags:
        args.append("--build-flag=" + flag)

    targets = list(spec.targets)
    for excluded in spec.exclude_on.get(env.name, []):
        targets.append("-" + excluded if not excluded.startswith("-") else excluded)
    for target in targets:
        args.append("--target=" + target)

    overlay_files = _dedupe(
        [label for label, _ in appends] +
        [label for label, _ in writes] +
        patch_labels +
        [label for label, _ in tools],
    )
    data = ([source_archive] if source_archive else []) + overlay_files + _inner_bazel_data(bazel_version)

    # host_only environments (local) can only run when the host matches the
    # goal's platform; mark the others incompatible so they're skipped, not run.
    # host_cpu_only gates on CPU arch alone (any host OS): used by actiond, whose
    # local worker runs a Linux guest of the *host's* arch — so e.g. only the
    # linux_amd64 actiond goal is live on an x86_64 host (Linux or macOS).
    compatible = None
    if env.host_only:
        compatible = [plat.os_constraint, plat.cpu_constraint]
    elif env.host_cpu_only:
        compatible = [plat.cpu_constraint]

    py_binary(
        name = goal_name,
        srcs = ["//tools/buildrunner:runner.py"],
        main = "runner.py",
        deps = ["@rules_python//python/runfiles"],
        data = data,
        args = args + _inner_bazel_arg(bazel_version),
        target_compatible_with = compatible,
        visibility = visibility,
    )
    return goal_name

def museum_project(
        name,
        source_archive,
        environments,
        build = None,
        test = None,
        strip_prefix = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    """Declare a museum project and emit its environment x platform x command grid.

    Args:
      name: project name (informational; the package path also identifies it).
      source_archive: label of the pinned source tarball (e.g. "@cxx_archive//file").
      environments: environments to target (e.g. [LOCAL, RBE]).
      build: a build_spec(...) (or None to emit no build goals).
      test: a test_spec(...) (or None to emit no test goals).
      strip_prefix: top-level directory inside the tarball = workspace root.
      toolchains: overlays applied to every goal (e.g. [HERMETIC_LLVM]).
      bazel_version: legacy single-client shorthand — which pinned inner Bazel to
        run the build with. Defaults to the museum default; set it to match a
        project's .bazelversion when the project targets an older Bazel (must be
        a version in //tools/fetch). Ignored when `clients` is set.
      clients: the client axis (see //builds:clients.bzl): a list of client
        names (e.g. ["bazel8", "bazel9"]) this project supports. The first is the
        default. When omitted, a single client is derived from `bazel_version`.
      visibility: visibility for the generated goal targets.
    """

    # Unique per-project id, derived from the package path so two projects'
    # goals (e.g. both `build_local_darwin_arm64`) don't collide on the build root.
    project_id = (native.package_name().replace("/", "_") or name)
    specs = [s for s in (build, test) if s]
    client_structs = clients_for(bazel_version, clients)
    default_client = client_structs[0]

    for env in environments:
        for plat_name in env.platforms:
            plat = PLATFORMS[plat_name]
            for spec in specs:
                for client in client_structs:
                    goal_name = _emit_goal(
                        project_id,
                        source_archive,
                        strip_prefix,
                        toolchains,
                        env,
                        plat,
                        spec,
                        client,
                        visibility,
                    )

                    # Back-compat alias without the client segment, pointing at
                    # the project's default (first) client. Keeps the historical
                    # `<cmd>_<env>_<platform>` goal names working and gives the
                    # test dispatcher a stable name when `client` is omitted.
                    if client == default_client:
                        native.alias(
                            name = "{}_{}_{}".format(spec.command, env.name, plat.name),
                            actual = ":" + goal_name,
                            visibility = visibility,
                        )

def bcr_project(
        name,
        module,
        version,
        environments,
        build = None,
        test = None,
        toolchains = None,
        rbe_toolchains = None,
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    """Declare a museum project that builds/tests a Bazel Central Registry module
    *as published* — rather than pinning the upstream source and running its
    in-repo BUILD.

    The runner synthesizes a tiny root module that `bazel_dep`s `module` at
    `version`, so the registry resolves the module's source, patches, and
    MODULE.bazel; the goal then builds/tests the module's own `@<module>//...`
    targets (e.g. the `test_targets` the BCR's presubmit.yml runs). This captures
    projects whose Bazel build lives in the BCR (community-"ported" modules) and
    whose upstream repo ships no/partial in-repo Bazel. Emits the same
    `<cmd>_<env>_<client>_<platform>` goal grid.

    Toolchain by environment: by default this reaches for hermetic LLVM only
    where it's actually needed. Autodetect-capable environments (LOCAL, CIIMG —
    the host or a CI image that ships a compiler) build with the *ambient* host
    toolchain, no overlay. The pin-platform RBE environment, where a host-
    autodetected toolchain can't match the remote executor's compiler, gets
    HERMETIC_LLVM. (MINIMG — the toolchain-free minimal image — has no compiler to
    autodetect, so if you target it, pass it via `toolchains` with HERMETIC_LLVM.)

    Args:
      name: project name (informational; the package path also identifies it).
      module: the BCR module name (e.g. "simdutf").
      version: the BCR module version to pin (e.g. "7.7.0").
      environments: environments to target (e.g. [LOCAL, CIIMG, RBE]).
      build: a build_spec(...) over @<module>//... targets, or None.
      test: a test_spec(...) over @<module>//... targets, or None.
      toolchains: overlays for the autodetect-capable (non-pin_platform)
        environments. Defaults to [] (the ambient host/CI-image toolchain).
      rbe_toolchains: overlays for pin_platform environments (RBE). Defaults to
        [HERMETIC_LLVM] — the reproducible cross-machine toolchain.
      bazel_version: legacy single-client shorthand; ignored when `clients` set.
      clients: the client axis (see //builds:clients.bzl).
      visibility: visibility for the generated goal targets.
    """
    host_toolchains = toolchains if toolchains != None else []
    pin_toolchains = rbe_toolchains if rbe_toolchains != None else [HERMETIC_LLVM]
    project_id = (native.package_name().replace("/", "_") or name)
    specs = [s for s in (build, test) if s]
    client_structs = clients_for(bazel_version, clients)
    default_client = client_structs[0]
    bcr_module = "{}={}".format(module, version)

    for env in environments:
        env_toolchains = pin_toolchains if env.pin_platform else host_toolchains
        for plat_name in env.platforms:
            plat = PLATFORMS[plat_name]
            for spec in specs:
                for client in client_structs:
                    goal_name = _emit_goal(
                        project_id,
                        None,  # no source archive
                        "",
                        env_toolchains,
                        env,
                        plat,
                        spec,
                        client,
                        visibility,
                        bcr_module = bcr_module,
                    )
                    if client == default_client:
                        native.alias(
                            name = "{}_{}_{}".format(spec.command, env.name, plat.name),
                            actual = ":" + goal_name,
                            visibility = visibility,
                        )
