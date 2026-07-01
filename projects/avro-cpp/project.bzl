load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# Apache Avro C++ — data serialization (apache/avro).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
AVRO_CPP_PROJECT = project_spec(
    name = "avro-cpp",
    source = bcr_module_source(
        module = "avro-cpp",
        version = "1.12.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@avro-cpp//:all"], flags = ["-c", "opt"]),
)
