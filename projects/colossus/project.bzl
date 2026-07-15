load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

# Candidate discovered by //pipeline:next_candidates.
# Upstream: https://github.com/lucperkins/colossus
# Description: An example microservice architecture for Kubernetes using Bazel, Go, Java, Docker, Kubernetes, Minikube, Gazelle, gRPC, Prometheus, Grafana, and more.
#
# TODO: add colossus_archive to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
# TODO: add "colossus_archive" to the project_sources use_repo() call in MODULE.bazel.
# TODO: replace strip_prefix with the archive's top-level directory.
# TODO: narrow the build targets once the project loads successfully.
COLOSSUS_PROJECT = project_spec(
    name = "colossus",
    source = tarball_source(
        archive = "@colossus_archive//file",
        strip_prefix = "TODO",
    ),
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//..."]),
)
