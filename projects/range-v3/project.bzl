load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/ericniebler/range-v3
# Description: Range library for C++14/17/20, basis for C++20's std::ranges
#
# TODO: add range_v3_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "range_v3_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
RANGE_V3_PROJECT = project_spec(
    name = "range-v3",
    source = tarball_source(
        archive = "@range_v3_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
