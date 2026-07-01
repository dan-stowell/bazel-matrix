load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# zziplib — lightweight ZIP archive access in C (gdraheim/zziplib).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier on LOCAL +
# the full CI image (CIIMG) with the ambient toolchain — no hermetic LLVM.
ZZIPLIB_PROJECT = project_spec(
    name = "zziplib",
    source = bcr_module_source(
        module = "zziplib",
        version = "0.13.72",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@zziplib//..."], flags = ["-c", "opt"]),
)
