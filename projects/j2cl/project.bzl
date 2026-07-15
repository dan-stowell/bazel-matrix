load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/google/j2cl
# Description: Java to Closure JavaScript transpiler
#
# TODO: add j2cl_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "j2cl_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
J2CL_PROJECT = project_spec(
    name = "j2cl",
    source = tarball_source(
        archive = "@j2cl_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
