load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libpcap — the C packet-capture library (the-tcpdump-group/libpcap).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
LIBPCAP_PROJECT = project_spec(
    name = "libpcap",
    source = bcr_module_source(
        module = "libpcap",
        version = "1.10.5.bcr.3",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libpcap//..."], flags = ["-c", "opt"]),
)
