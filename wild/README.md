# wild — builds "as found in nature"

The museum proper makes projects hermetic *by injection*: a pinned inner Bazel, a
fully-hermetic LLVM toolchain, and per-project overlays. This directory takes the
opposite bet:

> Put the reproducibility boundary at the **container**, not the build graph. Ship
> an image with **nothing but bazelisk**, drop a project's source in *exactly as
> upstream wrote it* (no overlays, no injected toolchain), and run its build. The
> question we're measuring: **which projects are already hermetic enough to build
> with nothing but bazelisk + the network?**

## Pieces

- [`Dockerfile`](Dockerfile) — a two-stage build whose final image is just
  `debian-slim` + `ca-certificates` + the `bazelisk` binary (~136 MB). No
  compiler, no language SDK, no build tools. (CA certs are irreducible: bazelisk
  downloads Bazel, and builds fetch the BCR + toolchains over https.)
- [`build.sh`](build.sh) — `wild/build.sh <project> [bazel-args…]`. Reuses the
  museum's pinned source tarball (same url+sha256 as
  `//tools/fetch:extension.bzl`), verifies it on the host, mounts it into the
  container, and runs `bazelisk` against the upstream `MODULE.bazel`/`BUILD` as
  found. `USE_BAZEL_VERSION=<v>` forces a specific Bazel (otherwise bazelisk
  honors the project's `.bazelversion`, or the latest if it pins none).

```sh
docker build -t bazel-wild wild/
wild/build.sh buildtools build //buildifier:buildifier
USE_BAZEL_VERSION=7.4.1 wild/build.sh fast_float build //...
```

## First findings

Two failure layers surface immediately, and they are the whole story so far.

**1. Version drift.** A project that pins no `.bazelversion` gets whatever
bazelisk thinks is latest (today, Bazel **9.1.1**). Bazel 9 removed the
autoloaded `cc_*` / `sh_test` built-ins, so older releases break at *load* time:

```
buildtools v7.3.1  (no .bazelversion)
  → bazelisk picks 9.1.1
  → ERROR: buildifier/BUILD.bazel:60: name 'sh_test' is not defined
```

In nature, "reproducible" and "buildable" are not the same thing: the source is
pinned, but the *toolchain selector* is a moving target the project never nailed
down.

**2. The host C/C++ toolchain is the universal wall.** Pin past the version drift
(`USE_BAZEL_VERSION=7.4.1`) and every project that compiles anything fails at the
*same* place — Bazel's C/C++ toolchain **auto-configuration**, which probes the
host for `gcc`/`CC` and finds none in a bazelisk-only image:

```
fast_float  (pure C++)   → @rules_cc//…/local_config_cc:cc-compiler-k8
buildtools  (pure Go!)   → @rules_go//:cgo_context_data → …/local_config_cc
  both → "Auto-Configuration Error: Cannot find gcc or CC"
```

Note buildtools is a *pure-Go* binary, yet rules_go still eagerly configures a
cgo C toolchain at analysis time. So even "no native code" projects lean on a
host compiler in nature — exactly the dependency the museum's `HERMETIC_LLVM`
overlay removes by injection.

## The baseline image: build it as it is

Almost nothing builds with *literally* nothing but bazelisk, because in nature a
Bazel project assumes the host is a developer machine. So the working image is
[`Dockerfile.baseline`](Dockerfile.baseline) — bazelisk + a **normal CI machine**
(C/C++ toolchain, JDK, python, git, zip; ~1.1 GB). The goal is to *build things
as they are*; the pinned image is the "nature" they run in. Hermeticity then
becomes **its own dimension** we measure, not a precondition:

- **hermetic from the start** — builds in the strict, compiler-free image.
- **hermetic with a nudge** — would, with a small declared change (e.g. register
  a `toolchains_llvm` toolchain in its own MODULE).
- **leans on the host** — builds only with the baseline image's toolchain.

## First catalog (baseline image, `build //...` unless noted)

| project | bazelisk picked | result | wall / note |
|---------|:--------------:|:------:|-------------|
| cpu_features | 9.1.1 | ✅ | builds clean as-is (98 actions) |
| fast_float | 9.1.1→**7.4.1** | ✅¹ | builds at 7.4.1; `//...` on 9 fails (drift) |
| json | 9.1.1 | ❌ | `//...`: `docs/mkdocs/...` pkg won't load (drift) |
| googletest | 9.1.1 | ❌ | `//...`: `googlemock/test` pkg won't load (drift) |
| buildtools | 9.1.1 | ❌ | `sh_test` removed in Bazel 9 (pins no version) |
| doctest | **8.5.0** | ❌ | root `//:doctest` uses `includes=["."]`, rejected as the main module (fine as a *dep*) |

¹ with `USE_BAZEL_VERSION=7.4.1`.

The dimensions that fell out, each roughly independent:

1. **Bazel version.** Does the repo pin a `.bazelversion`? buildtools/json/fast_float
   pin none → bazelisk grabs Bazel 9, which removed the `cc_*`/`sh_test` autoloads,
   so any package still using them fails to *load*. doctest *does* pin (8.5.0) and
   bazelisk honors it — version-pinning works in nature when the repo bothers.
2. **Host toolchain.** Cleared by the baseline image (gcc/JDK/python); the strict
   image is the probe for who doesn't need it.
3. **Build surface.** `build //...` is the honest "build it all," but one stray
   docs/test/example package (often the version-drift casualty) fails the whole
   pattern even when the core lib is fine. Per-target builds tell a different story.
4. **Consumption shape.** Some libraries (doctest) are meant to be *consumed*, not
   built as the root module — `includes=["."]` is legal for an external dep, not
   for the main workspace.

## Status / strict-image findings

The strict (bazelisk-only) image established the two walls below; the baseline
image clears the host-toolchain one, leaving version drift as the dominant blocker.

| project | lang | result (strict, bazelisk-only) |
|---------|------|----------------------|
| buildtools | Go | ❌ no `.bazelversion` → Bazel 9 `sh_test` removed; @7.4.1 → no host gcc (rules_go cgo) |
| fast_float | C++ | ❌ @7.4.1 → no host gcc (rules_cc autoconfig) |
