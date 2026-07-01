load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# FTXUI — a functional C++ terminal-UI library (screen / dom / component).
# Source pinned in //kiss:extension.bzl (@ftxui_archive, release v7.0.0),
# built from the upstream source/module as-is. The hermetic LLVM modification
# lives in //projects/ftxui/hermetic_llvm. FTXUI ships first-party Bazel
# files, but its test target pulls in googletest (cc_* unloaded), so it runs on
# the Bazel 8.7 inner like the other googletest-consuming C++ projects. (It
# declares a direct `platforms` dep, so no PLATFORMS_DEP overlay is needed.)
#
FTXUI_PROJECT = project_spec(
    name = "ftxui",
    source = tarball_source(
        archive = "@ftxui_archive//file",
        strip_prefix = "FTXUI-7.0.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:ftxui"], flags = ["-c", "opt"]),
    # FTXUI's monolithic self-test (//:tests) — the screen/dom/component unit
    # tests, which render to in-memory buffers (no real TTY needed).
    test = test_spec(targets = ["//:tests"], flags = ["-c", "opt"]),
)
