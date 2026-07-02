load("@rules_python//python:defs.bzl", "py_test")
load("//bazel_runner:extension.bzl", "DEFAULT_INNER_BAZEL_VERSION")

def build_spec(targets, flags = [], exclude_on = {}, emit_artifacts = True):
    return struct(
        command = "build",
        targets = targets,
        flags = flags,
        exclude_on = exclude_on,
        emit_artifacts = emit_artifacts,
    )

def test_spec(targets, flags = [], exclude_on = {}):
    return struct(
        command = "test",
        targets = targets,
        flags = flags,
        exclude_on = exclude_on,
    )

def _compat_env(name):
    return struct(name = name)

LOCAL = _compat_env("local")
RBE = _compat_env("rbe")

def overlay(name, appends = [], writes = [], patches = [], build_flags = [], remote_header_envs = [], tools = []):
    return struct(
        name = name,
        appends = appends,
        writes = writes,
        patches = patches,
        build_flags = build_flags,
        remote_header_envs = remote_header_envs,
        tools = tools,
    )

HERMETIC_LLVM = overlay(name = "hermetic_llvm")
_RBE_HERMETIC_LLVM = overlay(
    name = "rbe_hermetic_llvm",
    appends = [("//bazel_runner:hermetic_llvm.MODULE.bazel", "MODULE.bazel")],
)
_HERMETIC_LLVM_MODIFICATION = overlay(
    name = "hermetic_llvm",
    appends = [("//bazel_runner:hermetic_llvm.MODULE.bazel", "MODULE.bazel")],
    # cc_test defaults to linkstatic = 0, so test binaries dynamically link
    # libc++.so.1/libc++abi.so.1 from the hermetic toolchain. On RBE workers the
    # dynamic loader cannot resolve those runfiles-relative solibs and falls
    # back to the worker image's /usr/local/lib copies, which are incompatible
    # ("undefined symbol: __msan_va_arg_overflow_size_tls"). Forcing static
    # linking removes the runtime dependency on worker system libraries.
    build_flags = ["--dynamic_mode=off"],
)
# For projects with py_test targets: rules_python's default
# bootstrap_impl=system_python stage-1 stub execs `/usr/bin/env python3` even
# when a hermetic runtime is attached, and RBE images have no python3. The
# script bootstrap needs no system interpreter. The append gives the root
# module a rules_python dep so the flag's repo is addressable from the
# command line (MVS keeps the project's own newer pin if it has one).
HERMETIC_PYTHON = overlay(
    name = "hermetic_python",
    appends = [("//bazel_runner:hermetic_python.MODULE.bazel", "MODULE.bazel")],
    build_flags = ["--@rules_python//python/config_settings:bootstrap_impl=script"],
)

# For projects whose root module already declares a rules_python bazel_dep
# (appending another one is an error): just the bootstrap flag.
HERMETIC_PYTHON_FLAGS = overlay(
    name = "hermetic_python_flags",
    build_flags = ["--@rules_python//python/config_settings:bootstrap_impl=script"],
)
CC_NODETECT = overlay(name = "cc_nodetect")
HERMETIC_ZIP = overlay(
    name = "hermetic_zip",
    writes = [("//bazel_runner:zip.py", ".bazel-runner-tools/zip")],
    build_flags = ["--strategy=Genrule=local"],
)
RULES_RUST_SYSROOT_FIX = overlay(name = "rules_rust_sysroot_fix")
RULES_CC_DEP = overlay(name = "rules_cc_dep")
PLATFORMS_DEP = overlay(name = "platforms_dep")
BUILDBUDDY_BES = overlay(
    name = "buildbuddy_bes",
    build_flags = [
        "--bes_results_url=https://app.buildbuddy.io/invocation/",
        "--bes_backend=grpcs://remote.buildbuddy.io",
        "--build_metadata=USER=bazel-matrix",
        "--build_metadata=VISIBILITY=PUBLIC",
    ],
)
BUILDBUDDY_RBE = overlay(
    name = "buildbuddy_rbe",
    build_flags = [
        "--remote_cache=grpcs://remote.buildbuddy.io",
        "--remote_header=x-buildbuddy-api-key=$BUILDBUDDY_API_KEY",
        "--remote_timeout=10m",
        "--jobs=32",
        "--remote_executor=grpcs://remote.buildbuddy.io",
        # BuildBuddy's default executor image is Ubuntu 16.04 (glibc 2.23);
        # hermetic-llvm targets glibc 2.28, so test binaries died with
        # "libm.so.6: version GLIBC_2.27 not found". Run remote actions in a
        # newer image instead (hermetic-llvm's rbe.bzl pins the same one).
        # Only applies when the execution platform sets no exec_properties.
        "--remote_default_exec_properties=container-image=docker://ubuntu:22.04",
    ],
)

