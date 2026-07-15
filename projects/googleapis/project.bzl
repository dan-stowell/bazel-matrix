load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/googleapis/googleapis
# Description: Public interface definitions of Google APIs.
#
# TODO: add googleapis_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "googleapis_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
GOOGLEAPIS_PROJECT = project_spec(
    name = "googleapis",
    source = tarball_source(
        archive = "@googleapis_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
