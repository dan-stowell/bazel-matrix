load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# iceoryx2 — the Rust rewrite of Eclipse iceoryx: zero-copy, lock-free shared-
# memory inter-process communication. Source pinned in //kiss:extension.bzl
# (@iceoryx2_archive, v0.9.2). First-party Bazel: rules_rust with crate_universe
# (a checked-in Cargo.Bazel.lock pins the crate graph, fetched from crates.io).
# Run on the 8.7 inner; rules_rust downloads its own Rust toolchain. First Rust-
# native project built and tested in the matrix.
#
#   bazel run //projects/iceoryx2:build_local_linux_amd64
#   bazel run //projects/iceoryx2:test_local_linux_amd64
ICEORYX2_PROJECT = project_spec(
    name = "iceoryx2",
    source = tarball_source(
        archive = "@iceoryx2_archive//file",
        strip_prefix = "iceoryx2-0.9.2",
    ),
    toolchains = [HERMETIC_LLVM],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, MINIMG],
    build = build_spec(targets = ["//iceoryx2:iceoryx2"], flags = ["-c", "opt"]),
    test = test_spec(targets = ["//iceoryx2:iceoryx2-tests"], flags = ["-c", "opt"]),
)
