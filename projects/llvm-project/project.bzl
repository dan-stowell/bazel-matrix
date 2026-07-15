load("//bazel_runner:defs.bzl", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# LLVM — the LLVM compiler infrastructure project, C++ (llvm/llvm-project). A "BCR
# module" project: the runner bazel_dep()s llvm-project from the Bazel Central
# Registry and runs a scoped set of its own unit tests. Host tier on LOCAL + the
# LOCAL with the ambient toolchain — no hermetic LLVM. Pinned to
# BCR 17.0.4.bcr.1.
#
# The BCR module exposes 32 aggregate tests in llvm/unittests. Their configured
# dependency closure is only modestly larger than the former five-target subset,
# so run the complete package. Disable optional libpfm support because the BCR
# module does not declare an @pfm repository; LLVM's default "external" setting
# otherwise leaves the full suite unloadable.
LLVM_PROJECT_PROJECT = project_spec(
    name = "llvm-project",
    source = bcr_module_source(
        module = "llvm-project",
        version = "17.0.4.bcr.1",
    ),
    environments = [LOCAL],
    test = test_spec(
        targets = ["@llvm-project//llvm/unittests:all"],
        flags = [
            "-c",
            "opt",
            "--@llvm-project//llvm:pfm=disable",
        ],
    ),
)
