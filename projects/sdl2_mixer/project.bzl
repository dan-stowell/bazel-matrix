load("//kiss:defs.bzl", "CIIMG", "LOCAL", "bcr_module_source", "project_spec", "test_spec")
# SDL2_mixer — audio mixer for SDL2 (libsdl-org/SDL_mixer).
# A "BCR module" project: the runner bazel_dep()s the module from the Bazel
# Central Registry and runs its own presubmit test target. Host tier: builds and
# tests with the ambient toolchain on LOCAL and in the full CI image (CIIMG) — no
# hermetic LLVM. (RBE/hermetic reached for only when needed.)
SDL2_MIXER_PROJECT = project_spec(
    name = "sdl2_mixer",
    source = bcr_module_source(
        module = "sdl2_mixer",
        version = "2.8.1.bcr.beta.2",
    ),
    environments = [LOCAL, CIIMG],
    test = test_spec(targets = ["@sdl2_mixer//:sdl2_mixer_headers_consumer_compile_test"], flags = ["-c", "opt"]),
)
