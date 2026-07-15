load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/tensorflow/tensorflow
# Description: Computation using data flow graphs for scalable machine learning.
#
# TODO: add tensorflow_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "tensorflow_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
TENSORFLOW_PROJECT = project_spec(
    name = "tensorflow",
    source = tarball_source(
        archive = "@tensorflow_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
