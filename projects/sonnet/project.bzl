load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/google-deepmind/sonnet
# Description: TensorFlow-based neural network library
#
# TODO: add sonnet_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "sonnet_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
SONNET_PROJECT = project_spec(
    name = "sonnet",
    source = tarball_source(
        archive = "@sonnet_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
