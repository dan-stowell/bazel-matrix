# Design

Bazel Museum is a collection of reproducible Bazel builds of public open-source
projects. There are three pieces. **Piece 1 (the data pipeline) and Piece 2
(isolated, daemonless builds) are built, and Piece 3 has three projects spanning
three toolchains — C++ (abseil-cpp), JVM (copybara), and Rust (cxx) — each built
fully hermetically. The optional containerized isolation tier is the next step.**

Everything is driven by Bazel: clone the repo onto a host that has only Bazel
(via `bazelisk`) and you can build and run everything. No host Python, no host
`gh`, no daemons assumed.

---

## Piece 1 — Data pipeline (built)

Discovers public projects that build with Bazel and writes a normalized
snapshot to [`data/projects.json`](../data/projects.json).

```
bazel run //pipeline:gather                 # fetch + enrich + write snapshot
bazel run //pipeline:gather -- --enrich=none # offline: skip GitHub enrichment
bazel run //pipeline:gather -- --enrich=all  # enrich rulesets/tooling too
```

### Sources

| id        | what                                                              | how |
|-----------|-------------------------------------------------------------------|-----|
| `nicolov` | [nicolov/awesome-bazel] "Projects built with Bazel" section       | parse Markdown bullet list |
| `jin`     | [jin/awesome-bazel] "Projects" section                            | parse Markdown bullet list |
| `bcr`     | [Bazel Central Registry] — every module's `metadata.json`         | download one repo tarball, read all metadata, **classify** |

[nicolov/awesome-bazel]: https://github.com/nicolov/awesome-bazel
[jin/awesome-bazel]: https://github.com/jin/awesome-bazel
[Bazel Central Registry]: https://github.com/bazelbuild/bazel-central-registry

The awesome-list "projects" sections are curated, so their entries are trusted
as projects. The registry is mostly rulesets/tooling mixed with real projects,
so each module is classified heuristically.

### Classification heuristics (BCR)

Implemented in [`pipeline/classify.py`](../pipeline/classify.py). Every decision
carries a human-readable `classification_reason` so the output is auditable:

- module name contains `rules_` / `-rules` / `_rules` → **ruleset**
- module name contains `bazel`, `gazelle`, `toolchain`, `stardoc`, `skylib`,
  `buildtools`/`buildifier` → **tooling**
- published by a known Bazel-tooling org (`bazelbuild`, `bazel-contrib`,
  `aspect-build`) → **tooling**
- otherwise → **project** (e.g. abseil-cpp, grpc, openexr, antlr4, libavif)

These are intentionally conservative and easy to tune.

### Normalization, dedup, enrichment

- Every entry is keyed by `owner/repo` (case-insensitive) and deduped; an entry
  found in multiple sources keeps the union of `sources` and the most specific
  category.
- Enrichment uses the GitHub API (via hermetic `gh`) to add `stars`, `archived`,
  `language`, `pushed_at`, and `description`. Because `gh` follows renames, the
  canonical `owner/repo` is adopted and a second dedup pass collapses aliases
  (e.g. `google/protobuf` → `protocolbuffers/protobuf`).
- Output is deterministic (sorted by category, then stars, then key; no
  timestamps) so committed diffs are meaningful.

### Hermetic `gh` (GitHub CLI as a Bazel dependency)

We do **not** rely on a host-installed `gh`. [`tools/gh/extension.bzl`](../tools/gh/extension.bzl)
is a module extension that downloads a pinned `gh` release tarball
(version + sha256) and exposes the binary. `//pipeline:gather` bundles it via
`data`/`args` (selected per CPU; linux **amd64** and **arm64** are both wired
up) and locates it at runtime through runfiles.

**Token handling** (see [`pipeline/github.py`](../pipeline/github.py)):

1. `GH_TOKEN` or `GITHUB_TOKEN` from the environment, else
2. the host's stored credential via `gh auth token` (reads `~/.config/gh`).

