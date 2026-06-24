# bazel-museum

A collection of reproducible **Bazel builds of public open-source projects**.

Clone onto a host that has only Bazel (via [`bazelisk`]) and you can build and
run everything inside — no host Python, no host `gh`, no daemons assumed.

[`bazelisk`]: https://github.com/bazelbuild/bazelisk

## Status

| Piece | What | Status |
|-------|------|--------|
| 1 | **Data pipeline** — discover public projects that build with Bazel | ✅ built |
| 2 | **Run Bazel builds in isolation** — hermetic, daemonless inner build | ✅ built (Tier 1; container next) |
| 3 | **The build collection** — first project: abseil-cpp | ✅ first build (abseil-cpp) |

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
# in an isolated build root (no host Bazel state touched):
bazel run //builds/abseil_cpp:build

# Build a subset (overrides the default targets):
bazel run //builds/abseil_cpp:build -- //absl/strings:strings

# Pass flags through to the inner build:
bazel run //builds/abseil_cpp:build -- --verbose_failures
```

First run compiles from scratch (~5 min); reruns hit the inner action cache
(~5 s). See [docs/DESIGN.md](docs/DESIGN.md#piece-2--running-bazel-builds-in-isolation-built)
for how the isolation works.
