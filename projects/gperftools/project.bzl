load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# gperftools — Google performance tools: the tcmalloc allocator + profilers (C++).
# Source pinned in //kiss:extension.bzl (@gperftools_archive, release
# 2.18.1), built from the upstream source/module as-is. The hermetic LLVM
# modification lives in //projects/gperftools/hermetic_llvm. First-party Bazel, but
# its tests pull in googletest (cc_* unloaded), so it runs on the Bazel 8.7
# inner. (gperftools declares a direct platforms dep, so no PLATFORMS_DEP.)
#
GPERFTOOLS_PROJECT = project_spec(
    name = "gperftools",
    source = tarball_source(
        archive = "@gperftools_archive//file",
        strip_prefix = "gperftools-gperftools-2.18.1",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:tcmalloc_minimal"], flags = ["-c", "opt"]),
    # The core minimal-tcmalloc allocator test — a self-contained allocation
    # correctness exercise of the library. (gperftools' heap-checker/profiler
    # tests lean on ptrace/timers and are left out of the hermetic scope.)
    test = test_spec(targets = ["//:tcmalloc_minimal_test"], flags = ["-c", "opt"]),
)