The resolved token is passed explicitly to every `gh api` call via `GH_TOKEN`,
so authentication works without the binary depending on host `gh` state. To use
a specific token: `GH_TOKEN=… bazel run //pipeline:gather`.

### Layout

```
pipeline/
  gather.py        entrypoint: fetch → merge/dedup → enrich → write JSON
  model.py         Project dataclass, GitHub URL parsing, dedup/merge
  classify.py      BCR project/ruleset/tooling heuristics
  github.py        hermetic-gh wrapper + token resolution
  netfetch.py      stdlib-only HTTP helpers (no third-party deps)
  sources/         one module per source (nicolov, jin, bcr)
tools/gh/          hermetic gh CLI module extension (pipeline enrichment)
tools/fetch/       module extensions: inner Bazel binary + project source pins
tools/buildrunner/ runner.py — the isolated, daemonless inner-build engine
  overlays/        static snippets appended onto a project (e.g. hermetic LLVM)
builds/
  defs.bzl         museum_project / goal macros
  overlays.bzl     reusable named overlays (e.g. HERMETIC_LLVM)
  abseil_cpp/ copybara/ cxx/   one package per project, each with build+test goals
data/projects.json generated snapshot (committed)
```

The pipeline uses only the Python standard library plus `rules_python`'s
runfiles helper — no pip lockfile — which keeps it simple and hermetic.

---

## Piece 2 — Running Bazel builds in isolation (built; Tier 1)

`bazel run //builds/<project>:<goal>` runs an inner `bazel build`/`test` with a
**pinned, hermetic inner Bazel**, **daemonless**, in an **isolated build root** —
using only Bazel on the host. Isolation here is at the level of *Bazel state +
environment* (Tier 1); a kernel/container tier is the next step.

### How it works

```
bazel run //builds/abseil_cpp:test
  │  (outer Bazel)
  ▼
tools/buildrunner/runner.py            # the engine, a py_binary per goal
  ├─ resolves (via runfiles):
  │    @inner_bazel_<os>_<cpu>//file   # pinned bazel 9.1.1 binary (hermetic)
  │    @absl_archive//file             # pinned abseil source tarball (sha256)
  ├─ extracts source fresh into  <build_root>/work/   (deterministic mtimes)
  ├─ applies the goal's overlays: appends snippets (e.g. hermetic LLVM into
  │    MODULE.bazel) and patches (patch -p1) onto the source
  └─ exec:  bazel --batch --nohome_rc --nosystem_rc
                  --output_user_root=<build_root>/output_root
                  test --repository_cache=<build_root>/repo_cache
                  <overlay+goal flags> -- <targets>
            (cwd = extracted workspace, scrubbed env)
```

The pinned inner Bazel binary and project source tarballs are fetched by
[`tools/fetch/extension.bzl`](../tools/fetch/extension.bzl) (the same hermetic,
sha256-pinned pattern as the `gh` CLI; linux + darwin, amd64 + arm64). The
`museum_project`/`goal` macros ([`builds/defs.bzl`](../builds/defs.bzl)) wire a
`py_binary` per goal around `runner.py` with that project's source, the inner
Bazel, and the goal's overlay files as `data`.

### What "isolation" guarantees (Tier 1)

- **Hermetic inner Bazel** — a pinned release binary, never the host's bazel/
  bazelisk.
- **Pinned source** — extracted fresh each run from a content-addressed
  tarball, so the build always starts from a pristine, known tree.
- **Dedicated state** — its own `--output_user_root` and `--repository_cache`
  under a per-project build root (default `${TMPDIR}/bazel-museum/<project>`,
  override with `MUSEUM_BUILD_ROOT`). The host's `~/.cache/bazel` is never
  touched.
- **Daemonless** — `--batch`: no Bazel server survives the run.
- **No host config leakage** — `--nohome_rc --nosystem_rc`, and a scrubbed
  environment (only an explicit allowlist — `PATH`, proxy/TLS vars, `CC`/`CXX`,
  locale — is passed through).

