load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# google/benchmark — the C++ microbenchmark library.
# Source pinned in //kiss:extension.bzl (@benchmark_archive, release
# v1.9.5), built from the upstream source/module as-is. The hermetic LLVM
# modification lives in //projects/benchmark/hermetic_llvm.
BENCHMARK_PROJECT = project_spec(
    name = "benchmark",
    source = tarball_source(
        archive = "@benchmark_archive//file",
        strip_prefix = "benchmark-1.9.5",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:benchmark"], flags = ["-c", "opt"]),
    # benchmark's own self-test suite (//test) — it exercises the library against
    # googletest plus output-format assertions. locale_impermeability_test is
    # excluded everywhere: it switches to the en_US.UTF-8 locale to prove output
    # is locale-independent, but that locale isn't a Bazel-tracked input in the
    # hermetic environment (only C.UTF-8 exists), so it can't construct it.
    test = test_spec(
        targets = ["//test/...", "-//test:locale_impermeability_test"],
        flags = ["-c", "opt"],
    ),
)
