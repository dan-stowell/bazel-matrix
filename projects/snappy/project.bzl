load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# snappy — Google's fast compression/decompression library (C++).
# Source pinned in //kiss:extension.bzl (@snappy_archive, release 1.2.2),
# built from the upstream source/module as-is. The hermetic LLVM modification
# lives in //projects/snappy/hermetic_llvm.
SNAPPY_PROJECT = project_spec(
    name = "snappy",
    source = tarball_source(
        archive = "@snappy_archive//file",
        strip_prefix = "snappy-1.2.2",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:snappy"], flags = ["-c", "opt"]),
    # snappy's correctness unit test (reads the bundled testdata corpus). The
    # sibling snappy_benchmark target is a benchmark, not parity — left out.
    test = test_spec(targets = ["//:snappy_unittest"], flags = ["-c", "opt"]),
)
