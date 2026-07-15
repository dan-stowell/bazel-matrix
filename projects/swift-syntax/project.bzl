load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/swiftlang/swift-syntax
# Description: A set of Swift libraries for parsing, inspecting, generating, and transforming Swift source code.
#
# TODO: add swift_syntax_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "swift_syntax_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
SWIFT_SYNTAX_PROJECT = project_spec(
    name = "swift-syntax",
    source = tarball_source(
        archive = "@swift_syntax_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
