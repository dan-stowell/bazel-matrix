load("//kiss:defs.bzl", "ACTIOND", "HERMETIC_LLVM", "LOCAL", "MINIMG", "RBE", "build_spec", "overlay", "project_spec", "tarball_source")
# Brotli — Google's compression library + CLI.
# Source pinned in //kiss:extension.bzl (@brotli_archive, v1.2.0). The
# release tarball ships BUILD files but no MODULE.bazel (its in-tree build is
# WORKSPACE-based), so we inject the canonical module() declaration. Built on
# the Bazel 8.7 inner: brotli's BUILD calls cc_library unloaded, which Bazel 8.7
# autoloads (Bazel 9 removed that) — and 8.7 carries hermetic-llvm.
#
# This target (the C library + CLI) has no cc_test rules — brotli's C tests are
# CMake/CTest roundtrips. Its only *Bazel* tests are the go_test rules in the
# nested go/ module, which exercise this C library through cgo; those are wired
# up separately as //projects/brotli_go (see that package).
#
# BROTLI_MODULE must precede HERMETIC_LLVM so module() is the first statement in
# the synthesized MODULE.bazel (the toolchain block is appended after it).
BROTLI_MODULE = overlay(
    name = "brotli_module",
    appends = [("//projects/brotli:module.MODULE.bazel", "MODULE.bazel")],
)

#   bazel run //projects/brotli:build_local_linux_amd64
BROTLI_PROJECT = project_spec(
    name = "brotli",
    source = tarball_source(
        archive = "@brotli_archive//file",
        strip_prefix = "brotli-1.2.0",
    ),
    toolchains = [BROTLI_MODULE, HERMETIC_LLVM],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, ACTIOND, MINIMG],
    build = build_spec(targets = ["//:brotli", "//:brotlienc", "//:brotlidec"], flags = ["-c", "opt"]),
)
