load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "build_spec", "project_spec", "tarball_source", "test_spec")
# cpptrace — a C++ stacktrace / backtrace library. Source pinned in
# //kiss:extension.bzl (@cpptrace_archive, release v1.0.4). First-party
# Bazel: the project self-registers toolchains_llvm (a hermetic clang) and pulls
# zstd/xz via rules_foreign_cc. Built host-locally on a late Bazel 8 inner (its
# root BUILD calls cc_library unloaded). LOCAL-only.
#
#   bazel run //projects/cpptrace:build_local_linux_amd64
#   bazel run //projects/cpptrace:test_local_linux_amd64
CPPTRACE_PROJECT = project_spec(
    name = "cpptrace",
    source = tarball_source(
        archive = "@cpptrace_archive//file",
        strip_prefix = "cpptrace-1.0.4",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "8.7.0",
    environments = [LOCAL, MINIMG],
    build = build_spec(targets = ["//:cpptrace"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//test:unittest"], flags = ["-c", "opt"]),
)
