load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/jpsim/SourceKitten
# Description: An adorable little framework and command line tool for interacting with SourceKit.
#
# TODO: add sourcekitten_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "sourcekitten_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
SOURCEKITTEN_PROJECT = project_spec(
    name = "sourcekitten",
    source = tarball_source(
        archive = "@sourcekitten_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
