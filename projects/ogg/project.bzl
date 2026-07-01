load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libogg — the Ogg multimedia container library in C (xiph/ogg).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
OGG_PROJECT = project_spec(
    name = "ogg",
    source = bcr_module_source(
        module = "ogg",
        version = "1.3.5.bcr.3",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@ogg//:bitwise_test"], flags = ["-c", "opt"]),
)