Reruns are fast: even though the source is re-extracted, the tarball's
deterministic mtimes mean the inner action cache hits (~5 s vs ~5 min cold).

### Overlays, goals, and projects

The build layer is organized so that **overlays/patches attach to a (project ×
goal × environment) combination** — the structure we grow toward remote
execution and harder targets (e.g. `actiond`).

- An **overlay** ([`builds/overlays.bzl`](../builds/overlays.bzl)) is a reusable,
  named bundle of: source `appends` (file → `MODULE.bazel` / `.bazelrc`),
  `patches` (unified diffs, `patch -p1`), `build_flags`, and `remote_header_envs`
  (`ENV:HEADER` pairs the runner turns into `--remote_header=HEADER=<value>`, to
  inject secrets like an API key without committing them).
- A **goal** is one runnable target = `(command: build|test, targets, overlays,
  flags)`.
- A **project** (`museum_project`) pins a source tarball + base overlays and
  lists goals; each goal becomes `//builds/<project>:<goal>`, merging base +
  goal overlays. Overlays compose, so an environment (remote cache / RBE) is
  just another overlay you add to a goal.

### Hermetic C/C++ toolchain (the `HERMETIC_LLVM` overlay)

The `HERMETIC_LLVM` overlay builds a project with a **fully hermetic LLVM
toolchain** — [hermeticbuild/hermetic-llvm][hllvm], the BCR module `llvm`. It is
*zero-sysroot*: the target libc, libc++, CRT, and compiler runtimes are
built/linked from Bazel-managed sources, so the build does **not** use the host
compiler, headers, libc, or any sysroot. (Verified: abseil/cxx compile with
`external/llvm++.../bin/clang` and zero `/usr/bin` compiler calls.) It is
injected **without forking the project**: the overlay appends
[`hermetic_cc.MODULE.bazel`](../tools/buildrunner/overlays/hermetic_cc.MODULE.bazel)
(`bazel_dep(name = "llvm", ...)` + `register_toolchains(...)`) onto the source's
`MODULE.bazel` and adds `--extra_toolchains=@llvm//toolchain:all` to win over the
host-autodetected toolchain. Its zero-sysroot property is also what will make
hermetic RBE work without a sysroot baked into the remote image.

[hllvm]: https://github.com/hermeticbuild/hermetic-llvm

hermetic-llvm also cross-compiles (linux x86_64 ↔ aarch64, and more), the lever
for cross-platform/RBE work.

### Remote build execution (BuildBuddy RBE)

The `BUILDBUDDY_RBE` overlay ([`builds/overlays.bzl`](../builds/overlays.bzl))
runs builds *and* tests on BuildBuddy's cloud executors. Each project has
`build.remote` and `test.remote` goals (the overlay composes onto any goal).

