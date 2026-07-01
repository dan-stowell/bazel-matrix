load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# tinyformat — type-safe printf-style C++ string formatting (c42f/tinyformat).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
TINYFORMAT_PROJECT = project_spec(
    name = "tinyformat",
    source = bcr_module_source(
        module = "tinyformat",
        version = "2.3.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@tinyformat//:tinyformat_test"], flags = ["-c", "opt"]),
)
