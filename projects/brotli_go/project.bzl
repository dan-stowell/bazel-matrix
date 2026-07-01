load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "build_spec", "overlay", "project_spec", "tarball_source", "test_spec")
# brotli's Bazel tests — its go bindings. The C library (built by //projects/brotli)
# ships no cc_test rules; brotli's only Bazel test targets are the go_test rules
# in the nested module at brotli-1.2.0/go (go/MODULE.bazel, module "brotli_go"):
#   * //brotli:{brotli_test,synth_test}  — the pure-Go decoder
#   * //cbrotli:{cbrotli_test,synth_test} — the cgo wrapper, which compiles and
#     links the C encoder/decoder we build, exercising it round-trip.
# So this is a faithful test of brotli's compression, just reached through Go.
#
# The go module pulls the C library with `local_path_override(path = "..")`, i.e.
# it expects the parent dir (the C sources) to be a Bazel module. The release
# tarball has no MODULE.bazel there, so BROTLI_GO_PARENT writes one to
# ../MODULE.bazel. The Go SDK is downloaded hermetically by rules_go (already a
# bazel_dep in go/MODULE.bazel); cgo compiles the C with the same zero-sysroot
# hermetic LLVM toolchain (registered here via HERMETIC_LLVM, appended to the go
# module). Built on the Bazel 8.7 inner like the C build.
#
# The cgo tests link Go runtime objects (which carry text relocations) through
# the hermetic toolchain's lld, which rejects them by default ("relocation
# R_X86_64_64 ... recompile with -fPIC"). -Wl,-z,notext lets lld emit the text
# relocations, exactly as gold/bfd do; the resulting test binaries run fine.
#
#   bazel run //projects/brotli_go:test_local_linux_amd64   # 4/4 go tests
BROTLI_GO_PARENT = overlay(
    name = "brotli_go_parent",
    writes = [("//projects/brotli_go:parent.MODULE.bazel", "MODULE.bazel")],
)

BROTLI_GO_PROJECT = project_spec(
    name = "brotli_go",
    source = tarball_source(
        archive = "@brotli_archive//file",
        strip_prefix = "brotli-1.2.0",
        source_subdir = "go",
    ),
    toolchains = [HERMETIC_LLVM, BROTLI_GO_PARENT],
    bazel_version = "8.7.0",
    environments = [LOCAL, MINIMG],
    build = build_spec(
        targets = ["//..."],
        flags = ["-c", "opt", "--linkopt=-Wl,-z,notext"],
    ),
    test = test_spec(
        targets = ["//..."],
        flags = ["-c", "opt", "--linkopt=-Wl,-z,notext"],
    ),
)