def tarball_source(archive, strip_prefix = "", source_subdir = ""):
    return struct(
        kind = "tarball",
        archive = archive,
        strip_prefix = strip_prefix,
        source_subdir = source_subdir,
    )

def bcr_module_source(module, version):
    return struct(
        kind = "bcr_module",
        module = module,
        version = version,
        source_subdir = "",
    )

def project_spec(
        name,
        source,
        environments,
        build = None,
        test = None,
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None):
    return struct(
        name = name,
        source = source,
        environments = environments,
        build = build,
        test = test,
        toolchains = toolchains,
        bazel_version = bazel_version,
        clients = clients,
    )

def inner_bazel(version):
    vtag = version.replace(".", "_")
    return select({
        "//bazel_runner:linux_amd64": "@inner_bazel_{}_linux_amd64//file".format(vtag),
        "//bazel_runner:linux_arm64": "@inner_bazel_{}_linux_arm64//file".format(vtag),
        "//bazel_runner:darwin_amd64": "@inner_bazel_{}_darwin_amd64//file".format(vtag),
        "//bazel_runner:darwin_arm64": "@inner_bazel_{}_darwin_arm64//file".format(vtag),
    })

def inner_bazel_data(version):
    vtag = version.replace(".", "_")
    return select({
        "//bazel_runner:linux_amd64": ["@inner_bazel_{}_linux_amd64//file".format(vtag)],
        "//bazel_runner:linux_arm64": ["@inner_bazel_{}_linux_arm64//file".format(vtag)],
        "//bazel_runner:darwin_amd64": ["@inner_bazel_{}_darwin_amd64//file".format(vtag)],
        "//bazel_runner:darwin_arm64": ["@inner_bazel_{}_darwin_arm64//file".format(vtag)],
    })

def inner_bazel_arg(version):
    vtag = version.replace(".", "_")
    return select({
        "//bazel_runner:linux_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_amd64//file)".format(vtag)],
        "//bazel_runner:linux_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_arm64//file)".format(vtag)],
        "//bazel_runner:darwin_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_amd64//file)".format(vtag)],
        "//bazel_runner:darwin_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_arm64//file)".format(vtag)],
    })

def _extract_source_impl(ctx):
    out = ctx.actions.declare_directory(ctx.attr.name)
    args = ctx.actions.args()
    args.add(ctx.file.archive)
    args.add(out.path)
    args.add(ctx.attr.strip_prefix)
    for src, dest in ctx.attr.appends.items():
        args.add("--append")
        args.add(_single_file(src[DefaultInfo].files, "appends"))
        args.add(dest)
    for src, dest in ctx.attr.writes.items():
        args.add("--write")
        args.add(_single_file(src[DefaultInfo].files, "writes"))
        args.add(dest)
    ctx.actions.run_shell(
        inputs = [ctx.file.archive] + ctx.files.appends + ctx.files.writes,
        outputs = [out],
        arguments = [args],
        command = """
set -euo pipefail
archive="$1"
out="$2"
strip_prefix="$3"
shift 3
mkdir -p "$out"
if [[ -n "$strip_prefix" ]]; then
  strip_components=$(awk -F/ '{print NF}' <<< "$strip_prefix")
  tar -xzf "$archive" -C "$out" --strip-components="$strip_components" "$strip_prefix"
else
  tar -xzf "$archive" -C "$out"
fi
while (($#)); do
  op="$1"
  src="$2"
  dest="$3"
  shift 3
  mkdir -p "$(dirname "$out/$dest")"
  case "$op" in
    --append)
      printf '\\n' >> "$out/$dest"
      cat "$src" >> "$out/$dest"
      printf '\\n' >> "$out/$dest"
      ;;
    --write)
      cp "$src" "$out/$dest"
      chmod +x "$out/$dest"
      ;;
    *)
      echo "unknown overlay op: $op" >&2
      exit 2
      ;;
  esac
done
""",
    )
    return [DefaultInfo(files = depset([out]))]

