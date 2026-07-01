load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# SystemC — the C++ hardware modeling reference library (accellera-official/systemc).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
SYSTEMC_PROJECT = project_spec(
    name = "systemc",
    source = bcr_module_source(
        module = "systemc",
        version = "3.0.2.bcr.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@systemc//..."], flags = ["-c", "opt"]),
)
