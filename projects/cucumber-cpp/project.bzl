load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# cucumber-cpp — BDD step definitions for C++ (cucumber/cucumber-cpp).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
CUCUMBER_CPP_PROJECT = project_spec(
    name = "cucumber-cpp",
    source = bcr_module_source(
        module = "cucumber-cpp",
        version = "0.8.0.bcr.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@cucumber-cpp//..."], flags = ["-c", "opt"]),
)
