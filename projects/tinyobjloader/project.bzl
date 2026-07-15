load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/tinyobjloader/tinyobjloader
# Description: Tiny but powerful single file wavefront obj loader
#
# TODO: add tinyobjloader_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "tinyobjloader_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
TINYOBJLOADER_PROJECT = project_spec(
    name = "tinyobjloader",
    source = tarball_source(
        archive = "@tinyobjloader_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
