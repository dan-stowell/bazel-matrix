load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# FFTW3 — the Fastest Fourier Transform in the West, C (FFTW/fftw3).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
FFTW_PROJECT = project_spec(
    name = "fftw",
    source = bcr_module_source(
        module = "fftw",
        version = "3.3.10",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@fftw//:bench_double"], flags = ["-c", "opt"]),
)
