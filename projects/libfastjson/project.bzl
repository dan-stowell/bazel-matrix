load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libfastjson — fast JSON parsing C library (rsyslog/libfastjson).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier on LOCAL +
# the full CI image (CIIMG) with the ambient toolchain — no hermetic LLVM.
LIBFASTJSON_PROJECT = project_spec(
    name = "libfastjson",
    source = bcr_module_source(
        module = "libfastjson",
        version = "1.2304.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libfastjson//..."], flags = ["-c", "opt"]),
)
