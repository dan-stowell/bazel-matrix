# bazel-museum

A collection of reproducible **Bazel builds of public open-source projects**.

Clone onto a host that has only Bazel (via [`bazelisk`]) and you can build and
run everything inside — no host Python, no host `gh`, no daemons assumed.

[`bazelisk`]: https://github.com/bazelbuild/bazelisk

## Status

| Piece | What | Status |
|-------|------|--------|
| 1 | **Data pipeline** — discover public projects that build with Bazel | ✅ built |
| 2 | **Run Bazel builds + tests in isolation** — daemonless, hermetic toolchains, composable overlays, BuildBuddy RBE | ✅ built (RBE on linux; macOS RBE next) |
| 3 | **The build collection** — 3 projects across 3 toolchains, each with build/test + remote build/test | ✅ abseil-cpp (C++), copybara (Java), cxx (Rust) |

See [docs/DESIGN.md](docs/DESIGN.md) for the architecture and
[docs/KICKOFF.md](docs/KICKOFF.md) for the project's intent.

## Quick start

```sh
# Discover projects (fetches awesome-bazel lists + the Bazel Central Registry,
# enriches with GitHub stars/metadata via a hermetic gh) and write the snapshot:
bazel run //pipeline:gather

# Offline (no GitHub API calls):
bazel run //pipeline:gather -- --enrich=none
```

The result lands in [`data/projects.json`](data/projects.json): a deduped,
classified, enriched snapshot of public projects that build with Bazel.

Enrichment authenticates GitHub via a hermetic, pinned `gh` (downloaded as a
Bazel dependency). It uses `GH_TOKEN`/`GITHUB_TOKEN` if set, otherwise the
host's `gh auth` credentials. Pass one explicitly with
`GH_TOKEN=… bazel run //pipeline:gather`.

### Build a project in isolation

```sh
# Build all of abseil-cpp with a pinned, hermetic inner Bazel, daemonless,
# in an isolated build root, using a fully-hermetic LLVM toolchain (no host
# compiler/sysroot, no host Bazel state touched):
bazel run //builds/abseil_cpp:build

# Build a subset (overrides the default targets):
bazel run //builds/abseil_cpp:build -- //absl/strings:strings

# Pass flags through to the inner build:
bazel run //builds/abseil_cpp:build -- --verbose_failures

# Other projects / toolchains:
bazel run //builds/copybara:build   # Java  — rules_java + hermetic remote JDK
bazel run //builds/cxx:build        # Rust  — rules_rust + hermetic LLVM

# Run each project's tests, hermetically (no host toolchain):
bazel run //builds/abseil_cpp:test  # 251/251 pass
bazel run //builds/cxx:test         # 1/1 pass
bazel run //builds/copybara:test    # 220/220 pass (Mercurial tests excluded)

# Build AND test on BuildBuddy remote execution (no toolchains_buildbuddy;
# hermetic-llvm runs on the executors). Needs BUILDBUDDY_API_KEY in the env:
bazel run //builds/abseil_cpp:build.remote
bazel run //builds/abseil_cpp:test.remote   # 248/248 pass remotely
bazel run //builds/cxx:test.remote
bazel run //builds/copybara:test.remote
```

First run compiles from scratch (~5 min); reruns hit the inner action cache
(~5 s). See [docs/DESIGN.md](docs/DESIGN.md#piece-2--running-bazel-builds-in-isolation-built)
for how the isolation works.
