load("//kiss:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")
# quill — an asynchronous, low-latency C++ logging library. Source pinned in
# //kiss:extension.bzl (@quill_archive, release v12.0.0). First-party
# Bazel (bzlmod): its root BUILD calls cc_library unloaded, so it runs on the
# Bazel 8.7 inner. The hermetic LLVM modification lives in
# //projects/quill/hermetic_llvm. No upstream Bazel test
# target, so this is a build-only project. quill's MODULE declares a direct
# platforms dep, so no PLATFORMS_DEP overlay.
#
QUILL_PROJECT = project_spec(
    name = "quill",
    source = tarball_source(
        archive = "@quill_archive//file",
        strip_prefix = "quill-12.0.0",
    ),
    bazel_version = "8.7.0",
    environments = [LOCAL, RBE],
    build = build_spec(targets = ["//:quill"], flags = ["-c", "opt"]),
)
