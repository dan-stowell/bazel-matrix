"""`museum_build`: declare an isolated, daemonless inner Bazel build of a project.

Each invocation creates a `bazel run`-nable target that builds the given project
from its pinned source tarball using a pinned inner Bazel, fully isolated from
the host (see //tools/buildrunner/runner.py for what isolation means here).

Example:

    load("//builds:defs.bzl", "museum_build")

    museum_build(
        name = "build",
        source_archive = "@absl_archive//file",
        strip_prefix = "abseil-cpp-20260526.0",
        targets = ["//absl/..."],
        build_flags = ["-c", "opt"],
    )

    # then: bazel run //builds/abseil_cpp:build
    #       bazel run //builds/abseil_cpp:build -- //absl/strings/...   (override targets)
"""

load("@rules_python//python:defs.bzl", "py_binary")

# Per-CPU selection of the pinned inner Bazel binary (data dep + runfiles path).
_INNER_BAZEL_DATA = select({
    "@platforms//cpu:x86_64": ["@inner_bazel_linux_amd64//file"],
    "@platforms//cpu:arm64": ["@inner_bazel_linux_arm64//file"],
})
_INNER_BAZEL_ARG = select({
    "@platforms//cpu:x86_64": ["--bazel=$(rlocationpath @inner_bazel_linux_amd64//file)"],
    "@platforms//cpu:arm64": ["--bazel=$(rlocationpath @inner_bazel_linux_arm64//file)"],
})

def museum_build(
        name,
        source_archive,
        targets,
        strip_prefix = "",
        build_flags = [],
        visibility = ["//visibility:public"]):
    """Create a `bazel run`-nable isolated inner build target.

    Args:
      name: target name (typically "build").
      source_archive: label of the pinned source tarball (e.g. "@absl_archive//file").
      targets: list of inner build targets (e.g. ["//absl/..."]).
      strip_prefix: top-level directory inside the tarball to treat as the
        workspace root.
      build_flags: flags forwarded to the inner `bazel build`.
      visibility: target visibility.
    """
    # Unique per-project build root, derived from the package path so two
    # projects' targets (often both named "build") don't share caches.
    project_id = (native.package_name().replace("/", "_") or name)

    fixed_args = [
        "--name=" + project_id,
        "--source-archive=$(rlocationpath {})".format(source_archive),
    ]
    if strip_prefix:
        fixed_args.append("--strip-prefix=" + strip_prefix)
    for flag in build_flags:
        fixed_args.append("--build-flag=" + flag)
    for target in targets:
        fixed_args.append("--target=" + target)

    py_binary(
        name = name,
        srcs = ["//tools/buildrunner:runner.py"],
        main = "runner.py",
        deps = ["@rules_python//python/runfiles"],
        data = [source_archive] + _INNER_BAZEL_DATA,
        args = fixed_args + _INNER_BAZEL_ARG,
        visibility = visibility,
    )
