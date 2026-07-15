load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/GoogleContainerTools/container-structure-test
# Description: validate the structure of your container images
#
# TODO: add container_structure_test_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "container_structure_test_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
CONTAINER_STRUCTURE_TEST_PROJECT = project_spec(
    name = "container-structure-test",
    source = tarball_source(
        archive = "@container_structure_test_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
