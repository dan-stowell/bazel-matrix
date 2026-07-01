load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# LCM (Lightweight Communications and Marshalling) — a low-latency message-passing
# and data-marshalling system widely used in robotics. Source pinned in
# //kiss:extension.bzl (@lcm_archive, v1.5.2). First-party Bazel, run on
# the 8.7 inner. The hermetic LLVM modification lives in //projects/lcm/hermetic_llvm.
# We build the static C++ library
# and run a C++ unit test. LCM's MODULE declares a direct platforms dep (no
# PLATFORMS_DEP).
#
LCM_PROJECT = project_spec(
    name = "lcm",
    source = tarball_source(
        archive = "@lcm_archive//file",
        strip_prefix = "lcm-1.5.2",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//lcm:lcm-static"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//test/cpp:memq_test"], flags = ["-c", "opt"]),
)
