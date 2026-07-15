load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/tensorflow/serving
# Description: A flexible, high-performance serving system for machine learning models
#
# TODO: add serving_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "serving_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
SERVING_PROJECT = project_spec(
    name = "serving",
    source = tarball_source(
        archive = "@serving_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
