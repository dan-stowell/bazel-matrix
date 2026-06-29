"""Environments: where a goal's inner build actually runs.

An *environment* provisions execution capacity and declares which (os, arch)
platforms it can serve. museum_project crosses environments x platforms x
commands to emit the concrete `<command>_<env>_<os>_<arch>` goal targets (see
//builds:defs.bzl).

Fields:
  * name        — token used in target names (`local`, `rbe`).
  * platforms   — list of PLATFORMS keys this environment can serve.
  * overlays    — overlays applied to every goal in this environment (e.g. the
                  BuildBuddy connection for `rbe`).
  * pin_platform — if True, the goal injects museum_rbe/ and pins --platforms /
                  --extra_execution_platforms / --host_platform to its platform.
                  Used by remote environments so the build is fully explicit
                  about os/arch instead of inheriting the orchestrating host's.
  * host_only   — if True, each goal only runs when the *host* matches its
                  platform (via target_compatible_with). This is how `local`
                  models "one OS/arch at a time": on this laptop only the
                  darwin_arm64 goals are live; on the linux VM only linux_amd64.
  * platform_flags — dict platform-name -> extra build flags applied only to
                  goals on that platform (e.g. a toolchain flag a particular
                  os/arch needs in this environment).

To add an environment (e.g. a future `actiond`), define it here with the
platforms it supports and add it to a project's `environments = [...]`.
"""

load(":overlays.bzl", "ACTIOND_WORKER", "BUILDBUDDY_RBE", "CC_NODETECT")

def environment(name, platforms, overlays = [], pin_platform = False, host_only = False, host_cpu_only = False, platform_flags = {}, container_image = None):
    return struct(
        name = name,
        platforms = platforms,
        overlays = overlays,
        pin_platform = pin_platform,
        host_only = host_only,
        host_cpu_only = host_cpu_only,
        platform_flags = platform_flags,
        container_image = container_image,
    )

# The host machine itself. Supports exactly one platform at a time — whichever
# the host is — so each per-platform goal is gated on the host matching it.
LOCAL = environment(
    name = "local",
    platforms = ["linux_amd64", "darwin_arm64"],
    host_only = True,
)

# BuildBuddy cloud RBE. Host-independent: runs the same from a linux or macOS
# orchestrator. Serves linux amd64/arm64 and darwin arm64.
#
# darwin_arm64 uses the *prebuilt* hermetic-llvm toolchain (the default `source`)
# like linux does — the compiler is downloaded and only the compiler-rt builtins
# build from source (~600 actions for an abseil target). We deliberately do NOT
# force `--@llvm//toolchain:source=bootstrapped`: that rebuilds clang/LLVM from
# source on the executor (~13k actions, ~22x more) and was only needed before the
# HERMETIC_LLVM `-isysroot` backport, when the toolchain's host-tool compiles fell
# through to host Xcode. With that patch the prebuilt path is hermetic on the
# executor (no Xcode-path errors), so no per-platform flag is required.
RBE = environment(
    name = "rbe",
    platforms = ["linux_amd64", "linux_arm64", "darwin_arm64"],
    overlays = [BUILDBUDDY_RBE],
    pin_platform = True,
)

# actiond: a local Linux RE worker (a QEMU/KVM VM on this host). Builds+tests the
# museum's projects locally instead of in the cloud — the same matrix cells as
# `rbe`'s linux platforms, but served by a worker on this machine.
#
# actiond boots a Linux guest of the *host's* CPU arch (it starts an embedded
# qemu-system with -accel kvm), so it serves the linux platform matching the
# host: linux_amd64 on an x86_64 host, linux_arm64 on an arm64 host (incl. an
# arm64 macOS host running a Linux guest). host_cpu_only gates each goal on the
# host CPU so only the matching-arch cell is live. pin_platform makes the build
# explicit about os/arch (HERMETIC_LLVM cross-targets linux regardless of host).
# Requires KVM access and the worker running: `bazel run //tools/actiond:serve`.
ACTIOND = environment(
    name = "actiond",
    platforms = ["linux_amd64", "linux_arm64"],
    overlays = [ACTIOND_WORKER],
    pin_platform = True,
    host_cpu_only = True,
)

# MINIMG: run the inner build inside a *minimal* container image — debian-slim
# with the generic build tools (python/git/curl/zip) but NO host C/C++ toolchain.
# The HERMETIC_LLVM overlay (carried on the project's `toolchains`) supplies clang
# over the BCR, so the image needs no compiler; CC_NODETECT suppresses Bazel's
# host-cc probe that would otherwise hard-error in a toolchain-free image. This is
# the containerised, image-agnostic build that actiond will execute remotely —
# proven for re2/abseil in docs/hermetic-minimal.md.
#
# Like actiond it runs a linux build of the host's CPU arch (the image is linux),
# so host_cpu_only gates each goal on the host CPU. The image is a docker tag
# built+loaded by `bazel run //runner/image:minimal_load`.
MINIMG = environment(
    name = "minimg",
    platforms = ["linux_amd64", "linux_arm64"],
    overlays = [CC_NODETECT],
    host_cpu_only = True,
    container_image = "museum-minimg:latest",
)

# CIIMG: run the inner build inside the *full* CI image — debian + the ordinary
# build toolchain (build-essential/gcc, JDK, python, git, curl, zip), the same
# "ordinary CI machine" the //projects wild builds use. No CC_NODETECT and no
# injected hermetic toolchain: the build uses the image's own gcc, autodetected.
# This is the non-hermetic container tier — "builds with the toolchain a real CI
# box has" — as opposed to MINIMG's toolchain-free + hermetic-LLVM design. The
# image is the docker tag built+loaded by `bazel run //runner/image:load`.
CIIMG = environment(
    name = "ciimg",
    platforms = ["linux_amd64", "linux_arm64"],
    overlays = [],
    host_cpu_only = True,
    container_image = "bazel-runner-baseline:latest",
)
