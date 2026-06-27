# Hermetic LLVM in a minimal image — feasibility proof

_Direction: instead of shipping a host C/C++ toolchain in the runner image, push
an **overlay** onto each project that registers a **hermetic LLVM** toolchain, so
the project builds (and tests) in a **minimal container image** — eventually
under **actiond**. This is the bridge from the current "ordinary CI machine"
image (`docs/minimal-image.md`) to a fully hermetic, image-agnostic build._

## Productized: the MINIMG environment

This is now a first-class museum **environment** (`//builds:environments.bzl`,
`MINIMG`) alongside LOCAL/RBE/ACTIOND — not a manual probe. Every project carries
it (`environments = [..., MINIMG]`), emitting `build_minimg_linux_amd64` /
`test_minimg_linux_amd64` goals:

```
bazel run //builds/re2:build_minimg_linux_amd64
bazel run //builds/re2:test_minimg_linux_amd64
```

How it works:
- `tools/buildrunner/runner.py` gained `--container-image`: it bind-mounts the
  museum build root + the inner bazel binary at identical paths into the image
  and runs the inner build there (host uid, host network), instead of on the host.
- `MINIMG` sets that image to `museum-minimg:latest`
  (`runner/image/minimal.Dockerfile` — debian-slim + python/git/curl/zip, **no
  C/C++ toolchain**) and adds the `CC_NODETECT` overlay
  (`--repo_env=BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=1`). The HERMETIC_LLVM overlay
  (already on each project's `toolchains`) supplies the compiler — so the source
  transformation is reused unchanged; MINIMG only swaps the environment.

### Sweep — build, all 49 projects (`runner/image-minimg.tsv`)

**43/49 build** in the toolchain-free container (44 counting grpc, which timed
out at 98%). The six exceptions are specific, not the toolchain:

| Project | Cause |
|---------|-------|
| bazel | genrule shells to `objcopy` (binutils) — absent from the image |
| cpptrace | its *self-registered* `toolchains_llvm` clang needs `libtinfo.so.5` (not the museum's hermetic `llvm`) |
| nsync | `<mutex>` not found — its futex-platform compile relies on host libstdc++ headers, not libc++ |
| grpc_gateway | Go **cgo** external-link via `clang++` fails (pure-Go buildtools builds fine) |
| z3 | foreign_cc `bazel-bin/**` glob / FindPython3 edge (pre-existing) |
| grpc | timeout at 98% (4036/4132) — builds, just slow |

So the hermetic-LLVM transformation carries the large majority of the suite into
a toolchain-free image. The residual failures are tool needs (objcopy), a
competing self-registered toolchain (cpptrace), host-stdlib assumptions (nsync),
cgo linking (grpc_gateway), and pre-existing edges (z3) — each a candidate for a
small per-project transformation/patch.

### Sweep — test, all 42 test goals (`runner/image-minimg-test.tsv`)

**35/42 build *and test*** in the toolchain-free container (37 counting bazel +
grpc, which only timed out at ~25 min on their large test graphs). The seven
non-passing break down as:

| Project | Test result |
|---------|-------------|
| bazel / grpc | timeout (huge test graphs; build/test both just slow) |
| cpptrace / grpc_gateway | same as build (libtinfo / cgo link) |
| copybara | **build + most tests pass**; only the `patch`/`quilt`-transformation tests fail — those host tools aren't in the image (a tool need, like git/zip) |
| protobuf | **build + most tests pass**; one arch-check test (`protoc_x86_64_test`) fails |
| opentelemetry_cpp | benchmark *smoketests* fail to build (a few targets); the rest pass |

The pattern matches the build sweep: the hermetic toolchain itself is never the
problem. What remains are specific tool needs (objcopy, patch/quilt), a couple of
test targets, and the pre-existing edges — each a small, local fix.

## Fixes applied — getting the suite working in MINIMG

Two classes of fix: **environment tools** (added to the image — auxiliary tools a
build graph invokes, never a compiler) and **source-level** (per-project, the
"transformation" axis).

After both rounds of fixes below, the MINIMG build sweep is **46/49** (the
remaining three: grpc just times out but builds; cpptrace's self-registered
toolchain and z3's foreign_cc glob are deeper edges).

**Image (`minimal.Dockerfile`) — fixed bazel + copybara:**

| Added | Unblocked |
|-------|-----------|
| `binutils` (objcopy) | **bazel** now builds (green, ~28 min) — its install-base genrule shells to `objcopy` |
| `patch`, `quilt` | **copybara** now passes all **220/220** tests (the patch/quilt-transformation tests) |
| `libtinfo5` | the clang cpptrace's *own* `toolchains_llvm` downloads now loads (see below) |

The image stays compiler-free: `gcc`/`g++`/`cc` are still absent.

**Remaining — source-level, per-project (candidates for a `variants` transform):**

| Project | Diagnosis | Fix shape |
|---------|-----------|-----------|
| nsync | pure-C `//:nsync` **builds**; only `//:nsync_cpp` fails — it compiles `.c` as `-x c++`, which Bazel treats as a C action, so the hermetic toolchain (`--sysroot=/dev/null -nostdlibinc`) adds glibc/kernel/compiler-rt headers but **not libc++** → `<mutex>` not found | narrow the MINIMG build to `//:nsync`, or a copt adding libc++'s isystem |
| grpc_gateway | Go **cgo** external-link: `ld.lld: relocation R_X86_64_64 cannot be used against symbol` (known rules_go/lld interaction) | pass `-extldflags` / linkmode to rules_go |
| cpptrace | gets past libtinfo now, but its *self-registered* `toolchains_llvm` (not the museum's hermetic `llvm`) can't link in the foreign_cc libunwind configure (`C compiler cannot create executables`) — that toolchain isn't self-contained | patch cpptrace to use the museum `llvm`, or drop its `toolchains_llvm` |
| z3 | foreign_cc `bazel-bin/**` glob / FindPython3 (pre-existing, image-independent) | upstream-edge patch |
| protobuf / opentelemetry_cpp | one arch test / a few benchmark smoketests; **builds + bulk of tests pass** | per-env test exclusion |
| bazel / grpc | only the 25-min sweep cap (bazel *builds* in ~28 min) | raise the goal timeout |

## Status: tiers 1 & 2 proven

| Tier | Goal | Result |
|------|------|--------|
| 1 | Overlay hermetic LLVM → **build** in a minimal image | ✅ re2, abseil-cpp build in a **bazelisk-only** image (no gcc/g++/make/python) |
| 2 | …→ **build + test** in a minimal image | ✅ re2 **16/16** tests pass, abseil-cpp **81/81** tests pass — same image |
| 3 | …→ run under **actiond** | next |

The minimal image used: `debian:bookworm-slim` + `bazelisk` + `ca-certificates`,
**nothing else** — no C/C++ toolchain at all. The hermetic `llvm` module
(hermeticbuild/hermetic-llvm, BCR `llvm` 0.8.9) is zero-sysroot: it builds the
target libc/libc++/CRT/compiler-rt from source, so it needs no host compiler,
headers, libc, or sysroot. Its clang does **not** need `libtinfo.so.5` (unlike
the bazelbuild `toolchains_llvm` that cpptrace/envoy self-register — see
[host-build-tooling]).

## The recipe

Two ingredients, exactly what the museum's `HERMETIC_LLVM` overlay already does
for the LOCAL/RBE path — here applied to a project built inside a container:

1. **Append to the project's `MODULE.bazel`:**
   ```starlark
   bazel_dep(name = "llvm", version = "0.8.9")
   register_toolchains("@llvm//toolchain:all")
   ```
   (On macOS also carry the `single_version_override` isysroot patch from
   `//tools/buildrunner/overlays:hermetic_cc.MODULE.bazel`; on Linux it's not
   needed.)

2. **Build/test flags:**
   ```
   --extra_toolchains=@llvm//toolchain:all
   --repo_env=BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=1
   ```
   The second flag is essential: Bazel's `cc_configure` (rules_cc) otherwise
   probes for a host `cc` unconditionally and hard-errors in a no-compiler image,
   even though the hermetic toolchain is what actually gets selected.

Reproduce (the docker runtime, against a bazelisk-only image):
```
RUNNER_RUNTIME=docker RUNNER_IMAGE=<bazelisk-only> \
RUNNER_BAZEL_FLAGS="--extra_toolchains=@llvm//toolchain:all --repo_env=BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=1" \
projects/run.sh re2 8.7.0 test //:all -//:exhaustive_test ...
```

## What this changes vs the as-is front door

- The current front door builds projects **as upstream ships them**, so they use
  the image's host gcc — which is why `build-essential` is in the image. With the
  hermetic-LLVM overlay, **`build-essential` comes out of the image** for C++
  projects: the toolchain rides in over the BCR instead.
- Residual per-project image needs are unchanged and carry over from
  `docs/minimal-image.md`: **python3** (protobuf / rules_python), **git**
  (ortools `git_repository`), **curl** (grpc wrapper), **zip** (bazel). Those are
  build-time *tools*, not the C/C++ toolchain, so hermetic LLVM doesn't remove
  them — but they're only the four heavyweights.

## Proposed productization

Make this a first-class **environment** alongside LOCAL/RBE (e.g. `MINIMG`):
`museum_project(environments=[..., MINIMG])` emits a goal that runs the
overlaid source (HERMETIC_LLVM already in `toolchains`) inside a minimal image
via the container runner, with the two flags above baked in. Then:

- a tiny `//runner/image:minimal` (bazelisk + ca-certs, plus python/git/curl/zip
  only where a project needs them), and
- the same goal grid (build / test) the museum already generates.

That sets up tier 3: the same hermetic, image-agnostic action graph is what
**actiond** executes remotely.
