load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# highway — Google's portable SIMD/vector library (C++).
# Source pinned in //kiss:extension.bzl (@highway_archive, release
# 1.4.0), built from the upstream source/module as-is. The hermetic LLVM
# modification lives in //projects/highway/hermetic_llvm. The library loads
# rules_cc, but its test suite depends on googletest (cc_* unloaded), so it runs
# on the Bazel 8.7 inner like the other googletest-consuming C++ projects.
#
HIGHWAY_PROJECT = project_spec(
    name = "highway",
    source = tarball_source(
        archive = "@highway_archive//file",
        strip_prefix = "highway-1.4.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:hwy"], flags = ["-c", "opt"]),
    # highway's full suite is ~130 tests, each compiled across every SIMD target
    # the toolchain enables (SSE4/AVX2/AVX3/...) — 40–50s per test to compile, so
    # the whole suite is impractically heavy for a routine goal. We run a core
    # representative subset that exercises the fundamental vector API (base ops,
    # arithmetic, logical, compare, plus the top-level smoke test) — enough to
    # prove highway's SIMD tests build + run hermetically and dispatch correctly.
    test = test_spec(
        targets = [
            "//:base_test",
            "//:arithmetic_test",
            "//:logical_test",
            "//:compare_test",
            "//:highway_test",
        ],
        flags = ["-c", "opt"],
    ),
)
