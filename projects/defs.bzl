"""`runner_project` — per-project "build it as it is" targets.

Each museum project gets a //projects/<project> package whose `:build` and
`:test` targets run the project's *upstream* build/test (its pinned source, its
own MODULE/BUILD, no overlays, no injected toolchain) inside the //runner/image
container via //projects:run.sh. The pinned crun binary and image OCI layout are
ordinary runfiles/data dependencies of each runner:

    bazel build //runner/image:oci_layout   # optional prebuild
    bazel run //projects/cpu_features:build        # runner image
    bazel run //projects/cpu_features:local_build  # host-local tools

`version` is the project's known-good Bazel (bazelisk pins it via
USE_BAZEL_VERSION); "-" lets bazelisk honor the repo's own .bazelversion.
"""

load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

def runner_project(name, version = "-", build = None, test = None):
    """Generate :build and/or :test runners for one project.

    Args:
        name: the archive key in //tools/fetch:extension.bzl (e.g. "cpu_features").
        version: known-good Bazel version, or "-" to let bazelisk decide.
        build: upstream build target labels (omit/empty to skip the :build target).
        test: upstream test target labels (omit/empty to skip the :test target).
    """
    for goal, targets in [("build", build), ("test", test)]:
        if targets:
            sh_binary(
                name = goal,
                srcs = ["//projects:run.sh"],
                args = [name, version, goal] + targets,
                data = [
                    "//runner/image:crun",
                    "//runner/image:oci_layout",
                ],
                # docker run reaches the network and isn't sandboxable; keep
                # these out of `bazel build //...` wildcards.
                tags = ["manual", "no-sandbox", "requires-network"],
                visibility = ["//visibility:public"],
            )

            sh_binary(
                name = "local_" + goal,
                srcs = ["//projects:run.sh"],
                args = [name, version, "local_" + goal] + targets,
                # Host-local runs reach the network and intentionally use host
                # tools, so keep them out of wildcard builds as well.
                tags = ["manual", "no-sandbox", "requires-network"],
                visibility = ["//visibility:public"],
            )
