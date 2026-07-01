load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# prometheus-cpp — the Prometheus metrics client library for C++. Source pinned
# in //kiss:extension.bzl (@prometheus_cpp_archive, v1.3.0). First-party
# Bazel; its BUILD files call cc_* unloaded, so it runs on the 8.7 inner.
# The hermetic LLVM modification lives in //projects/prometheus_cpp/hermetic_llvm.
# We build the core library and run its unit tests; the //pull
# exposer's integration tests stand up a live HTTP server, so they're left out.
# prometheus-cpp's MODULE declares a direct platforms dep (no PLATFORMS_DEP).
#
PROMETHEUS_CPP_PROJECT = project_spec(
    name = "prometheus_cpp",
    source = tarball_source(
        archive = "@prometheus_cpp_archive//file",
        strip_prefix = "prometheus-cpp-1.3.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//core:core"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//core/tests:unit"], flags = ["-c", "opt"]),
)
