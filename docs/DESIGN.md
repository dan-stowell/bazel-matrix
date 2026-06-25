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
- **Dedicated state** — its own `--output_user_root` under a per-goal build root
  (default `${TMPDIR}/bazel-museum/<goal>`, override with `MUSEUM_BUILD_ROOT`).
  The host's `~/.cache/bazel` is never touched. The `--repository_cache` is the
  one exception: it's *shared* across goals (`…/bazel-museum/repo_cache`) because
  it's content-addressed (keyed by sha256), so a toolchain or source archive —
  most importantly the rate-limited macOS SDK and the hermetic LLVM tarballs — is
  fetched once and reused, instead of re-downloaded per goal (which trips
  upstream CDN rate limits and intermittently breaks darwin builds).
- **Daemonless** — `--batch`: no Bazel server survives the run.
- **No host config leakage** — `--nohome_rc --nosystem_rc`, and a scrubbed
  environment (only an explicit allowlist — `PATH`, proxy/TLS vars, `CC`/`CXX`,
  locale — is passed through).

Reruns are fast: even though the source is re-extracted, the tarball's
deterministic mtimes mean the inner action cache hits (~5 s vs ~5 min cold).

### Environments, platforms, and the goal matrix

The build layer models three independent dimensions and crosses them into
explicit, runnable targets named **`<command>_<env>_<os>_<arch>`** (e.g.
`build_rbe_linux_amd64`, `test_local_darwin_arm64`):

- **command** — `build` or `test`.
- **environment** ([`builds/environments.bzl`](../builds/environments.bzl)) —
  *where* a goal runs. Three exist: `LOCAL` (the host machine — serves one
  os/arch at a time, so each goal is gated on the host matching it via
  `target_compatible_with`), `RBE` (BuildBuddy cloud; host-independent), and
  `ACTIOND` (a local Linux RE worker — [hermeticbuild/actiond][actiond] — that
  runs actions in a VM on this host, serving linux/arm64 without leaving the
  Mac). An environment declares the platforms it can serve, the overlays it adds,
  whether it `pin_platform`s, and any per-platform flags; new ones drop in here.

[actiond]: https://github.com/hermeticbuild/actiond
- **platform** ([`builds/platforms.bzl`](../builds/platforms.bzl)) — a canonical
  `(os, arch)` with its constraints, `//builds` config_setting, and RBE
  `exec_properties`.