extract_source = rule(
    implementation = _extract_source_impl,
    attrs = {
        "appends": attr.label_keyed_string_dict(allow_files = True),
        "archive": attr.label(allow_single_file = True, mandatory = True),
        "strip_prefix": attr.string(),
        "writes": attr.label_keyed_string_dict(allow_files = True),
    },
)

def _bcr_source_impl(ctx):
    out = ctx.actions.declare_directory(ctx.attr.name)
    args = ctx.actions.args()
    args.add(out.path)
    args.add(ctx.attr.module)
    args.add(ctx.attr.version)
    for src, dest in ctx.attr.appends.items():
        args.add("--append")
        args.add(_single_file(src[DefaultInfo].files, "appends"))
        args.add(dest)
    for src, dest in ctx.attr.writes.items():
        args.add("--write")
        args.add(_single_file(src[DefaultInfo].files, "writes"))
        args.add(dest)
    ctx.actions.run_shell(
        inputs = ctx.files.appends + ctx.files.writes,
        outputs = [out],
        arguments = [args],
        command = """
set -euo pipefail
out="$1"
module="$2"
version="$3"
shift 3
mkdir -p "$out"
cat > "$out/MODULE.bazel" <<EOF
module(name = "bazel_runner_bcr_${module}")
bazel_dep(name = "${module}", version = "${version}")
EOF
touch "$out/BUILD.bazel"
while (($#)); do
  op="$1"
  src="$2"
  dest="$3"
  shift 3
  mkdir -p "$(dirname "$out/$dest")"
  case "$op" in
    --append)
      printf '\\n' >> "$out/$dest"
      cat "$src" >> "$out/$dest"
      printf '\\n' >> "$out/$dest"
      ;;
    --write)
      cp "$src" "$out/$dest"
      chmod +x "$out/$dest"
      ;;
    *)
      echo "unknown overlay op: $op" >&2
      exit 2
      ;;
  esac
done
""",
    )
    return [DefaultInfo(files = depset([out]))]

bcr_source = rule(
    implementation = _bcr_source_impl,
    attrs = {
        "appends": attr.label_keyed_string_dict(allow_files = True),
        "module": attr.string(mandatory = True),
        "version": attr.string(mandatory = True),
        "writes": attr.label_keyed_string_dict(allow_files = True),
    },
)

def _single_file(files, attr_name):
    files = files.to_list()
    if len(files) != 1:
        fail("{} must provide exactly one file, got {}".format(attr_name, len(files)))
    return files[0]

def _job_label(package, target_name):
    parts = package.split("/")
    if len(parts) >= 3 and parts[0] == "projects":
        project = "/".join(parts[1:-1])
        variant = parts[-1]
    else:
        project = package
        variant = "unknown"
    environment = "rbe" if "_rbe_" in target_name else "local"
    command = "test" if target_name.endswith("_test") else "build"
    return "{}/{}/{}/{}".format(project, variant, environment, command)

def _local_build_name(project_name):
    return project_name + "_local_build"

def _rbe_build_name(project_name):
    return project_name + "_rbe_build"

def _local_test_name(project_name):
    return project_name + "_local_test"

