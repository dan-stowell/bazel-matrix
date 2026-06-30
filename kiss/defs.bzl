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
_RBE_HERMETIC_LLVM = overlay(
    name = "rbe_hermetic_llvm",
    appends = [("//kiss:hermetic_llvm.MODULE.bazel", "MODULE.bazel")],
)
CC_NODETECT = overlay(name = "cc_nodetect")
HERMETIC_ZIP = overlay(
    name = "hermetic_zip",
    writes = [("//kiss:zip.py", ".kiss-tools/zip")],
    build_flags = ["--strategy=Genrule=local"],
)
RULES_RUST_SYSROOT_FIX = overlay(name = "rules_rust_sysroot_fix")
RULES_CC_DEP = overlay(name = "rules_cc_dep")
PLATFORMS_DEP = overlay(name = "platforms_dep")
BUILDBUDDY_RBE = overlay(
    name = "buildbuddy_rbe",
    build_flags = [
        "--bes_results_url=https://buildbuddy.buildbuddy.io/invocation/",
        "--bes_backend=grpcs://buildbuddy.buildbuddy.io",
        "--remote_cache=grpcs://buildbuddy.buildbuddy.io",
        "--remote_timeout=10m",
        "--jobs=32",
        "--remote_executor=grpcs://buildbuddy.buildbuddy.io",
        "--remote_header=x-buildbuddy-api-key=$BUILDBUDDY_API_KEY",
    ],
)
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
module(name = "kiss_bcr_${module}")
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

def _kiss_build_impl(ctx):
    source = _single_file(ctx.attr.source[DefaultInfo].files, "source")
    out = ctx.actions.declare_file(ctx.attr.name + ".tar")

    args = ctx.actions.args()
    args.add("--mode=build")
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
        mnemonic = "KissBuild",
        progress_message = "KISS building %{label}",
        use_default_shell_env = ctx.attr.use_default_shell_env,
    )
    return [DefaultInfo(files = depset([out]))]

_kiss_build = rule(
    implementation = _kiss_build_impl,
    attrs = {
        "bazel": attr.label(allow_single_file = True, mandatory = True),
        "flags": attr.string_list(),
        "source": attr.label(mandatory = True),
        "source_subdir": attr.string(),
        "targets": attr.string_list(mandatory = True),
        "use_default_shell_env": attr.bool(),
        "_runner": attr.label(
            default = Label("//kiss:kiss_runner"),
            executable = True,
            cfg = "exec",
        ),
    },
)

def kiss_build(name, source, bazel, targets, flags = [], source_subdir = "", visibility = None, use_default_shell_env = False):
    _kiss_build(
        name = name,
        source = source,
        source_subdir = source_subdir,
        bazel = bazel,
        targets = targets,
        flags = flags,
        visibility = visibility,
        use_default_shell_env = use_default_shell_env,
    )