An **overlay** ([`builds/overlays.bzl`](../builds/overlays.bzl)) is a reusable,
named bundle of source `appends` (file → `MODULE.bazel` / `.bazelrc`), `writes`
(file copied verbatim to a path — e.g. dropping a patch + a `BUILD` marker into a
fresh package, where `appends`' leading newline would corrupt the file),
`patches` (unified diffs, `patch -p1`), `build_flags`, and `remote_header_envs`
(`ENV:HEADER` pairs the runner turns into `--remote_header=HEADER=<value>`, to
inject secrets like an API key without committing them).

**Patching a dependency module without forking it.** Some fixes live in a
project's *dependencies* (a BCR module), not the project. We ride the latest
published module and carry the fix as a `single_version_override(patches=…)`: the
overlay `appends` the override onto `MODULE.bazel` and `writes` the patch (plus a
`BUILD` marker) into a `museum_patches/` package the override references. This is
how `HERMETIC_LLVM` backports [hermetic-llvm#642][hl642] (pass `-isysroot` on
macOS so a stray `SDKROOT` can't override the hermetic SDK) onto `llvm` 0.8.9, and
how `RULES_RUST_SYSROOT_FIX` backports [rules_rust#4101][rr4101] (prefix `${pwd}`
onto the `-isysroot <path>` that fix now emits) onto `rules_rust` 0.68.1 — so Rust
+ macOS builds work today, before either PR ships. Both drop out once released.

[hl642]: https://github.com/hermeticbuild/hermetic-llvm/pull/642
[rr4101]: https://github.com/bazelbuild/rules_rust/pull/4101

A **project** (`museum_project`) pins a source tarball + `toolchains` (overlays
applied to every goal, e.g. `HERMETIC_LLVM`), the `environments` it targets, and
a `build`/`test` spec. It emits one goal per **runnable** cell of
environments × platforms × commands; `test_spec.exclude_on` drops target patterns
per-environment. Only runnable cells appear: `RBE` lists the platforms it has
executors for, and `LOCAL` goals are inert off their host.

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

The `RBE` environment (overlay `BUILDBUDDY_RBE`, [`builds/overlays.bzl`](../builds/overlays.bzl))
runs builds *and* tests on BuildBuddy's cloud executors, host-independently —
identical from a linux or macOS orchestrator. It emits `{build,test}_rbe_<os>_<arch>`
goals.

We deliberately **do not use `toolchains_buildbuddy`**. Because `HERMETIC_LLVM`
is zero-sysroot, the compiler and all inputs are content-addressed and uploaded
to the CAS, so they run **image-agnostically** on the executor — hermetic-llvm
even builds its own glibc 2.28 + compiler-rt from source *on the executor*. The
API key is injected as a `--remote_header` by the runner (never committed).

The execution+target **platform is pinned explicitly** rather than inherited from
the orchestrator. `museum_project` injects a `museum_rbe/` package (one
`platform()` per os/arch, carrying the executor `container-image`/pool as
`exec_properties` — see
[`rbe_platforms.BUILD.bazel`](../tools/buildrunner/overlays/rbe_platforms.BUILD.bazel))
and pins `--platforms` / `--extra_execution_platforms` / `--host_platform` to it.
This is what makes RBE host-neutral and keeps host-baked state from leaking onto
the executor. Two flags matter for that:

- `--host_platform` is pinned to the executor platform so **host/exec tool**
  resolution (and the legacy `--host_cpu`) follows the executor — otherwise a
  tool built for the orchestrator (e.g. a darwin `buildifier`, or `ijar`'s
  `zipper`) is shipped to a linux executor and fails.
- `--spawn_strategy=remote,sandboxed,local` drops Bazel's default **`worker`**
  strategy: persistent workers run *locally*, so a pinned remote platform would
  make a local worker try to exec the executor's toolchain (e.g. the linux remote
  JDK) on the orchestrator. `--experimental_platform_in_output_dir` makes the
  output tree name directories by the real target platform (not the legacy
  `--cpu`), so this class of bug is visible.

Verified **from a macOS arm64 host** against linux/**amd64** executors: abseil and
cxx `build`/`test` green; copybara `build` green. Tests execute remotely too:

| Project | `test_rbe_linux_amd64` | excluded on the executor (kept locally) |
|---------|------------------------|------------------------------------------|
| abseil-cpp | 248/248 pass | 3 cctz/time tests — executor lacks system tzdata |
| cxx | 1/1 pass | — |
| copybara | from a linux host | from macOS, `buildifier_prebuilt` registers only the host (darwin) toolchain, so most tests fail to resolve a toolchain — a cross-host wart, deferred |

The linux exclusions are **executor-environment** differences (missing tzdata,
root uid), not real failures — the local `test` goals still run them.

**linux/arm64 on RBE — builds yes, execution no.** `linux_arm64` is in
`RBE.platforms`, routed to BuildBuddy's arm64 executor pool via an `Arch=arm64`
exec property. `build_rbe_linux_arm64` is **green** (abseil, 4160 actions, fully
cross-compiling the hermetic LLVM toolchain to aarch64). But anything that has to
*run* an arm64 binary on the executor fails: `test_rbe_linux_arm64`'s test
binaries come back "No such file or directory" from the test wrapper (0/248,
where amd64 with identical flags is 248/248), and cxx's Rust toolchain dies on
`bootstrap_process_wrapper.sh: Exec format error`. So arm64 *target* compilation
works on the cloud, but arm64 *execution* on the public arm64 pool does not (an
executor-side wart we don't control). The reliable way to **build and test**
linux/arm64 from this Mac is the `actiond` environment below — a real local arm64
VM — not RBE.

**macOS arm64 on RBE (in progress).** This is "build & test Darwin on RBE,"
distinct from *orchestrating from* a Mac (which works above). Two findings from
probing it, each correcting an earlier assumption:

- **Executors exist.** A remote-only `genrule` pinned to a darwin exec platform
  ran `uname -sm` → `Darwin arm64` on a real macOS executor. So executors are not
  the blocker, and the macOS SDK download isn't either (hermetic-llvm fetches its
  own pinned SDK, with a mirror; local darwin builds succeed through it).
- **The blocker is a toolchain layering issue, in two layers:**
  - *Layer 1 (museum-side, ready):* building the toolchain's own runtimes
    (compiler-rt, libunwind…) otherwise falls through to `apple_support`/host
    Xcode. `--@llvm//toolchain:source=bootstrapped` makes them compile with
    hermetic-llvm's own clang instead. Wired as a per-platform flag on the `RBE`
    environment for `darwin_arm64`; confirmed it gets the build past compiler-rt.
  - *Layer 2 (upstream, open):* hermetic-llvm's internal host **tools** (e.g.
    `tools/internal/static_library_validator`) still compile via `apple_support`.
    Its `cxx_builtin_include_directories` are baked from the **orchestrator's**
    Xcode (`/Applications/Xcode.app/…`) but the action runs on the executor
    (`/Applications/Xcode_26.5.0.app/…`); the paths differ only by the `.app`
    name, so Bazel's absolute-path-inclusion check rejects the executor's headers.
    Fixes: align the executor's Xcode path/`DEVELOPER_DIR` with the orchestrator's
    (executor-image config), or route those tool compiles through hermetic-llvm's
    downloaded SDK (upstream). Until then `darwin_arm64` is left out of
    `RBE.platforms`.

Both copybara-from-macOS and the Layer 2 darwin issue are the same shape as the
local host-tooling notes below: a host-configured tool that doesn't survive the
trip to a differently-configured executor.

### actiond — a local Linux arm64 worker (build & test linux from the Mac)

[actiond][actiond] is a local Remote Execution worker + cache: it boots a small
Linux VM and runs Bazel actions inside it, so the host acts as a local linux
remote-execution worker. The museum models it as the `ACTIOND` environment
([`builds/environments.bzl`](../builds/environments.bzl)) — a target
`{env, os, arch}` exactly like `rbe`, emitting `{build,test}_actiond_linux_arm64`
goals. It is the museum's answer to "build *and test* linux/arm64 from this Mac":
the VM is real arm64 (Apple silicon), so unlike RBE's amd64 pool it can actually
*run* arm64 binaries. Structurally it's RBE pointed at a local endpoint:
`--remote_executor`/`--remote_cache=grpc://127.0.0.1:8980`, everything remote (no
local fallback — the pinned platform is linux, unrunnable on macOS), the same
zero-sysroot `HERMETIC_LLVM` cross-targeting linux so the whole compiler uploads
to the worker's CAS and runs in its empty VM chroot.

The worker is a persistent local *service* (like BuildBuddy, but on-box), so it
lives outside the daemonless inner builds. Start it once:

```
bazel run //tools/actiond:serve      # boots the VM, serves grpc on :8980
```

The binary is pinned hermetically (sha256, same pattern as `gh`/inner-bazel;
[`tools/actiond:extension.bzl`](../tools/actiond/extension.bzl)); the VM kernel,
initramfs, and runtime image are embedded in it. Two things the worker needs that
a cloud pool doesn't:

- **Memory.** The first build compiles the entire hermetic LLVM toolchain
  (compiler-rt/libcxx/libunwind) from source; at cloud concurrency the
  memory-heavy clang/llvm-ar actions OOM-kill inside a small VM. The serve
  wrapper gives the guest **14 GiB** (`--memory-mib`, override with
  `MUSEUM_ACTIOND_MEMORY_MIB`) and the overlay keeps inner `--jobs` modest (8).
- **Exec properties.** actiond runs each action in an *empty* chroot, so
  non-hermetic actions request what they need via exec properties — and those
  must live on the **execution platform** (`museum_rbe/`, see
  [`rbe_platforms.BUILD.bazel`](../tools/buildrunner/overlays/rbe_platforms.BUILD.bazel)),
  *not* `--remote_default_exec_properties`, which Bazel ignores once a platform
  sets any `exec_properties` (ours sets `OSFamily`/`Arch`). The `linux_arm64`
  platform carries `requires-bash=` (mounts the embedded bash for shell-script
  actions — the test wrappers `test-setup.sh`/`generate-xml.sh`, and rules_rust's
  `bootstrap_process_wrapper.sh`; without it they exit 127) and `libc=glibc2.39`
  (mounts a glibc for dynamically-linked tool binaries; backward-compatible, so
  the newest embedded one satisfies older needs). BuildBuddy ignores both keys,
  so they're harmless on the RBE side of the shared platform.

Verified on this macOS arm64 host: the worker's VM boots and serves, and
`build_actiond_linux_arm64` for abseil is **green** — 2072 actions, the full
hermetic LLVM toolchain compiled from source *inside the VM* and the library
graph built for aarch64-linux, entirely on-box. (Each change to the platform's
`exec_properties` re-keys every remote action, so the next build recompiles the
toolchain from scratch — a one-time cost while tuning.)

**cxx (Rust) on actiond is blocked one layer down**, not by our patches: the
exec properties get rules_rust's prebuilt `rustc` to *start* (bash + glibc
mounted), but it then dies on `libgcc_s.so.1: cannot open shared object file` —
a GCC runtime lib the minimal VM image doesn't ship and that `libc=glibc…`
doesn't include. So Rust on the local arm64 worker needs a runtime carrying
`libgcc_s` (or a fully-static rustc); the C/C++ projects, which link the hermetic
compiler-rt instead of libgcc, don't hit this.

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
"source as a dep in `MODULE.bazel`"), and overlays/patches attach per goal. Each
project emits the `<command>_<env>_<os>_<arch>` matrix (currently
`{build,test}_{local_darwin_arm64 | local_linux_amd64 | rbe_linux_amd64}`).

### Projects

| Project | Lang | Source pin | Toolchain (all hermetic) |
|---------|------|-----------|--------------------------|
| [abseil-cpp](../builds/abseil_cpp/BUILD.bazel) | C++ | release `20260526.0` | LLVM (`HERMETIC_LLVM`) |
| [copybara](../builds/copybara/BUILD.bazel) | Java | tag `v20260622` | remote JDK (rules_java) + LLVM (for `ijar`) |
| [cxx](../builds/cxx/BUILD.bazel) | Rust | tag `1.0.194` | rustc (rules_rust) + LLVM |

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
