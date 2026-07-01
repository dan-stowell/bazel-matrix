load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# ExprTk — C++ mathematical expression parsing/evaluation (ArashPartow/exprtk).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
EXPRTK_PROJECT = project_spec(
    name = "exprtk",
    source = bcr_module_source(
        module = "exprtk",
        version = "0.0.3.bcr.1",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@exprtk//:exprtk_test"], flags = ["-c", "opt"]),
)
