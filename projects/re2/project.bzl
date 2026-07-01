load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
_RE2_TEST = test_spec(
    targets = [
        "//:all",
        "-//:exhaustive_test",
        "-//:exhaustive1_test",
        "-//:exhaustive2_test",
        "-//:exhaustive3_test",
    ],
    flags = ["-c", "opt"],
)

RE2_PROJECT = project_spec(
    name = "re2",
    source = tarball_source(
        archive = "@re2_archive//file",
        strip_prefix = "re2-2025-11-05",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:re2"], flags = ["-c", "opt"]),
    test = _RE2_TEST,
)
