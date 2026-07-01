load("//kiss:defs.bzl", "ACTIOND", "HERMETIC_LLVM", "LOCAL", "MINIMG", "RBE", "RULES_RUST_SYSROOT_FIX", "build_spec", "project_spec", "tarball_source", "test_spec")
# cxx (cxx.rs) — safe FFI between Rust and C++. Build #3: exercises the Rust
# toolchain (rules_rust + hermetic rustc) plus, via the C++ bridge, the
# hermetic LLVM toolchain. Source pinned at tag 1.0.194.
#
#   bazel run //projects/cxx:build_local_darwin_arm64
#   bazel run //projects/cxx:test_rbe_linux_amd64
CXX_PROJECT = project_spec(
    name = "cxx",
    source = tarball_source(
        archive = "@cxx_archive//file",
        strip_prefix = "cxx-1.0.194",
    ),
    toolchains = [HERMETIC_LLVM, RULES_RUST_SYSROOT_FIX],
    environments = [LOCAL, RBE, ACTIOND, MINIMG],
    build = build_spec(targets = ["//:cxx", "//:core"]),
    test = test_spec(targets = ["//..."]),
)
