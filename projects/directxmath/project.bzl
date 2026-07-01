load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# DirectXMath — SIMD linear-algebra library in C++ (microsoft/DirectXMath).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
DIRECTXMATH_PROJECT = project_spec(
    name = "directxmath",
    source = bcr_module_source(
        module = "directxmath",
        version = "3.20",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@directxmath//..."], flags = ["-c", "opt"]),
)
