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

load(":overlays.bzl", "ACTIOND_WORKER", "BUILDBUDDY_RBE")

def environment(name, platforms, overlays = [], pin_platform = False, host_only = False, platform_flags = {}):
    return struct(
        name = name,
        platforms = platforms,
        overlays = overlays,
        pin_platform = pin_platform,
        host_only = host_only,
        platform_flags = platform_flags,
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

# actiond: a local Linux RE worker (a VM on this host). Builds+tests the museum's
# projects for linux/arm64 without leaving this macOS machine — the same matrix
# cell as `rbe` linux_arm64, but executed locally instead of in the cloud. The
# VM is arm64 (matches Apple silicon), so it serves linux_arm64. pin_platform
# makes the build fully explicit about os/arch (the worker doesn't turn a macOS
# toolchain into a Linux one — HERMETIC_LLVM does, by cross-targeting linux).
# Requires the worker to be running: `bazel run //tools/actiond:serve`.
ACTIOND = environment(
    name = "actiond",
    platforms = ["linux_arm64"],
    overlays = [ACTIOND_WORKER],
    pin_platform = True,
)
