load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# CityHash — string hash functions in C++ (google/cityhash).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
CITYHASH_PROJECT = project_spec(
    name = "cityhash",
    source = bcr_module_source(
        module = "cityhash",
        version = "1.1.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@cityhash//:all"], flags = ["-c", "opt"]),
)
