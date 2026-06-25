"""Reusable, named *overlays* — bundles of source edits + flags for a goal.

An overlay captures everything needed to make some project build/test under some
condition (a toolchain, an environment like remote cache / RBE, a project fix):

  * appends   — list of (file_label, dest): append file onto dest in the source
                (e.g. inject a toolchain into MODULE.bazel, flags into .bazelrc)
  * writes    — list of (file_label, dest): copy file verbatim to dest (creating
                parent dirs), e.g. drop a patch + BUILD marker into a fresh
                package. Unlike appends, no leading newline / no existing file.
  * patches   — list of unified-diff file labels applied with `patch -p1`
  * build_flags        — flags added to the inner `bazel <command>`
  * remote_header_envs — "ENVVAR:HEADER" pairs; the runner reads ENVVAR and adds
                         --remote_header=HEADER=<value> (keeps secrets off disk)

Overlays compose: a project sets base overlays for all its goals, and each goal
can add more (e.g. a remote-execution overlay). This is how we capture
overlays/patches per (project x goal x environment).
"""

def overlay(name, appends = [], writes = [], patches = [], build_flags = [], remote_header_envs = []):
    return struct(
        name = name,
        appends = appends,
        writes = writes,
        patches = patches,
        build_flags = build_flags,
        remote_header_envs = remote_header_envs,
    )

# Fully-hermetic LLVM C/C++ toolchain (hermeticbuild/hermetic-llvm). Zero-sysroot:
# no host compiler/headers/libc. See //tools/buildrunner/overlays/.
HERMETIC_LLVM = overlay(
    name = "hermetic_llvm",
    appends = [("//tools/buildrunner/overlays:hermetic_cc.MODULE.bazel", "MODULE.bazel")],
    # Carry hermeticbuild/hermetic-llvm#642 (pass -isysroot on macOS) as a
    # single_version_override patch so we ride the latest published `llvm` BCR
    # module unforked. The appended MODULE.bazel references //museum_patches; we
    # drop that package (the patch + a BUILD marker) into the source here.
    writes = [
        ("//tools/buildrunner/overlays:patches/llvm-isysroot.patch", "museum_patches/llvm-isysroot.patch"),
        ("//tools/buildrunner/overlays:museum_patches.BUILD.bazel", "museum_patches/BUILD.bazel"),
    ],
    build_flags = ["--extra_toolchains=@llvm//toolchain:all"],
)

# rules_rust sysroot fix. Patches the published `rules_rust` (unforked, via
# single_version_override) so cargo build scripts prefix ${pwd} onto the
# `-isysroot <path>` that hermetic-llvm now emits on macOS — otherwise Rust C/C++
# build-script compiles get an execroot-relative sysroot and break. Backports
# bazelbuild/rules_rust#4101 / hermeticbuild/rules_rust#30. Pair with HERMETIC_LLVM
# on Rust projects. Self-contained like HERMETIC_LLVM's patch: writes the patch +
# the museum_patches/ BUILD marker (idempotent if both overlays are present).
RULES_RUST_SYSROOT_FIX = overlay(
    name = "rules_rust_sysroot_fix",
    appends = [("//tools/buildrunner/overlays:rules_rust_sysroot.MODULE.bazel", "MODULE.bazel")],
    writes = [
        ("//tools/buildrunner/overlays:patches/rules_rust-isysroot.patch", "museum_patches/rules_rust-isysroot.patch"),
        ("//tools/buildrunner/overlays:museum_patches.BUILD.bazel", "museum_patches/BUILD.bazel"),
    ],
)

# BuildBuddy cloud remote build execution (RBE). We deliberately do NOT use
# toolchains_buildbuddy: hermetic-llvm is zero-sysroot, so the compiler and all
# inputs are uploaded to the CAS and run image-agnostically on the executor.
#
# This overlay carries only the *connection* to BuildBuddy (endpoints, auth,
# fan-out). The execution+target *platform* is pinned separately, per goal, by
# museum_project (it injects museum_rbe/ and sets --platforms /
# --extra_execution_platforms / --host_platform to the goal's os/arch). That
# separation is what lets one environment serve multiple platforms. The API key
# is injected as a --remote_header by the runner, so it never hits disk.
_BB = "grpcs://buildbuddy.buildbuddy.io"
_BB_RESULTS = "https://buildbuddy.buildbuddy.io/invocation/"

BUILDBUDDY_RBE = overlay(
    name = "buildbuddy_rbe",
    build_flags = [
        "--remote_executor=" + _BB,
        "--remote_cache=" + _BB,
        "--bes_backend=" + _BB,
        "--bes_results_url=" + _BB_RESULTS,
        "--remote_timeout=10m",
        # Run spawns remotely, falling back to a local sandbox (then bare local)
        # only for actions that can't go remote. Crucially this drops the default
        # `worker` strategy: persistent workers run *locally*, so with a pinned
        # remote platform a local worker would try to exec the executor's toolchain
        # (e.g. the linux remote JDK) on the orchestrating host and fail with
        # "cannot execute binary file". Keeping workers off makes RBE host-neutral.
        "--spawn_strategy=remote,sandboxed,local",
        # RBE best practices: fan out, and don't pull every intermediate output.
        "--jobs=50",
        "--remote_download_toplevel",
    ],
    remote_header_envs = ["BUILDBUDDY_API_KEY:x-buildbuddy-api-key"],
)

# actiond (hermeticbuild/actiond): a *local* Remote Execution worker + cache that
# runs Bazel actions inside a small Linux VM on this host. Like BUILDBUDDY_RBE
# this overlay carries only the connection — the target/exec platform is pinned
# separately, per goal, by museum_project (linux_arm64). Start the worker first
# with `bazel run //tools/actiond:serve`; it serves grpc on 127.0.0.1:8980.
#
# Same zero-sysroot trick as RBE: because HERMETIC_LLVM uploads the whole
# compiler to the worker's CAS, actions run in actiond's empty VM chroot with no
# host toolchain. Everything goes remote (no local fallback): with the platform
# pinned to linux_arm64, a local action would try to run a linux binary on macOS.
_ACTIOND = "grpc://127.0.0.1:8980"

ACTIOND_WORKER = overlay(
    name = "actiond_worker",
    build_flags = [
        "--remote_executor=" + _ACTIOND,
        "--remote_cache=" + _ACTIOND,
        # Everything remote; no local fallback (per actiond's guidance and
        # because the pinned platform is linux, unrunnable on the macOS host).
        "--spawn_strategy=remote",
        "--genrule_strategy=remote",
        "--remote_local_fallback=false",
        "--remote_upload_local_results=false",
        "--noremote_cache_compression",
        # actiond is a *single* local VM, not a cloud pool. The museum's first
        # build compiles the whole hermetic LLVM toolchain (compiler-rt/libcxx/
        # libunwind) from source; at cloud concurrency (50) that many memory-heavy
        # clang compiles OOM-kill inside the VM. Keep concurrency modest to fit the
        # guest RAM (the serve target gives it 14 GiB); the guest CAS makes reruns
        # fast once the toolchain is warm.
        "--jobs=8",
        "--remote_download_toplevel",
    ],
)
