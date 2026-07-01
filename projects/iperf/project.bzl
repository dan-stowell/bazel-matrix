load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# iperf3 — network throughput measurement in C (esnet/iperf).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic not wired: reach for it only when needed.)
IPERF_PROJECT = project_spec(
    name = "iperf",
    source = bcr_module_source(
        module = "iperf",
        version = "3.18.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@iperf//..."], flags = ["-c", "opt"]),
)
