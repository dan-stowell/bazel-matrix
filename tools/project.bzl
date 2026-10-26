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
changes the outer action key. tools/remote.bazelrc, an input of both, pins
the executor image by digest, the same image the runner must run (see
tools/bb.sh), so the image is part of the key too.

With --//:inner_remote (see README.md, "Inner Bazels on RBE"), `test` runs
on an RBE executor instead, so its inner Bazel's host is the executor's
image and arch; it then runs tools/remote_inner_bazel.py, and the inner
Bazel is the one for the target cpu (linux-arm64 under
--platforms=//tools:linux_arm64).
"""

load(":versions.bzl", "INNER_BAZELS")

def _repo(version, arm64 = False):
    return "@projects//:bazel_" + version + ("_arm64" if arm64 else "")

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

bool_setting = rule(
    implementation = _setting_impl,
    build_setting = config.bool(flag = True),
)

# The test's execution requirements when it runs on the outer machine (not
# with --//:inner_remote); see project().
_LOCAL_TEST = {
    "no-remote-exec": "1",
    "no-sandbox": "1",
    "requires-network": "1",
}

def _inputs(ctx):
    return [
        ctx.file.source,
        ctx.file.bazel,
        ctx.file._remote_rc,
        ctx.file._inner_rc,
        ctx.file._credential_helper,
        ctx.file._credentials,
    ]

def _args(ctx, mode, path):
    version = ctx.attr.bazel_version
    if version not in INNER_BAZELS:
        fail("unknown inner Bazel version %s; known: %s" % (version, ", ".join(INNER_BAZELS)))
    aarch64 = ctx.attr._aarch64[platform_common.ConstraintValueInfo]
    if ctx.target_platform_has_constraint(aarch64) and not INNER_BAZELS[version].arm64_sha256:
        fail("%s: inner Bazel %s has no linux-arm64 binary in tools/versions.bzl" % (ctx.attr.project, version))
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
    ] + ["--startup_flag=" + f for f in INNER_BAZELS[version].startup_flags] + [
        "--flag=" + f
        for f in flags
    ] + ["--target=" + t for t in ctx.attr.targets]

def _resources(_os, _inputs_size):
    # An inner Bazel JVM (capped at 2 GB heap by tools/inner_bazel.py) plus
    # its client; see the tags in project().
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
    remote = ctx.attr._inner_remote[InnerSettingInfo].value
    return [
        DefaultInfo(executable = script, runfiles = runfiles),
        testing.ExecutionInfo({} if remote else _LOCAL_TEST),
    ]

_ATTRS = {
    "bazel": attr.label(allow_single_file = True, mandatory = True),
    "bazel_version": attr.string(mandatory = True),
    "flags": attr.string_list(),
    "project": attr.string(mandatory = True),
    "source": attr.label(allow_single_file = True, mandatory = True),
    "targets": attr.string_list(mandatory = True),
    "_aarch64": attr.label(default = "@platforms//cpu:aarch64"),
    "_credential_helper": attr.label(allow_single_file = True, default = "//tools:buildbuddy_credential_helper.py"),
    # Not the key: a constant marker that makes the key file exist.
    "_credentials": attr.label(allow_single_file = True, default = "@buildbuddy_credentials//:marker"),
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
        "_inner_remote": attr.label(default = "//:inner_remote"),
        "_runner": attr.label(default = "//tools:test_runner", cfg = "target"),
    },
)

def project(name, targets, flags = [], bazel_version = None, known_failing = None):
    """The `build` and `test` targets of one project.

    Args:
      name: the BCR module.
      targets: inner target patterns, exclusions as `-//pattern`.
      flags: extra inner flags for both build and test.
      bazel_version: pins this project's inner Bazel; by default it's
        --//:inner_bazel_version.
      known_failing: "build" tags both targets `manual`, "test" only the
        test, so `//...` skips them; naming them still runs them.
    """
    if known_failing not in (None, "build", "test"):
        fail("known_failing must be None, \"build\" or \"test\"")
    # For //tools:generated_test, which checks it against projects.txt.
    native.exports_files(["BUILD.bazel"], visibility = ["//tools:__pkg__"])
    manual = ["manual"] if known_failing else []
    # The linux-arm64 inner Bazel when the target cpu is aarch64 (the test
    # runs it on an arm64 executor), else linux-x86_64.
    if bazel_version:
        bazel = select({
            "//tools:aarch64": _repo(bazel_version, arm64 = True),
            "//conditions:default": _repo(bazel_version),
        }) if INNER_BAZELS[bazel_version].arm64_sha256 else _repo(bazel_version)
        version = bazel_version
    else:
        bazel = select(
            {"//tools:inner_bazel_" + v: _repo(v) for v in INNER_BAZELS} |
            {"//tools:inner_bazel_%s_arm64" % v: _repo(v, arm64 = True) for v, i in INNER_BAZELS.items() if i.arm64_sha256},
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
    inner_build(
        name = "build",
        tags = manual if known_failing == "build" else [],
        # It runs on the outer machine, which can't run an arm64 inner
        # Bazel (--config=inner-remote-arm64 runs only :test remotely).
        target_compatible_with = select({
            "//tools:aarch64": ["@platforms//:incompatible"],
            "//conditions:default": [],
        }),
        **common
    )
    inner_test(
        name = "test",
        size = "enormous",
        timeout = "eternal",
        # no-remote-exec, no-sandbox and requires-network come from the
        # rule (_LOCAL_TEST), unless --//:inner_remote.
        tags = [
            "resources:cpu:2",
            "resources:memory:2500",
        ] + manual,
        **common
    )

# For target_compatible_with of tests that must not share an invocation with
# --//:inner_remote, whose env-overrides header puts the API key in the
# environment of every remote action (README.md, "Inner Bazels on RBE").
NOT_WITH_INNER_REMOTE = select({
    "//tools:inner_remote": ["@platforms//:incompatible"],
    "//conditions:default": [],
})
