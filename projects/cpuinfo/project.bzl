load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/pytorch/cpuinfo
# Description: CPU INFOrmation library (x86/x86-64/ARM/ARM64, Linux/Windows/Android/macOS/iOS)
#
# TODO: add cpuinfo_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "cpuinfo_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
CPUINFO_PROJECT = project_spec(
    name = "cpuinfo",
    source = tarball_source(
        archive = "@cpuinfo_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
