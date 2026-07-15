"""Module extension that fetches a pinned GitHub CLI binary."""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

GH_VERSION = "2.95.0"

# repo suffix -> (release asset platform fragment, extension, sha256)
GH_PLATFORMS = {
    "linux_amd64": ("linux_amd64", "tar.gz", "25d1e4729e8808c9ed3d613e96ebd3f3e44446f2d368c89d878a71a36ddb3d8c"),
    "linux_arm64": ("linux_arm64", "tar.gz", "d41e0b3b6218e5741c8bb4db39b16e53a59e0e06299a8489bd38f623ef7ebaae"),
    "darwin_amd64": ("macOS_amd64", "zip", "985707e9ac60c95ed51cddd808c338b481abe69fffa77e9d6547c3750045f77e"),
    "darwin_arm64": ("macOS_arm64", "zip", "3677f9c27965825f9c7d50395473c134edaea4b484373ef6b25de653570a0489"),
}

_BUILD_FILE = """\
filegroup(
    name = "gh",
    srcs = ["bin/gh"],
    visibility = ["//visibility:public"],
)
"""

def _gh_extension_impl(_ctx):
    for suffix, (asset_platform, ext, sha256) in GH_PLATFORMS.items():
        archive_name = "gh_{version}_{platform}".format(
            version = GH_VERSION,
            platform = asset_platform,
        )
        http_archive(
            name = "gh_cli_" + suffix,
            urls = ["https://github.com/cli/cli/releases/download/v{version}/{name}.{ext}".format(
                version = GH_VERSION,
                name = archive_name,
                ext = ext,
            )],
            sha256 = sha256,
            strip_prefix = archive_name,
            build_file_content = _BUILD_FILE,
        )

gh_extension = module_extension(implementation = _gh_extension_impl)
