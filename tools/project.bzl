"""Rules that run one project's inner Bazel; see README.md.

`project()` (used by the generated //<module>:BUILD.bazel) declares
  - `build`: an action running inner `bazel build`, writing a summary and
    the inner log. It runs on the machine running the outer Bazel
    (no-remote-exec), but is not `local`, so the outer remote cache keeps
    its result;
  - `test`: a test running inner `bazel test`, writing one test.xml
    testcase per inner test target.
Both pass the inner Bazel the same flags; anything that changes them
(project flags, //:inner_flags, the inner Bazel version, the rc files)
changes the outer action key.
"""

# Pinned inner Bazel binaries (fetched in MODULE.bazel as
# @inner_bazel_<version with _>//file), with startup flags only some
# versions know.
INNER_BAZELS = {
    "9.3.1": ["--experimental_remote_repo_contents_cache"],
    "8.4.2": [],
}

DEFAULT_INNER_BAZEL = "9.3.1"

def _repo(version):
    return "@inner_bazel_%s//file" % version.replace(".", "_")

InnerSettingInfo = provider(fields = ["value"])

def _setting_impl(ctx):
    return [InnerSettingInfo(value = ctx.build_setting_value)]

string_list_setting = rule(
    implementation = _setting_impl,
    build_setting = config.string_list(flag = True, repeatable = True),
)

string_setting = rule(
    implementation = _setting_impl,
    build_setting = config.string(flag = True),
)

def _inputs(ctx):
    return [
        ctx.file.source,
        ctx.file.bazel,
        ctx.file._remote_rc,
        ctx.file._inner_rc,
        ctx.file._credential_helper,
        ctx.file._credentials_marker,
    ]

def _args(ctx, mode, path):
    version = ctx.attr.bazel_version
    if version not in INNER_BAZELS:
        fail("unknown inner Bazel version %s; known: %s" % (version, ", ".join(INNER_BAZELS)))
    flags = ctx.attr.flags + ctx.attr._inner_flags[InnerSettingInfo].value
    return [
        "--mode=" + mode,
        "--project=" + ctx.attr.project,
        "--source=" + path(ctx.file.source),
        "--bazel=" + path(ctx.file.bazel),
        "--bazel_version=" + version,
        "--rc=" + path(ctx.file._remote_rc),
        "--rc=" + path(ctx.file._inner_rc),
        "--credential_helper=" + path(ctx.file._credential_helper),
    ] + ["--startup_flag=" + f for f in INNER_BAZELS[version]] + [
        "--flag=" + f
        for f in flags
    ] + ["--target=" + t for t in ctx.attr.targets]

def _resources(_os, _inputs_size):
    # An inner Bazel server plus its client; see the tags in project().
    return {"cpu": 2, "memory": 2500}

def _build_impl(ctx):
    summary = ctx.actions.declare_file(ctx.attr.name + ".txt")
    log = ctx.actions.declare_file(ctx.attr.name + ".log")
    ctx.actions.run(
        executable = ctx.attr._runner[DefaultInfo].files_to_run,
        arguments = _args(ctx, "build", lambda f: f.path) + [
            "--summary=" + summary.path,
            "--log=" + log.path,
        ],
        inputs = _inputs(ctx),
        outputs = [summary, log],
        mnemonic = "InnerBazelBuild",
        progress_message = "Building %s with inner Bazel %s" % (ctx.attr.project, ctx.attr.bazel_version),
        execution_requirements = {
            "no-remote-exec": "1",
            "no-sandbox": "1",
            "requires-network": "1",
        },
        resource_set = _resources,
    )
    return [DefaultInfo(files = depset([summary, log]))]

def _shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"

def _test_impl(ctx):
    script = ctx.actions.declare_file(ctx.attr.name + ".sh")
    runner = ctx.attr._runner[DefaultInfo]
    args = _args(ctx, "test", lambda f: f.short_path)
    ctx.actions.write(
        script,
        "#!/bin/bash\nexec %s %s \"$@\"\n" % (
            _shell_quote(runner.files_to_run.executable.short_path),
            " ".join([_shell_quote(a) for a in args]),
        ),
        is_executable = True,
    )
    runfiles = ctx.runfiles(files = _inputs(ctx)).merge(runner.default_runfiles)
    return [DefaultInfo(executable = script, runfiles = runfiles)]

_ATTRS = {
    "bazel": attr.label(allow_single_file = True, mandatory = True),
    "bazel_version": attr.string(mandatory = True),
    "flags": attr.string_list(),
    "project": attr.string(mandatory = True),
    "source": attr.label(allow_single_file = True, mandatory = True),
    "targets": attr.string_list(mandatory = True),
    "_credential_helper": attr.label(allow_single_file = True, default = "//tools:buildbuddy_credential_helper.py"),
    "_credentials_marker": attr.label(allow_single_file = True, default = "@buildbuddy_credentials//:marker"),
    "_inner_flags": attr.label(default = "//:inner_flags"),
    "_inner_rc": attr.label(allow_single_file = True, default = "//tools:inner.bazelrc"),
    "_remote_rc": attr.label(allow_single_file = True, default = "//tools:remote.bazelrc"),
}

inner_build = rule(
    implementation = _build_impl,
    attrs = _ATTRS | {
        "_runner": attr.label(default = "//tools:inner_bazel", cfg = "exec"),
    },
)

inner_test = rule(
    implementation = _test_impl,
    test = True,
    attrs = _ATTRS | {
        "_runner": attr.label(default = "//tools:inner_bazel", cfg = "target"),
    },
)

def project(name, targets, flags = [], bazel_version = None):
    """The `build` and `test` targets of one project.

    Args:
      name: the BCR module.
      targets: inner target patterns, exclusions as `-//pattern`.
      flags: extra inner flags for both build and test.
      bazel_version: pins this project's inner Bazel; by default it's
        --//:inner_bazel_version.
    """
    if bazel_version:
        bazel = _repo(bazel_version)
        version = bazel_version
    else:
        bazel = select(
            {"//tools:inner_bazel_" + v: _repo(v) for v in INNER_BAZELS},
            no_match_error = "--//:inner_bazel_version must be one of " + ", ".join(INNER_BAZELS),
        )
        version = select({"//tools:inner_bazel_" + v: v for v in INNER_BAZELS})
    common = dict(
        project = name,
        source = "@projects//:" + name,
        bazel = bazel,
        bazel_version = version,
        targets = targets,
        flags = flags,
    )
    inner_build(name = "build", **common)
    inner_test(
        name = "test",
        size = "enormous",
        tags = [
            "no-remote-exec",
            "no-sandbox",
            "requires-network",
            "resources:cpu:2",
            "resources:memory:2500",
        ],
        **common
    )
