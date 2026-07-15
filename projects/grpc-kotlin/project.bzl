load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/grpc/grpc-kotlin
# Description: Kotlin gRPC implementation. HTTP/2 based RPC
#
# TODO: add grpc_kotlin_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "grpc_kotlin_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
GRPC_KOTLIN_PROJECT = project_spec(
    name = "grpc-kotlin",
    source = tarball_source(
        archive = "@grpc_kotlin_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