def _rbe_test_name(project_name):
    return project_name + "_rbe_test"

def _bazel_runner_build_impl(ctx):
    source = _single_file(ctx.attr.source[DefaultInfo].files, "source")
    out = ctx.actions.declare_file(ctx.attr.name + ".tar")

    args = ctx.actions.args()
    args.add("--mode=build")
    args.add("--job", _job_label(ctx.label.package, ctx.attr.name))
    args.add("--source", source.path)
    if ctx.attr.source_subdir:
        args.add("--source_subdir", ctx.attr.source_subdir)
    args.add("--bazel", ctx.file.bazel.path)
    args.add("--bundle", out.path)
    args.add_all(ctx.attr.flags, format_each = "--flag=%s")
    args.add_all(ctx.attr.targets, format_each = "--target=%s")

    ctx.actions.run(
        executable = ctx.executable._runner,
        inputs = depset([source, ctx.file.bazel]),
        outputs = [out],
        arguments = [args],
        mnemonic = "BazelRunnerBuild",
        progress_message = "building %{label}",
        use_default_shell_env = ctx.attr.use_default_shell_env,
    )
    return [DefaultInfo(files = depset([out]))]

_bazel_runner_build = rule(
    implementation = _bazel_runner_build_impl,
    attrs = {
        "bazel": attr.label(allow_single_file = True, mandatory = True),
        "flags": attr.string_list(),
        "source": attr.label(mandatory = True),
        "source_subdir": attr.string(),
        "targets": attr.string_list(mandatory = True),
        "use_default_shell_env": attr.bool(),
        "_runner": attr.label(
            default = Label("//bazel_runner:bazel_runner"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def bazel_runner_build(name, source, bazel, targets, flags = [], source_subdir = "", visibility = None, use_default_shell_env = False):
    _bazel_runner_build(
        name = name,
        source = source,
        source_subdir = source_subdir,
        bazel = bazel,
        targets = targets,
        flags = flags,
        visibility = visibility,
        use_default_shell_env = use_default_shell_env,
    )

def bazel_runner_test(name, source, targets, bazel = None, bazel_data = None, bazel_arg = None, flags = [], source_subdir = "", env_inherit = [], visibility = None):
    if bazel_data == None:
        bazel_data = [bazel]
    if bazel_arg == None:
        bazel_arg = ["--bazel=$(rlocationpath %s)" % bazel]

    py_test(
        name = name,
        srcs = ["//bazel_runner:bazel_runner.py"],
        main = "bazel_runner.py",
        args = [
            "--mode=test",
            "--job=%s" % _job_label(native.package_name(), name),
            "--source=$(rlocationpath %s)" % source,
        ] + ([
            "--source_subdir=%s" % source_subdir,
        ] if source_subdir else []) + bazel_arg + [
            "--flag=%s" % flag.replace("$", "$$")
            for flag in flags
        ] + [
            "--target=%s" % target
            for target in targets
        ],
        data = [
            source,
        ] + bazel_data,
        deps = ["@rules_python//python/runfiles"],
        env_inherit = env_inherit,
        size = "large",
        timeout = "eternal",
        visibility = visibility,
    )

def _spec_targets(spec, environment):
    """Target patterns for a build/test spec in an environment.

    exclude_on maps an environment name ("local"/"rbe") to target patterns to
    exclude there, e.g. tests that read host state absent on RBE workers.
    """
    excluded = spec.exclude_on.get(environment, [])
    return spec.targets + ["-" + target for target in excluded]

def _overlay_files(toolchains, field):
    result = {}
    for toolchain in toolchains:
        for label, dest in getattr(toolchain, field):
            result[Label(label)] = dest
    return result

def _overlay_build_flags(toolchains):
    result = []
    for toolchain in toolchains:
        result.extend(toolchain.build_flags)
    return result

def _emit_source(name, source, toolchains):
    if source.kind == "tarball":
        extract_source(
            name = name,
            archive = source.archive,
            strip_prefix = source.strip_prefix,
            appends = _overlay_files(toolchains, "appends"),
            writes = _overlay_files(toolchains, "writes"),
        )
    elif source.kind == "bcr_module":
        bcr_source(
            name = name,
            module = source.module,
            version = source.version,
            appends = _overlay_files(toolchains, "appends"),
            writes = _overlay_files(toolchains, "writes"),
        )
    else:
        fail("unknown source kind: {}".format(source.kind))

def _emit_bazel_runner_targets_for_spec(source, toolchains, build, test, bazel_version, target_prefix, visibility):
    if source.kind == "bcr_module" and build == None and test != None:
        build = build_spec(targets = test.targets, flags = test.flags)
    _emit_source("bazel_runner_source", source, toolchains)
    _emit_bazel_runner_targets_for_source(
        source = ":bazel_runner_source",
        source_subdir = source.source_subdir,
        toolchains = toolchains,
        build = build,
        test = test,
        bazel_version = bazel_version,
        target_prefix = target_prefix,
        visibility = visibility,
    )

def _emit_bazel_runner_targets(source_archive, strip_prefix, source_subdir, toolchains, build, test, bazel_version, target_prefix, visibility):
    extract_source(
        name = "bazel_runner_source",
        archive = source_archive,
        strip_prefix = strip_prefix,
        appends = _overlay_files(toolchains, "appends"),
        writes = _overlay_files(toolchains, "writes"),
    )

    bazel = inner_bazel(bazel_version)
    build_flags = _overlay_build_flags(toolchains) + _overlay_build_flags([BUILDBUDDY_BES])
    rbe_build_flags = build_flags + _overlay_build_flags([BUILDBUDDY_RBE])
    if build:
        bazel_runner_build(
            name = _local_build_name(target_prefix),
            source = ":bazel_runner_source",
            bazel = bazel,
            targets = _spec_targets(build, "local"),
            flags = build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        bazel_runner_build(
            name = _rbe_build_name(target_prefix),
            source = ":bazel_runner_source",
            bazel = bazel,
            targets = _spec_targets(build, "rbe"),
            flags = rbe_build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
            use_default_shell_env = True,
        )
    if test:
        bazel_runner_test(
            name = _local_test_name(target_prefix),
            source = ":bazel_runner_source",
            targets = _spec_targets(test, "local"),
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = build_flags + test.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        bazel_runner_test(
            name = _rbe_test_name(target_prefix),
            source = ":bazel_runner_source",
            targets = _spec_targets(test, "rbe"),
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = rbe_build_flags + test.flags,
            source_subdir = source_subdir,
            env_inherit = ["BUILDBUDDY_API_KEY"],
            visibility = visibility,
        )

def _emit_bazel_runner_targets_for_source(source, source_subdir, toolchains, build, test, bazel_version, target_prefix, visibility):
    bazel = inner_bazel(bazel_version)
    build_flags = _overlay_build_flags(toolchains) + _overlay_build_flags([BUILDBUDDY_BES])
    rbe_build_flags = build_flags + _overlay_build_flags([BUILDBUDDY_RBE])
    if build:
        bazel_runner_build(
            name = _local_build_name(target_prefix),
            source = source,
            bazel = bazel,
            targets = _spec_targets(build, "local"),
            flags = build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        bazel_runner_build(
            name = _rbe_build_name(target_prefix),
            source = source,
            bazel = bazel,
            targets = _spec_targets(build, "rbe"),
            flags = rbe_build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
            use_default_shell_env = True,
        )
    if test:
        bazel_runner_test(
            name = _local_test_name(target_prefix),
            source = source,
            targets = _spec_targets(test, "local"),
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = build_flags + test.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        bazel_runner_test(
            name = _rbe_test_name(target_prefix),
            source = source,
            targets = _spec_targets(test, "rbe"),
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = rbe_build_flags + test.flags,
            source_subdir = source_subdir,
            env_inherit = ["BUILDBUDDY_API_KEY"],
            visibility = visibility,
        )

def matrix_project(
        name = None,
        environments = None,
        source_archive = None,
        build = None,
        test = None,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        project = None,
        visibility = ["//visibility:public"]):
    if project:
        name = project.name
        source = project.source
        environments = project.environments
        build = project.build if build == None else build
        test = project.test if test == None else test
        toolchains = project.toolchains if toolchains == [] else toolchains
        bazel_version = project.bazel_version
        clients = project.clients if clients == None else clients
    else:
        source = tarball_source(source_archive, strip_prefix, source_subdir)
    if clients:
        fail("matrix_project does not support clients=; use bazel_version=")
    _emit_bazel_runner_targets_for_spec(source, toolchains, build, test, bazel_version, name, visibility)

def project_modification(
        name = None,
        environments = None,
        source_archive = None,
        build = None,
        test = None,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        project = None,
        visibility = ["//visibility:public"]):
    if project:
        name = project.name
        source = project.source
        environments = project.environments
        build = project.build if build == None else build
        test = project.test if test == None else test
        toolchains = project.toolchains + toolchains
        bazel_version = project.bazel_version
        clients = project.clients if clients == None else clients
    else:
        source = tarball_source(source_archive, strip_prefix, source_subdir)
    if clients:
        fail("project_modification does not support clients=; use bazel_version=")
    _emit_bazel_runner_targets_for_spec(
        source,
        toolchains,
        build,
        test,
        bazel_version,
        name,
        visibility,
    )

def hermetic_llvm_project_modification(
        name = None,
        environments = None,
        source_archive = None,
        build = None,
        test = None,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        project = None,
        visibility = ["//visibility:public"]):
    project_modification(
        name = name,
        source_archive = source_archive,
        environments = environments,
        build = build,
        test = test,
        strip_prefix = strip_prefix,
        source_subdir = source_subdir,
        toolchains = [_HERMETIC_LLVM_MODIFICATION] + toolchains,
        bazel_version = bazel_version,
        clients = clients,
        project = project,
        visibility = visibility,
    )

def project_test(
        name,
        source_archive,
        test,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    _emit_bazel_runner_targets(source_archive, strip_prefix, source_subdir, toolchains, None, test, bazel_version, name, visibility)

def bcr_project(
        name,
        module,
        version,
        environments,
        build = None,
        test = None,
        toolchains = None,
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    if clients:
        fail("bcr_project does not support clients=; use bazel_version=")
    _emit_bcr_project(
        name = name,
        module = module,
        version = version,
        build = build,
        test = test,
        toolchains = toolchains,
        bazel_version = bazel_version,
        visibility = visibility,
    )

def bcr_project_from_spec(
        project,
        toolchains = None,
        visibility = ["//visibility:public"]):
    if project.clients:
        fail("bcr_project_from_spec does not support clients=; use bazel_version=")
    if project.source.kind != "bcr_module":
        fail("bcr_project_from_spec requires a bcr_module source")
    _emit_bcr_project(
        name = project.name,
        module = project.source.module,
        version = project.source.version,
        build = project.build,
        test = project.test,
        toolchains = project.toolchains if toolchains == None else toolchains,
        bazel_version = project.bazel_version,
        visibility = visibility,
    )

def _emit_bcr_project(
        name,
        module,
        version,
        build,
        test,
        toolchains,
        bazel_version,
        visibility):
    if build == None and test != None:
        build = build_spec(targets = test.targets, flags = test.flags)
    bcr_source(
        name = "bazel_runner_source",
        module = module,
        version = version,
        appends = _overlay_files(toolchains or [], "appends"),
        writes = _overlay_files(toolchains or [], "writes"),
    )
    _emit_bazel_runner_targets_for_source(
        source = ":bazel_runner_source",
        source_subdir = "",
        toolchains = toolchains or [],
        build = build,
        test = test,
        bazel_version = bazel_version,
        target_prefix = name,
        visibility = visibility,
    )
