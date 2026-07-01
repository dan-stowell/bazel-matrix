load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# TRLC — Treat Requirements Like Code, a requirements DSL (bmw-software-engineering/trlc).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier on LOCAL +
# the full CI image (CIIMG) with the ambient toolchain — no hermetic LLVM.
TRLC_PROJECT = project_spec(
    name = "trlc",
    source = bcr_module_source(
        module = "trlc",
        version = "2.0.5",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@trlc//api-examples/..."], flags = ["-c", "opt"]),
)
