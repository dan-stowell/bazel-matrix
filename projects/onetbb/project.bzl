load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# oneTBB — Intel's oneAPI Threading Building Blocks, a C++ parallelism library.
# Source pinned in //kiss:extension.bzl (@onetbb_archive, release
# v2022.0.0), built from the upstream source/module as-is. The hermetic LLVM
# modification lives in //projects/onetbb/hermetic_llvm. Its Bazel BUILD uses
# the unloaded cc_* rules, so it runs on the Bazel 8.7 inner. (oneTBB declares
# the platforms dep directly, so no PLATFORMS_DEP.)
#
ONETBB_PROJECT = project_spec(
    name = "onetbb",
    source = tarball_source(
        archive = "@onetbb_archive//file",
        strip_prefix = "oneTBB-2022.0.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:tbb"], flags = ["-c", "opt"]),
    # The four upstream Bazel tests, exercising the mutex, parallel_for,
    # parallel_reduce and task scheduling paths against the built library.
    test = test_spec(
        targets = [
            "//:test_mutex",
            "//:test_parallel_for",
            "//:test_parallel_reduce",
            "//:test_task",
        ],
        flags = ["-c", "opt"],
    ),
)
