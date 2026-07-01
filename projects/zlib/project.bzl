load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")
# zlib — the ubiquitous DEFLATE compression library (C).
# Source pinned in //kiss:extension.bzl (@zlib_archive, release v1.3.2),
# built from the upstream source/module as-is. The hermetic LLVM modification
# lives in //projects/zlib/hermetic_llvm. zlib ships first-party Bazel files
# (MODULE.bazel + a BUILD that loads rules_cc), so the default 9.1.1 inner
# builds it as-authored.
# Build-only: zlib's BUILD declares the library (//:zlib, an alias to //:z) but
# no Bazel test targets.
ZLIB_PROJECT = project_spec(
    name = "zlib",
    source = tarball_source(
        archive = "@zlib_archive//file",
        strip_prefix = "zlib-1.3.2",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:zlib"], flags = ["-c", "opt"]),
)
