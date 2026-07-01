load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# SDL2 — Simple DirectMedia Layer (libsdl-org/SDL).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic not wired: reach for it only when needed.)
SDL2_PROJECT = project_spec(
    name = "sdl2",
    source = bcr_module_source(
        module = "sdl2",
        version = "2.32.0.bcr.beta.6",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@sdl2//:sdl2_headers_consumer_compile_test"], flags = ["-c", "opt"]),
)
