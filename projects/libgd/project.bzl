load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libgd — the GD graphics/image C library (libgd/libgd).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
LIBGD_PROJECT = project_spec(
    name = "libgd",
    source = bcr_module_source(
        module = "libgd",
        version = "2.3.3",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libgd//..."], flags = ["-c", "opt"]),
)
