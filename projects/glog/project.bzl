load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# glog — Google's C++ application-level logging library.
# Source pinned in //kiss:extension.bzl (@glog_archive, release v0.7.1),
# built with the fully-hermetic LLVM toolchain. Its Bazel BUILD uses the
# unloaded cc_* rules, so it runs on the Bazel 8.7 inner; PLATFORMS_DEP supplies
# the @platforms visibility the injected RBE platform package needs (glog's
# MODULE declares no platforms dep). gflags comes from glog's own MODULE dep
# (pulled from the BCR by the inner Bazel).
#
# glog's exhaustive unit tests are CMake-driven and not exposed as Bazel
# cc_test; its only Bazel test is //bazel/example:main, a smoke test that links
# against glog and exercises LOG/CHECK at runtime — honest build+link+run parity
# (see [[test-wiring-preference]]).
#
#   bazel run //projects/glog:build_local_linux_amd64
#   bazel run //projects/glog:test_local_linux_amd64
GLOG_PROJECT = project_spec(
    name = "glog",
    source = tarball_source(
        archive = "@glog_archive//file",
        strip_prefix = "glog-0.7.1",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//:glog"], flags = ["-c", "opt"]),
    # glog's exhaustive unit tests are CMake-only, but upstream does provide a
    # Bazel smoke test that links glog with gflags and exercises LOG/CHECK.
    test = test_spec(targets = ["//bazel/example:main"], flags = ["-c", "opt"]),
)
