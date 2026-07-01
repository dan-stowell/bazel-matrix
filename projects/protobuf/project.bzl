load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# Protocol Buffers — the matrix's marquee first-party Bazel C++ project.
# Source pinned in //kiss:extension.bzl (@protobuf_archive, the v35.1
# Bazel source dist), built from the upstream source/module as-is. The hermetic
# LLVM modification lives in //projects/protobuf/hermetic_llvm. It pulls
# abseil-cpp / rules_cc / zlib from the BCR via the inner Bazel.
#
PROTOBUF_PROJECT = project_spec(
    name = "protobuf",
    source = tarball_source(
        archive = "@protobuf_archive//file",
        strip_prefix = "protobuf-35.1",
    ),
    environments = [LOCAL, RBE],
    # The iconic artifacts: the protoc compiler and the C++ runtime library.
    build = build_spec(targets = ["//:protoc", "//:protobuf"], flags = ["-c", "opt"]),
    # The C++ runtime test tree. Other language bindings (Java/Python/Ruby/
    # Rust/Kotlin/upb) live elsewhere in the repo and need their own toolchains,
    # so we scope tests to the C++ core for now.
    test = test_spec(targets = ["//src/google/protobuf/..."]),
)
