load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# cpp-httplib — a single-header C++ HTTP/HTTPS client/server library
# (yhirose/cpp-httplib). A "BCR module" project: the runner bazel_dep()s it from
# the Bazel Central Registry and runs its own @cpp-httplib//... tests (which the
# BCR presubmit builds but does not run). Host tier on LOCAL + the full CI image
# (CIIMG) with the ambient toolchain — no hermetic LLVM.
CPP_HTTPLIB_PROJECT = project_spec(
    name = "cpp-httplib",
    source = bcr_module_source(
        module = "cpp-httplib",
        version = "0.46.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@cpp-httplib//..."], flags = ["-c", "opt"]),
)
