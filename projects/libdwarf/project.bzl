load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# libdwarf — DWARF debug-info reader library in C (davea42/libdwarf-code).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier on LOCAL +
# the full CI image (CIIMG) with the ambient toolchain — no hermetic LLVM.
LIBDWARF_PROJECT = project_spec(
    name = "libdwarf",
    source = bcr_module_source(
        module = "libdwarf",
        version = "2.2.0.bcr.1",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@libdwarf//..."], flags = ["-c", "opt"]),
)
