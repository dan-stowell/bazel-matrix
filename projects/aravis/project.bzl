load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# Aravis — GigE/USB3 Vision camera library in C (AravisProject/aravis).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
ARAVIS_PROJECT = project_spec(
    name = "aravis",
    source = bcr_module_source(
        module = "aravis",
        version = "0.9.2-20251111063445-57983d013883",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@aravis//tests/..."], flags = ["-c", "opt"]),
)
