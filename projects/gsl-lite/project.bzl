load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# gsl-lite — C++ Guidelines Support Library (gsl-lite/gsl-lite).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
GSL_LITE_PROJECT = project_spec(
    name = "gsl-lite",
    source = bcr_module_source(
        module = "gsl-lite",
        version = "1.1.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@gsl-lite//..."], flags = ["-c", "opt"]),
)
