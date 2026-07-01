load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# Verilator — the fast Verilog/SystemVerilog simulator (verilator/verilator).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
VERILATOR_PROJECT = project_spec(
    name = "verilator",
    source = bcr_module_source(
        module = "verilator",
        version = "5.046.bcr.5",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@verilator//..."], flags = ["-c", "opt"]),
)
