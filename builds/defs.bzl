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
load(":platforms.bzl", "PLATFORMS")

# Per-OS+CPU selection of the pinned inner Bazel binary (data dep + runfiles
# path). We key on os *and* cpu because the official release binaries differ per
# platform: a cpu-only select would, e.g., match the linux arm64 binary on a
# macOS arm64 host. The config settings are defined in //builds:BUILD.bazel.
_INNER_BAZEL_DATA = select({
    "//builds:linux_amd64": ["@inner_bazel_linux_amd64//file"],
    "//builds:linux_arm64": ["@inner_bazel_linux_arm64//file"],
    "//builds:darwin_amd64": ["@inner_bazel_darwin_amd64//file"],
    "//builds:darwin_arm64": ["@inner_bazel_darwin_arm64//file"],
})
_INNER_BAZEL_ARG = select({
    "//builds:linux_amd64": ["--bazel=$(rlocationpath @inner_bazel_linux_amd64//file)"],
    "//builds:linux_arm64": ["--bazel=$(rlocationpath @inner_bazel_linux_arm64//file)"],
    "//builds:darwin_amd64": ["--bazel=$(rlocationpath @inner_bazel_darwin_amd64//file)"],
    "//builds:darwin_arm64": ["--bazel=$(rlocationpath @inner_bazel_darwin_arm64//file)"],
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

def build_spec(targets, flags = []):
    """The `build` command for a project: what to build, plus extra flags."""
    return struct(command = "build", targets = targets, flags = flags, exclude_on = {})

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

def _emit_goal(project_id, source_archive, strip_prefix, toolchains, env, plat, spec, visibility):
    goal_name = "{}_{}_{}".format(spec.command, env.name, plat.name)

    overlays = toolchains + env.overlays
    appends = []  # (label, dest)
    writes = []  # (label, dest)
    patch_labels = []
    overlay_flags = []
    header_envs = []
    for ov in overlays:
        appends += ov.appends
        writes += ov.writes
        patch_labels += ov.patches
        overlay_flags += ov.build_flags
        header_envs += ov.remote_header_envs

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
        "--source-archive=$(rlocationpath {})".format(source_archive),
    ]
    if strip_prefix:
        args.append("--strip-prefix=" + strip_prefix)
    for label, dest in appends:
        args.append("--append=$(rlocationpath {})={}".format(label, dest))
    for label, dest in writes:
        args.append("--write=$(rlocationpath {})={}".format(label, dest))
    for label in patch_labels:
        args.append("--patch=$(rlocationpath {})".format(label))
    for env_spec in header_envs:
        args.append("--remote-header-env=" + env_spec)

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
        patch_labels,
    )
    data = [source_archive] + overlay_files + _INNER_BAZEL_DATA

    # host_only environments (local) can only run when the host matches the
    # goal's platform; mark the others incompatible so they're skipped, not run.
    compatible = None
    if env.host_only:
        compatible = [plat.os_constraint, plat.cpu_constraint]

    py_binary(
        name = goal_name,
        srcs = ["//tools/buildrunner:runner.py"],
        main = "runner.py",
        deps = ["@rules_python//python/runfiles"],
        data = data,
        args = args + _INNER_BAZEL_ARG,
        target_compatible_with = compatible,
        visibility = visibility,
    )

def museum_project(
        name,
        source_archive,
        environments,
        build = None,
        test = None,
        strip_prefix = "",
        toolchains = [],
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
      visibility: visibility for the generated goal targets.
    """

    # Unique per-project id, derived from the package path so two projects'
    # goals (e.g. both `build_local_darwin_arm64`) don't collide on the build root.
    project_id = (native.package_name().replace("/", "_") or name)
    specs = [s for s in (build, test) if s]

    for env in environments:
        for plat_name in env.platforms:
            plat = PLATFORMS[plat_name]
            for spec in specs:
                _emit_goal(
                    project_id,
                    source_archive,
                    strip_prefix,
                    toolchains,
                    env,
                    plat,
                    spec,
                    visibility,
                )
