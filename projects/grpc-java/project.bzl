load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/grpc/grpc-java
# Description: The Java gRPC implementation. HTTP/2 based RPC
#
# TODO: add grpc_java_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "grpc_java_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
GRPC_JAVA_PROJECT = project_spec(
    name = "grpc-java",
    source = tarball_source(
        archive = "@grpc_java_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
