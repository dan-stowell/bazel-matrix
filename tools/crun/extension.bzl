"""Module extension fetching a hermetic, pinned `crun` (static OCI runtime).

`crun` runs the //wild/image rootfs **daemonlessly and rootlessly** — no
dockerd, no host-installed runtime. We download the official statically-linked
release binary (a single self-contained ELF) and expose it as a file. Pinning
version + sha256 keeps it reproducible and removes any dependency on a host
container runtime, exactly as the museum does for `gh`, `zip`, and `bazelisk`.

linux amd64 + arm64 are wired up. To bump: update CRUN_VERSION and the sha256s
(sha256sum of each release asset at
github.com/containers/crun/releases/download/<v>/crun-<v>-linux-<arch>).
"""

load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_file")

CRUN_VERSION = "1.28"

# repo suffix -> sha256 of crun-<version>-linux-<arch> (statically linked).
CRUN_PLATFORMS = {
    "linux_amd64": "2aa6b7024a9c9f153895c0d11ae233d3758f54844011c3a039e3e89048d01d42",
    "linux_arm64": "cc1e8ec89aef1422e0741be196f9ed099e2e09d2f48f30f27cd44a22ef1f0342",
}

def _crun_impl(_ctx):
    for suffix, sha256 in CRUN_PLATFORMS.items():
        arch = suffix.split("_")[1]
        http_file(
            name = "crun_" + suffix,
            urls = ["https://github.com/containers/crun/releases/download/{v}/crun-{v}-linux-{a}".format(
                v = CRUN_VERSION,
                a = arch,
            )],
            sha256 = sha256,
            executable = True,
            downloaded_file_path = "crun",
        )

crun = module_extension(implementation = _crun_impl)