def kiss_test(name, source, targets, bazel = None, bazel_data = None, bazel_arg = None, flags = [], source_subdir = "", visibility = None):
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
        ] + ([
            "--source_subdir=%s" % source_subdir,
        ] if source_subdir else []) + bazel_arg + [
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

def _rbe_toolchains(toolchains, rbe_toolchains):
    return rbe_toolchains if rbe_toolchains != None else []

def _emit_kiss_targets(source_archive, strip_prefix, source_subdir, toolchains, rbe_toolchains, build, test, bazel_version, visibility):
    extract_source(
        name = "kiss_source",
        archive = source_archive,
        strip_prefix = strip_prefix,
        appends = _overlay_files(toolchains, "appends"),
        writes = _overlay_files(toolchains, "writes"),
    )
    rbe_toolchains = _rbe_toolchains(toolchains, rbe_toolchains)
    if build:
        extract_source(
            name = "kiss_rbe_source",
            archive = source_archive,
            strip_prefix = strip_prefix,
            appends = _overlay_files(rbe_toolchains, "appends"),
            writes = _overlay_files(rbe_toolchains, "writes"),
        )

    bazel = inner_bazel(bazel_version)
    build_flags = _overlay_build_flags(toolchains)
    rbe_build_flags = _overlay_build_flags(rbe_toolchains) + _overlay_build_flags([BUILDBUDDY_RBE])
    if build:
        kiss_build(
            name = "kiss_build",
            source = ":kiss_source",
            bazel = bazel,
            targets = build.targets,
            flags = build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        kiss_build(
            name = "kiss_rbe_build",
            source = ":kiss_rbe_source",
            bazel = bazel,
            targets = build.targets,
            flags = rbe_build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
            use_default_shell_env = True,
        )
    if test:
        kiss_test(
            name = "kiss_test",
            source = ":kiss_source",
            targets = test.targets,
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = build_flags + test.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )

def _emit_kiss_targets_for_source(source, rbe_source, source_subdir, toolchains, rbe_toolchains, build, test, bazel_version, visibility):
    bazel = inner_bazel(bazel_version)
    build_flags = _overlay_build_flags(toolchains)
    rbe_toolchains = _rbe_toolchains(toolchains, rbe_toolchains)
    rbe_build_flags = _overlay_build_flags(rbe_toolchains) + _overlay_build_flags([BUILDBUDDY_RBE])
    if build:
        kiss_build(
            name = "kiss_build",
            source = source,
            bazel = bazel,
            targets = build.targets,
            flags = build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )
        kiss_build(
            name = "kiss_rbe_build",
            source = rbe_source,
            bazel = bazel,
            targets = build.targets,
            flags = rbe_build_flags + build.flags,
            source_subdir = source_subdir,
            visibility = visibility,
            use_default_shell_env = True,
        )
    if test:
        kiss_test(
            name = "kiss_test",
            source = source,
            targets = test.targets,
            bazel_data = inner_bazel_data(bazel_version),
            bazel_arg = inner_bazel_arg(bazel_version),
            flags = build_flags + test.flags,
            source_subdir = source_subdir,
            visibility = visibility,
        )

def museum_project(
        name,
        source_archive,
        environments,
        build = None,
        test = None,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    if clients:
        fail("KISS-only museum_project does not support clients=; use bazel_version=")
    _emit_kiss_targets(source_archive, strip_prefix, source_subdir, toolchains, None, build, test, bazel_version, visibility)

def project_test(
        name,
        source_archive,
        test,
        strip_prefix = "",
        source_subdir = "",
        toolchains = [],
        rbe_toolchains = None,
        bazel_version = DEFAULT_INNER_BAZEL_VERSION,
        clients = None,
        visibility = ["//visibility:public"]):
    _emit_kiss_targets(source_archive, strip_prefix, source_subdir, toolchains, rbe_toolchains, None, test, bazel_version, visibility)

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
    if clients:
        fail("KISS-only bcr_project does not support clients=; use bazel_version=")
    if build == None and test != None:
        build = build_spec(targets = test.targets, flags = test.flags)
    bcr_source(
        name = "kiss_source",
        module = module,
        version = version,
        appends = _overlay_files(toolchains or [], "appends"),
        writes = _overlay_files(toolchains or [], "writes"),
    )
    if build:
        computed_rbe_toolchains = _rbe_toolchains(toolchains or [], rbe_toolchains)
        bcr_source(
            name = "kiss_rbe_source",
            module = module,
            version = version,
            appends = _overlay_files(computed_rbe_toolchains, "appends"),
            writes = _overlay_files(computed_rbe_toolchains, "writes"),
        )
    else:
        computed_rbe_toolchains = rbe_toolchains
    _emit_kiss_targets_for_source(
        source = ":kiss_source",
        rbe_source = ":kiss_rbe_source",
        source_subdir = "",
        toolchains = toolchains or [],
        rbe_toolchains = computed_rbe_toolchains,
        build = build,
        test = test,
        bazel_version = bazel_version,
        visibility = visibility,
    )
