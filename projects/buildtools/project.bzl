load("//kiss:defs.bzl", "HERMETIC_LLVM", "LOCAL", "MINIMG", "PLATFORMS_DEP", "RBE", "build_spec", "project_spec", "tarball_source", "test_spec")
# buildtools — Bazel's own BUILD/Starlark file tooling (buildifier, buildozer),
# written in Go. Source pinned in //kiss:extension.bzl (@buildtools_archive,
# release v7.3.1). Built with rules_go: the Go SDK is downloaded hermetically by
# rules_go, and a C toolchain (HERMETIC_LLVM) is registered for the rules_go
# stdlib even though buildifier itself is pure Go (no cgo). Its older
# aspect_rules_js / rules_nodejs deps use Bazel-9-removed APIs, so it runs on the
# Bazel 8.7 inner. PLATFORMS_DEP supplies @platforms visibility for the injected
# RBE platform package (buildtools' MODULE declares no direct platforms dep).
#
#   bazel run //projects/buildtools:build_local_linux_amd64
#   bazel run //projects/buildtools:test_local_linux_amd64
BUILDTOOLS_PROJECT = project_spec(
    name = "buildtools",
    source = tarball_source(
        archive = "@buildtools_archive//file",
        strip_prefix = "buildtools-7.3.1",
    ),
    toolchains = [HERMETIC_LLVM, PLATFORMS_DEP],
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE, MINIMG],
    # buildifier itself (the canonical Bazel file formatter), a pure-Go binary.
    build = build_spec(targets = ["//buildifier:buildifier"], flags = ["-c", "opt"]),
    # The pure-Go unit tests for the build-file parser/printer, the buildozer
    # edit engine, the linter warnings, the rule tables and the workspace logic.
    test = test_spec(
        targets = [
            "//build:build_test",
            "//edit:edit_test",
            "//warn:warn_test",
            "//tables:tables_test",
            "//wspace:wspace_test",
        ],
        flags = ["-c", "opt"],
    ),
)
