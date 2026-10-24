"""The pinned inner Bazels: the one place their versions and digests live.

tools/sources.bzl fetches each as `@projects//:bazel_<version>`;
tools/sync.py reads DEFAULT_INNER_BAZEL for bazel_compatibility checks.
"""

DEFAULT_INNER_BAZEL = "9.3.1"

INNER_BAZELS = {
    "9.3.1": struct(
        sha256 = "7f775b54bbec487efaf0f49ccda1d2ed02cd34f582edfdd6aeeec76e39ef585c",
        startup_flags = ["--experimental_remote_repo_contents_cache"],
    ),
    # Has no remote repo contents cache.
    "8.4.2": struct(
        sha256 = "4dc8e99dfa802e252dac176d08201fd15c542ae78c448c8a89974b6f387c282c",
        startup_flags = [],
    ),
}
