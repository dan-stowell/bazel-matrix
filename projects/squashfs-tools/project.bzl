load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# squashfs-tools — squashfs filesystem tools in C (plougher/squashfs-tools).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
SQUASHFS_TOOLS_PROJECT = project_spec(
    name = "squashfs-tools",
    source = bcr_module_source(
        module = "squashfs-tools",
        version = "4.7.5",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@squashfs-tools//..."], flags = ["-c", "opt"]),
)
