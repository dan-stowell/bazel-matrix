load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# zstd — Zstandard fast compression in C (facebook/zstd).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic not wired: reach for it only when needed.)
ZSTD_PROJECT = project_spec(
    name = "zstd",
    source = bcr_module_source(
        module = "zstd",
        version = "1.5.7.bcr.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@zstd//:fullbench"], flags = ["-c", "opt"]),
)
