load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# FlatBuffers — serialization library + the flatc schema compiler.
# Source pinned in //kiss:extension.bzl (@flatbuffers_archive, v25.12.19).
# Built from the upstream source/module as-is. The hermetic LLVM modification
# lives in //projects/flatbuffers/hermetic_llvm. flatbuffers
# pulls old aspect_bazel_lib / rules_foreign_cc / rules_go transitively, whose
# toolchains use APIs Bazel 9 removed — Bazel 8.7 resolves them as authored.
#
FLATBUFFERS_PROJECT = project_spec(
    name = "flatbuffers",
    source = tarball_source(
        archive = "@flatbuffers_archive//file",
        strip_prefix = "flatbuffers-25.12.19-2026-02-06-03fffb2",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:flatc", "//:flatbuffers"], flags = ["-c", "opt"]),
    # The C++ test suite is one monolithic cc_test that reads its schema/JSON
    # fixtures from runfiles (the //tests:test_data filegroup). The Go/TS/Swift
    # and the bazel-repository integration tests live in other toolchains.
    test = test_spec(targets = ["//tests:flatbuffers_test"]),
)
