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
  defs.bzl         the museum_build macro
  abseil_cpp/      first project: //builds/abseil_cpp:build
data/projects.json generated snapshot (committed)
```

The pipeline uses only the Python standard library plus `rules_python`'s
runfiles helper — no pip lockfile — which keeps it simple and hermetic.

---

## Piece 2 — Running Bazel builds in isolation (built; Tier 1)

`bazel run //builds/<project>:build` builds a project with a **pinned, hermetic
inner Bazel**, **daemonless**, in an **isolated build root** — using only Bazel
on the host. Isolation here is at the level of *Bazel state + environment*
(Tier 1); a kernel/container tier is the next step.

### How it works

```
bazel run //builds/abseil_cpp:build
  │  (outer Bazel)
  ▼
tools/buildrunner/runner.py            # the engine, a py_binary per project
  ├─ resolves (via runfiles):
  │    @inner_bazel_linux_amd64//file  # pinned bazel 9.1.1 binary (hermetic)
  │    @absl_archive//file             # pinned abseil source tarball (sha256)
  ├─ extracts source fresh into  <build_root>/work/   (deterministic mtimes)
  ├─ appends the hermetic-LLVM overlay onto the source's MODULE.bazel
  │    (when hermetic_cc = True — see below)
  └─ exec:  bazel --batch --nohome_rc --nosystem_rc
                  --output_user_root=<build_root>/output_root
                  build --repository_cache=<build_root>/repo_cache
                  -c opt --extra_toolchains=@llvm//toolchain:all //absl/...
            (cwd = extracted workspace, scrubbed env)
```

The pinned inner Bazel binary and project source tarballs are fetched by
[`tools/fetch/extension.bzl`](../tools/fetch/extension.bzl) (the same hermetic,
sha256-pinned pattern as the `gh` CLI; linux amd64 + arm64). The `museum_build`
macro ([`builds/defs.bzl`](../builds/defs.bzl)) wires a per-project `py_binary`
around `runner.py` with that project's source + the inner Bazel as `data`.

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

### Hermetic C/C++ toolchain (overlays + `hermetic_cc`)

A `museum_build(..., hermetic_cc = True)` builds the project with a **fully
hermetic LLVM toolchain** — [hermeticbuild/hermetic-llvm][hllvm], the BCR module
`llvm`. It is *zero-sysroot*: the target libc, libc++, CRT, and compiler
runtimes are built/linked from Bazel-managed sources, so the build does **not**
use the host compiler, headers, libc, or any sysroot. (Verified: abseil compiles
with `external/llvm++.../bin/clang` and zero `/usr/bin` compiler calls.)

[hllvm]: https://github.com/hermeticbuild/hermetic-llvm

This is injected **without forking the project**, via the runner's *overlay*
mechanism (`--append RLOC=DEST`): the snippet
[`tools/buildrunner/overlays/hermetic_cc.MODULE.bazel`](../tools/buildrunner/overlays/hermetic_cc.MODULE.bazel)
(`bazel_dep(name = "llvm", ...)` + `register_toolchains(...)`) is appended onto
the extracted source's `MODULE.bazel`, and `--extra_toolchains=@llvm//toolchain:all`
forces it ahead of the project's host-autodetected toolchain. Appending is safe
and deterministic because the source is content-pinned. The same overlay hook
is the home for project-specific patches in general.

hermetic-llvm also cross-compiles (linux x86_64 ↔ aarch64, and more), which is
the natural lever for the "linux arm64 next" goal.

### Known boundaries (future work)

- **Network is open** during the inner build (to fetch BCR deps + the toolchain);
  the repository cache makes this a one-time cost. Vendoring for fully offline
  builds is possible later.
- **Optional container tier (next).** Wrap the runner in a minimal OCI image
  built with [`rules_img`](https://github.com/bazel-contrib/rules_img), run via
  a container runtime — the kickoff's original idea — for kernel-level isolation
  on top of the Tier 1 + hermetic-toolchain foundation. With the toolchain now
  hermetic, the container's marginal value is whole-process FS/network
  confinement and a deterministic home for projects with *system-package* deps,
  so it is opt-in rather than required. (`bwrap` is a lighter alternative where
  a container runtime isn't available.)

## Piece 3 — The build collection

Each project lives under `builds/<project>/` and is declared with the
`museum_build` macro. Its source is pinned in
[`tools/fetch/extension.bzl`](../tools/fetch/extension.bzl) (the kickoff's
"source as a dep in `MODULE.bazel`"), and any overlays/patches live alongside
the build (the runner has a hook for applying them; abseil needs none).

### Projects

| Project | Lang | Target | Source pin | Toolchain (all hermetic) |
|---------|------|--------|-----------|--------------------------|
| [abseil-cpp](../builds/abseil_cpp/BUILD.bazel) | C++ | `//builds/abseil_cpp:build` | release `20260526.0` | LLVM (`hermetic_cc`) |
| [copybara](../builds/copybara/BUILD.bazel) | Java | `//builds/copybara:build` | tag `v20260622` | remote JDK (rules_java) |
| [cxx](../builds/cxx/BUILD.bazel) | Rust | `//builds/cxx:build` | tag `1.0.194` | rustc (rules_rust) + LLVM |

Each verified to compile with its hermetic toolchain and **zero host-compiler
invocations**: abseil/cxx use `external/llvm++.../bin/clang`, copybara runs on a
bundled OpenJDK (host `java` absent), cxx's rustc is rules_rust's downloaded
toolchain. Go-style native deps, JVM, and Rust+C++ FFI exercise three different
toolchain provisioning paths — and each fetches darwin toolchains too, so the
collection is positioned for a macOS port.

Adding a project:

1. Add its source tarball (url + sha256 + filename) to `_PROJECT_SOURCES` in
   `tools/fetch/extension.bzl` and `use_repo(...)` it in `MODULE.bazel`.
2. Create `builds/<project>/BUILD.bazel` with a `museum_build(...)` call.
3. `bazel run //builds/<project>:build`.

The data pipeline (piece 1) feeds the choice of projects: pick well-known,
self-contained projects that already build with Bazel from `data/projects.json`.
