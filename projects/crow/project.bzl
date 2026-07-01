load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# Crow — a header-only C++ microframework for building web services and APIs.
# Source pinned in //kiss:extension.bzl (@crow_archive, release v1.3.2).
# First-party Bazel: pulls asio, zlib and catch2 from the BCR. Its root BUILD
# calls cc_library unloaded, so it runs on the Bazel 8.7 inner with the hermetic
# LLVM toolchain. Crow's Bazel cc_test exercises the SSL path through Asio,
# BoringSSL, Catch2, and the OpenSSL CLI. PLATFORMS_DEP supplies @platforms
# visibility for the injected RBE platform (Crow's MODULE declares no direct
# platforms dep).
#
#   bazel run //projects/crow:build_local_linux_amd64
CROW_PROJECT = project_spec(
    name = "crow",
    source = tarball_source(
        archive = "@crow_archive//file",
        strip_prefix = "Crow-1.3.2",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, MINIMG],
    # The Crow header library (interface target over asio).
    build = build_spec(targets = ["//:crow"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//tests/ssl:ssltest"], flags = ["-c", "opt"]),
)
