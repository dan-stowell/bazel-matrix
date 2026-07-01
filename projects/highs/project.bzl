load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# HiGHS — a high-performance solver for large-scale linear programming, mixed-
# integer programming and quadratic programming (C++). Source pinned in
# //kiss:extension.bzl (@highs_archive, v1.14.0). First-party Bazel: its
# root BUILD loads cc_* from rules_cc, so the 9.1.1 inner with the hermetic LLVM
# toolchain. PLATFORMS_DEP supplies @platforms for the RBE platform.
#
#   bazel run //projects/highs:build_local_linux_amd64
#   bazel run //projects/highs:test_local_linux_amd64
HIGHS_PROJECT = project_spec(
    name = "highs",
    source = tarball_source(
        archive = "@highs_archive//file",
        strip_prefix = "HiGHS-1.14.0",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "9.1.1",
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//:highs"], flags = ["-c", "opt"]),
    # A couple of the generated check/*.cpp unit tests (the full set is large).
    test = test_spec(targets = ["//:TestThrow", "//:TestSpecialLps"], flags = ["-c", "opt"]),
)
