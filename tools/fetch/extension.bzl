"""Module extensions that fetch hermetic, pinned build inputs.

Two extensions:

* `inner_bazel` — the Bazel binary used to run the *inner* project builds. We
  pin a specific release (version + sha256) and download the official binary,
  rather than depending on a host-installed bazel/bazelisk. linux amd64 + arm64.

* `project_sources` — source tarballs of the museum's projects, pinned by
  sha256. This is the kickoff's "project source code as a dep in MODULE.bazel":
  each project's source is an immutable, content-addressed input. We fetch the
  tarball as an opaque file (http_file) so the *outer* Bazel never parses the
  project's own BUILD files — the inner Bazel does that, against an extracted
  copy.
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")

# --- Inner Bazel binary ----------------------------------------------------

INNER_BAZEL_VERSION = "9.1.1"

# repo suffix -> (release arch tag, sha256 of the binary)
_INNER_BAZEL = {
    "linux_amd64": ("linux-x86_64", "857bed5d2756b4d998d3caebf2d941d13d434c4eda4b1d6d7dda205736c25a93"),
    "linux_arm64": ("linux-arm64", "82d1163884e45a6a7ff764cc01197b1b1ed497000726b84dc4b47c1dfc8a2bb4"),
}


def _inner_bazel_impl(_ctx):
    for suffix, (arch, sha256) in _INNER_BAZEL.items():
        http_file(
            name = "inner_bazel_" + suffix,
            urls = ["https://github.com/bazelbuild/bazel/releases/download/{v}/bazel-{v}-{a}".format(
                v = INNER_BAZEL_VERSION,
                a = arch,
            )],
            sha256 = sha256,
            executable = True,
            downloaded_file_path = "bazel",
        )


inner_bazel = module_extension(implementation = _inner_bazel_impl)

# --- Project source archives ----------------------------------------------

# repo name -> dict(url, sha256, filename). Add a line here to vendor a new
# project's source. The repo's file is reachable as `@<name>//file`.
_PROJECT_SOURCES = {
    "absl_archive": {
        "url": "https://github.com/abseil/abseil-cpp/releases/download/20260526.0/abseil-cpp-20260526.0.tar.gz",
        "sha256": "6e1aee535473414164bf83e4ebc40240dec71a4701f8a642d906e95bea1aea0c",
        "filename": "abseil-cpp-20260526.0.tar.gz",
    },
}


def _project_sources_impl(_ctx):
    for name, info in _PROJECT_SOURCES.items():
        http_file(
            name = name,
            urls = [info["url"]],
            sha256 = info["sha256"],
            downloaded_file_path = info["filename"],
        )


project_sources = module_extension(implementation = _project_sources_impl)
