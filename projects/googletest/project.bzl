load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# GoogleTest — the C++ test framework.
# Source pinned in //kiss:extension.bzl (@googletest_archive, v1.17.0),
# built from the upstream source/module as-is. The hermetic LLVM modification
# lives in //projects/googletest/hermetic_llvm. The iconic artifacts: the gtest
# + gtest_main libraries (//:gtest bundles gmock).
#
# googletest 1.17.0's BUILD files (root + the test packages) call cc_library/
# cc_test/cc_binary unloaded, which Bazel 9 removed from the builtins. Rather
# than patch a load() into every package, we run the Bazel 8.7 inner — recent
# enough to carry the zero-sysroot hermetic-llvm toolchain (needs repo_metadata,
# added in 8.3), and old enough to still autoload the cc_* rules as authored.
#
GOOGLETEST_PROJECT = project_spec(
    name = "googletest",
    source = tarball_source(
        archive = "@googletest_archive//file",
        strip_prefix = "googletest-1.17.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:gtest", "//:gtest_main"], flags = ["-c", "opt"]),
    # googletest's own self-test suite: the C++ unit tests plus the Python-driven
    # tests that exercise the compiled binaries' output (rules_python supplies a
    # hermetic interpreter via bzlmod).
    test = test_spec(targets = ["//googletest/test/...", "//googlemock/test/..."]),
)
