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
  * tools     — list of (binary_label, name): stage the built binary onto the
                inner build's PATH as `name` (the runner's --tool). For a project
                whose build shells out to a host tool (e.g. Bazel's genrules call
                `zip`), this supplies a hermetic, pinned one instead.

Overlays compose: a project sets base overlays for all its goals, and each goal
can add more (e.g. a remote-execution overlay). This is how we capture
overlays/patches per (project x goal x environment).
"""

def overlay(name, appends = [], writes = [], patches = [], build_flags = [], remote_header_envs = [], tools = []):
    return struct(
        name = name,
        appends = appends,
        writes = writes,
        patches = patches,
        build_flags = build_flags,
        remote_header_envs = remote_header_envs,
        tools = tools,
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

# Hermetic `zip` on PATH. Some projects' builds shell out to `zip` (Bazel
# itself: its genrules call `zip` ~72x to pack the embedded install base), which
# the scrubbed inner environment doesn't provide. Instead of requiring a host
# `zip`, we build one from Info-ZIP's pinned source with the hermetic LLVM
# toolchain (//tools/zip, @infozip//:zip) and stage it onto the inner build's
# PATH via the runner's --tool. Pair with HERMETIC_LLVM on projects that need it.
HERMETIC_ZIP = overlay(
    name = "hermetic_zip",
    tools = [("@infozip//:zip", "zip")],
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

# Make @rules_cc visible so a BUILD file can `load()` the C/C++ rules. Bazel 9
# removed cc_library/cc_test/cc_binary from the global builtins; legacy BUILD
# files that call them unloaded (e.g. googletest) need both an explicit load()
# (patched in per project) and rules_cc in the module's repo mapping (this
# append). Apply only to projects that don't already depend on rules_cc — a
# duplicate bazel_dep errors.
RULES_CC_DEP = overlay(
    name = "rules_cc_dep",
    appends = [("//tools/buildrunner/overlays:rules_cc_dep.MODULE.bazel", "MODULE.bazel")],
)

# Makes @platforms visible by appending a direct bazel_dep. The museum's injected
# RBE platform package (museum_rbe) uses @platforms//os + @platforms//cpu
# constraints; a project that never declares `platforms` as a direct dep can't
# resolve them and its RBE/actiond goals fail at analysis. Apply to such projects
# (e.g. magic_enum). A no-op for local goals beyond a satisfied direct dep; don't
# apply to projects that already depend on platforms (a duplicate bazel_dep errors).
PLATFORMS_DEP = overlay(
    name = "platforms_dep",
    appends = [("//tools/buildrunner/overlays:platforms_dep.MODULE.bazel", "MODULE.bazel")],
)

# NOTE: projects whose *transitive deps* use Bazel-9-removed APIs (old
# aspect_bazel_lib, rules_foreign_cc, rules_go, ...) are handled by building them
# on a late Bazel 8 inner — museum_project(bazel_version = "8.7.0") — rather than
# by per-dep single_version_override overlays. Bazel 8.7 keeps the legacy APIs
# and still carries the zero-sysroot hermetic-llvm toolchain (repo_metadata
# landed in 8.3). See //builds/grpc and //builds/flatbuffers.

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
        # NB: actiond's per-action chroot needs `requires-bash`/`libc` exec
        # properties, but those go on the *platform* (museum_rbe/, see
        # rbe_platforms.BUILD.bazel), not here — --remote_default_exec_properties
        # is ignored once the execution platform sets any exec_properties (and
        # ours sets OSFamily/Arch).
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
