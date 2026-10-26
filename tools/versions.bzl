"""The pinned inner Bazels: the one place their versions and digests live.

tools/sources.bzl fetches each as `@projects//:bazel_<version>` (linux-x86_64)
and, with an arm64_sha256, `@projects//:bazel_<version>_arm64` (linux-arm64);
tools/sync.py reads DEFAULT_INNER_BAZEL for bazel_compatibility checks.
"""

DEFAULT_INNER_BAZEL = "9.3.1"

INNER_BAZELS = {
    "9.3.1": struct(
        sha256 = "7f775b54bbec487efaf0f49ccda1d2ed02cd34f582edfdd6aeeec76e39ef585c",
        # linux-arm64, for --config=inner-remote-arm64 (see README.md).
        arm64_sha256 = "10ba9cb76d4ee748d274dcc2981992bb12b74a203dc41a9c2eceeb8f29359366",
        startup_flags = ["--experimental_remote_repo_contents_cache"],
    ),
    # Has no remote repo contents cache.
    "8.4.2": struct(
        sha256 = "4dc8e99dfa802e252dac176d08201fd15c542ae78c448c8a89974b6f387c282c",
        arm64_sha256 = None,
        startup_flags = [],
    ),
}
