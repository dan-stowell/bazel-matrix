load("@rules_python//python:defs.bzl", "py_test")
load("//kiss:extension.bzl", "DEFAULT_INNER_BAZEL_VERSION")

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
ACTIOND = _compat_env("actiond")
MINIMG = _compat_env("minimg")
CIIMG = _compat_env("ciimg")

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
CC_NODETECT = overlay(name = "cc_nodetect")
HERMETIC_ZIP = overlay(name = "hermetic_zip")
RULES_RUST_SYSROOT_FIX = overlay(name = "rules_rust_sysroot_fix")
RULES_CC_DEP = overlay(name = "rules_cc_dep")
PLATFORMS_DEP = overlay(name = "platforms_dep")
BUILDBUDDY_RBE = overlay(name = "buildbuddy_rbe")
ACTIOND_WORKER = overlay(name = "actiond_worker")

def inner_bazel(version):
    vtag = version.replace(".", "_")
    return select({
        "//kiss:linux_amd64": "@inner_bazel_{}_linux_amd64//file".format(vtag),
        "//kiss:linux_arm64": "@inner_bazel_{}_linux_arm64//file".format(vtag),
        "//kiss:darwin_amd64": "@inner_bazel_{}_darwin_amd64//file".format(vtag),
        "//kiss:darwin_arm64": "@inner_bazel_{}_darwin_arm64//file".format(vtag),
    })

def inner_bazel_data(version):
    vtag = version.replace(".", "_")
    return select({
        "//kiss:linux_amd64": ["@inner_bazel_{}_linux_amd64//file".format(vtag)],
        "//kiss:linux_arm64": ["@inner_bazel_{}_linux_arm64//file".format(vtag)],
        "//kiss:darwin_amd64": ["@inner_bazel_{}_darwin_amd64//file".format(vtag)],
        "//kiss:darwin_arm64": ["@inner_bazel_{}_darwin_arm64//file".format(vtag)],
    })

def inner_bazel_arg(version):
    vtag = version.replace(".", "_")
    return select({
        "//kiss:linux_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_amd64//file)".format(vtag)],
        "//kiss:linux_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_linux_arm64//file)".format(vtag)],
        "//kiss:darwin_amd64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_amd64//file)".format(vtag)],
        "//kiss:darwin_arm64": ["--bazel=$(rlocationpath @inner_bazel_{}_darwin_arm64//file)".format(vtag)],
    })

def _extract_source_impl(ctx):
    out = ctx.actions.declare_directory(ctx.attr.name)
    args = ctx.actions.args()
    args.add(ctx.file.archive)
    args.add(out.path)
    args.add(ctx.attr.strip_prefix)
    ctx.actions.run_shell(
        inputs = [ctx.file.archive],
        outputs = [out],
        arguments = [args],
        command = """
set -euo pipefail
archive="$1"
out="$2"
strip_prefix="$3"
mkdir -p "$out"
if [[ -n "$strip_prefix" ]]; then
  tar -xzf "$archive" -C "$out" --strip-components=1 "$strip_prefix"
else
  tar -xzf "$archive" -C "$out"
fi
""",
    )
    return [DefaultInfo(files = depset([out]))]

extract_source = rule(
    implementation = _extract_source_impl,
    attrs = {
        "archive": attr.label(allow_single_file = True, mandatory = True),
        "strip_prefix": attr.string(),
    },
)

def _single_file(files, attr_name):
    files = files.to_list()
    if len(files) != 1:
        fail("{} must provide exactly one file, got {}".format(attr_name, len(files)))
    return files[0]

def _kiss_build_impl(ctx):
    source = _single_file(ctx.attr.source[DefaultInfo].files, "source")
    out = ctx.actions.declare_file(ctx.attr.name + ".tar")

    args = ctx.actions.args()
    args.add("--mode=build")
    args.add("--source", source.path)
    args.add("--bazel", ctx.file.bazel.path)
    args.add("--bundle", out.path)
    args.add_all(ctx.attr.flags, before_each = "--flag")
    args.add_all(ctx.attr.targets, before_each = "--target")

    ctx.actions.run(
        executable = ctx.executable._runner,
        inputs = depset([source, ctx.file.bazel]),
        outputs = [out],
        arguments = [args],
        mnemonic = "KissBuild",
        progress_message = "KISS building %{label}",
    )
    return [DefaultInfo(files = depset([out]))]

_kiss_build = rule(
    implementation = _kiss_build_impl,
    attrs = {
        "bazel": attr.label(allow_single_file = True, mandatory = True),
        "flags": attr.string_list(),
        "source": attr.label(mandatory = True),
        "targets": attr.string_list(mandatory = True),
        "_runner": attr.label(
            default = Label("//kiss:kiss_runner"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def kiss_build(name, source, bazel, targets, flags = [], visibility = None):
    _kiss_build(
        name = name,
        source = source,
        bazel = bazel,
        targets = targets,
        flags = flags,
        visibility = visibility,
    )

def kiss_test(name, source, targets, bazel = None, bazel_data = None, bazel_arg = None, flags = [], visibility = None):
    if bazel_data == None:
        bazel_data = [bazel]
    if bazel_arg == None:
        bazel_arg = ["--bazel=$(rlocationpath %s)" % bazel]

    py_test(
        name = name,
        srcs = ["//kiss:kiss_runner.py"],
        main = "kiss_runner.py",
        args = [
            "--mode=test",
            "--source=$(rlocationpath %s)" % source,
        ] + bazel_arg + [
            "--flag=%s" % flag
            for flag in flags
        ] + [
            "--target=%s" % target
            for target in targets
        ],
        data = [
            source,
        ] + bazel_data,
        deps = ["@rules_python//python/runfiles"],
        size = "large",
        timeout = "eternal",
        visibility = visibility,
    )

def _emit_kiss_targets(source_archive, strip_prefix, build, test, bazel_version, visibility):
    extract_source(
        name = "kiss_source",
        archive = source_archive,
        strip_prefix = strip_prefix,
    )

    bazel = inner_bazel(bazel_version)
    if build:
        kiss_build(
            name = "kiss_build",
            source = ":kiss_source",
            bazel = bazel,
            targets = build.targets,
            visibility = visibility,
        )
    if test:
        kiss_test(
            name = "kiss_test",
            source = ":kiss_source",
            targets = test.targets,
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
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
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    if clients:
        fail("KISS-only museum_project does not support clients=; use bazel_version=")
    _emit_kiss_targets(source_archive, strip_prefix, build, test, bazel_version, visibility)

def project_test(
        name,
        source_archive,
        test,
        strip_prefix = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    _emit_kiss_targets(source_archive, strip_prefix, None, test, bazel_version, visibility)

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
    # BCR projects do not have pinned source archives in this repo, so there is
    # no KISS source/build/test target to emit for them.
    pass
