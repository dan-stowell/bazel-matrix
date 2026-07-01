load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# marisa-trie — matching-and-recursive trie in C++ (s-yata/marisa-trie).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
MARISA_TRIE_PROJECT = project_spec(
    name = "marisa-trie",
    source = bcr_module_source(
        module = "marisa-trie",
        version = "0.3.1.bcr.2",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@marisa-trie//:base-test"], flags = ["-c", "opt"]),
)
