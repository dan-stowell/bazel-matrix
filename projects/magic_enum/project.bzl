load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# magic_enum — static reflection (to-string, iteration, …) for C++ enums.
# Source pinned in //kiss:extension.bzl (@magic_enum_archive, v0.9.8),
# built with the fully-hermetic LLVM toolchain.
#
# magic_enum is header-only, so its parity is the test suite. Those tests live in
# a *nested* Bazel module at magic_enum-0.9.8/test (test/MODULE.bazel, module
# "magic_enum_tests") that consumes the library as an external dep:
#     bazel_dep(name = "magic_enum"); local_path_override(... path = "..")
# i.e. it builds magic_enum from the parent dir (whose MODULE.bazel the tarball
# ships). So we extract the full archive root and run inner Bazel from test/.
# The tests vendor a Catch2 single-header (in 3rdparty/), so no BCR Catch2 is
# needed. HERMETIC_LLVM + PLATFORMS_DEP are appended to the test module (it
# declares neither llvm nor platforms, the latter required by the injected RBE
# platform package).
#
#   bazel run //projects/magic_enum:test_local_linux_amd64
MAGIC_ENUM_PROJECT = project_spec(
    name = "magic_enum",
    source = tarball_source(
        archive = "@magic_enum_archive//file",
        strip_prefix = "magic_enum-0.9.8",
        source_subdir = "test",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    environments = [LOCAL, RBE, MINIMG],
    # The two wired cc_tests (test, test_flags) — building them compiles real
    # magic_enum usage through the vendored Catch2 (the library itself is
    # header-only, so this is where the toolchain actually exercises it).
    build = build_spec(targets = ["//..."], flags = ["--build_tests_only", "-c", "opt"]),
    test = test_spec(targets = ["//..."], flags = ["-c", "opt"]),
)
