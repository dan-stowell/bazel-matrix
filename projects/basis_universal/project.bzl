load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# Basis Universal — GPU texture transcoder in C++ (BinomialLLC/basis_universal).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
BASIS_UNIVERSAL_PROJECT = project_spec(
    name = "basis_universal",
    source = bcr_module_source(
        module = "basis_universal",
        version = "2.0.3",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@basis_universal//..."], flags = ["-c", "opt"]),
)