We deliberately **do not use `toolchains_buildbuddy`**. Because `HERMETIC_LLVM`
is zero-sysroot, the compiler and all inputs are content-addressed and uploaded
to the CAS, so they run **image-agnostically** on the executor — hermetic-llvm
even builds its own glibc 2.28 + compiler-rt from source *on the executor*. The
only image requirement is a glibc new enough to launch the prebuilt `clang`
(BuildBuddy's default Ubuntu 16.04 is too old), so the overlay pins a modern
executor image via `--remote_default_exec_properties=container-image=…`. The API
key is injected as a `--remote_header` by the runner (never committed).

Verified on a linux/amd64 host: abseil 1327 remote actions, cxx 515 remote,
copybara 292 remote — all green. Tests execute remotely too:

| Project | `test.remote` | excluded on the executor (kept locally) |
|---------|---------------|------------------------------------------|
| abseil-cpp | 248/248 pass | 3 cctz/time tests — executor lacks system tzdata |
| cxx | 1/1 pass | — |
| copybara | 218/218 pass | Mercurial (no `hg`); 2 tests asserting permission-denied (executor runs as root) |

The exclusions are all **executor-environment** differences (missing tzdata,
root uid), not real failures — the local `test` goal still runs them. They're
the RBE analogue of the local host-tooling notes below, and the natural fix is a
hermetic data input (tzdata) / a non-root exec property rather than excluding.

**macOS arm64 (next).** On a darwin host, Bazel's auto exec platform is darwin,
but the executors are linux/x86_64. RBE from a Mac must therefore force a linux
exec+target platform (a `platform()` with the executor `container-image`, set via
`--host_platform`/`--platforms`/`--extra_execution_platforms`) so hermetic-llvm's
linux toolchain runs on the executor and the Mac only orchestrates. Note for that
work: `cxx` and `copybara` direct-depend on `platforms` (so `@platforms` is
visible for the platform target), but `abseil-cpp` does **not** — its Mac-RBE
overlay must also append `bazel_dep(name = "platforms", …)` to `MODULE.bazel`.

### Known boundaries (future work)

- **Host tooling in tests.** Some projects' tests shell out to host binaries.
  copybara's Mercurial (`hg`) tests are excluded (not a hermetic input); its Git
  tests currently use the host `git`. A pinned-binary overlay for `git` (same
  pattern as bazel/gh/llvm) would close this. Test actions otherwise run with a
  pinned UTF-8 locale for reproducibility.
- **Network is open** during the inner build (to fetch BCR deps + the toolchain);
  the repository cache makes this a one-time cost. Vendoring for fully offline
  builds is possible later.
- **Optional container tier.** A minimal OCI image via
  [`rules_img`](https://github.com/bazel-contrib/rules_img) for kernel-level
  isolation. With toolchains hermetic, its marginal value is whole-process
  FS/network confinement and a home for system-package deps — opt-in, not
  required.

## Piece 3 — The build collection

Each project lives under `builds/<project>/` and is declared with
`museum_project`. Its source is pinned in
[`tools/fetch/extension.bzl`](../tools/fetch/extension.bzl) (the kickoff's
"source as a dep in `MODULE.bazel`"), and overlays/patches attach per goal.

### Projects

| Project | Lang | Goals | Source pin | Toolchain (all hermetic) |
|---------|------|-------|-----------|--------------------------|
| [abseil-cpp](../builds/abseil_cpp/BUILD.bazel) | C++ | `build`, `test`, `build.remote`, `test.remote` | release `20260526.0` | LLVM (`HERMETIC_LLVM`) |
| [copybara](../builds/copybara/BUILD.bazel) | Java | `build`, `test`, `build.remote`, `test.remote` | tag `v20260622` | remote JDK (rules_java) |
| [cxx](../builds/cxx/BUILD.bazel) | Rust | `build`, `test`, `build.remote`, `test.remote` | tag `1.0.194` | rustc (rules_rust) + LLVM |

`bazel test` results, all hermetic (compiles use `external/llvm++.../bin/clang`
with zero `/usr/bin` compiler calls; copybara runs on a bundled OpenJDK with
host `java` absent):

| Project | tests | notes |
|---------|-------|-------|
| abseil-cpp | **251/251 pass** | — |
| cxx | **1/1 pass** | `//...` has a single test target |
| copybara | **220/220 pass** | excludes Mercurial (`hg`) tests; Git tests use host `git` |

Three different toolchain-provisioning paths (LLVM overlay, built-in remote JDK,
rules_rust download), and each fetches darwin toolchains too — the collection
runs on linux and macOS.

Adding a project:

1. Add its source tarball (url + sha256 + filename) to `_PROJECT_SOURCES` in
   `tools/fetch/extension.bzl` and `use_repo(...)` it in `MODULE.bazel`.
2. Create `builds/<project>/BUILD.bazel` with a `museum_project(...)` call
   declaring its `goal(...)`s (and any base overlays).
3. `bazel run //builds/<project>:build` / `:test`.

The data pipeline (piece 1) feeds the choice of projects: pick well-known,
self-contained projects that already build with Bazel from `data/projects.json`.
