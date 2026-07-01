load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# rules_multirun — Bazel ruleset to run multiple commands (keith/rules_multirun).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier on LOCAL +
# the full CI image (CIIMG) with the ambient toolchain — no hermetic LLVM.
RULES_MULTIRUN_PROJECT = project_spec(
    name = "rules_multirun",
    source = bcr_module_source(
        module = "rules_multirun",
        version = "0.14.0",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@rules_multirun//tests/..."], flags = ["-c", "opt"]),
)
