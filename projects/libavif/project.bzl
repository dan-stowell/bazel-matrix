load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libavif — AVIF image codec in C (AOMediaCodec/libavif).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
LIBAVIF_PROJECT = project_spec(
    name = "libavif",
    source = bcr_module_source(
        module = "libavif",
        version = "1.4.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libavif//..."], flags = ["-c", "opt"]),
)
