load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# lexbor — fast HTML/CSS rendering engine in C (lexbor/lexbor).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
LEXBOR_PROJECT = project_spec(
    name = "lexbor",
    source = bcr_module_source(
        module = "lexbor",
        version = "2.4.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@lexbor//:all"], flags = ["-c", "opt"]),
)
