load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# double-conversion — Google's library for binary-decimal conversion of IEEE-754
# doubles (the workhorse behind many printf/strtod implementations). Source
# pinned in //kiss:extension.bzl (@double_conversion_archive, v3.4.0).
# First-party Bazel: its root BUILD calls cc_* unloaded, so the 8.7 inner with
# the hermetic LLVM toolchain. PLATFORMS_DEP supplies @platforms for the injected
# RBE platform (its MODULE declares no direct platforms dep).
#
#   bazel run //projects/double_conversion:build_local_linux_amd64
#   bazel run //projects/double_conversion:test_local_linux_amd64
DOUBLE_CONVERSION_PROJECT = project_spec(
    name = "double_conversion",
    source = tarball_source(
        archive = "@double_conversion_archive//file",
        strip_prefix = "double-conversion-3.4.0",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//:double-conversion"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//:cctest"], flags = ["-c", "opt"]),
)
