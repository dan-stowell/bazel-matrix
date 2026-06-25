# bazel-museum

A collection of reproducible **Bazel builds of public open-source projects**.

Clone onto a host that has only Bazel (via [`bazelisk`]) and you can build and
run everything inside — no host Python, no host `gh`, no daemons assumed.

[`bazelisk`]: https://github.com/bazelbuild/bazelisk

## Status

| Piece | What | Status |
|-------|------|--------|
| 1 | **Data pipeline** — discover *and rank* public projects that build with Bazel | ✅ built |
| 2 | **Run Bazel builds + tests in isolation** — daemonless, hermetic toolchains, composable overlays, BuildBuddy RBE | ✅ built (RBE on linux; macOS RBE next) |
| 3 | **The build collection** — projects across toolchains, each with build/test + remote build/test | ✅ abseil-cpp, protobuf, grpc, googletest, nlohmann/json, Catch2, flatbuffers, OR-Tools, brotli (C++), copybara (Java), cxx (Rust) |

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
classified, enriched snapshot of public projects that build with Bazel. Each
project carries a `candidate_score` (recognition × still-maintained ×
buildability) so the next project to add is a ranking, not a guess.

```sh
# Order the universe of next candidates from the snapshot (offline, no network):
bazel run //pipeline:rank                    # top 30, excluding what's already in
bazel run //pipeline:rank -- --by-language   # best-per-toolchain coverage view
bazel run //pipeline:rank -- --language C++ --top 50
```

Buildability signals: `in_bcr` (a Bazel Central Registry module exists — someone
keeps a build green) and `first_party_bazel` (the repo itself ships Bazel build
files, vs. a BCR *port* of a CMake/autotools project). `gather` probes the
latter for projects above `--detect-bazel-min-stars` (default 1000).

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

# Other projects / toolchains (goals are <command>_<env>_<os>_<arch>):
bazel run //builds/protobuf:build_local_linux_amd64    # C++ — protoc + runtime
bazel run //builds/grpc:build_local_linux_amd64        # C++ — grpc + grpc++ (Bazel 8.7 inner)
bazel run //builds/googletest:build_local_linux_amd64  # C++ — gtest (+gmock)
bazel run //builds/json:build_local_linux_amd64        # C++ — nlohmann/json (header-only)
bazel run //builds/catch2:build_local_linux_amd64      # C++ — Catch2 framework
bazel run //builds/flatbuffers:build_local_linux_amd64 # C++ — flatc + runtime (Bazel 8.7 inner)
bazel run //builds/ortools:build_local_linux_amd64     # C++ — OR-Tools CP-SAT (Bazel 8.7 inner)
bazel run //builds/brotli:build_local_linux_amd64      # C++ — brotli CLI + libs (Bazel 8.7 inner)
bazel run //builds/copybara:build_local_linux_amd64    # Java — rules_java + hermetic JDK
bazel run //builds/cxx:build_local_linux_amd64         # Rust — rules_rust + hermetic LLVM

# Run each project's tests, hermetically (no host toolchain):
bazel run //builds/abseil_cpp:test  # 251/251 pass
bazel run //builds/cxx:test         # 1/1 pass
bazel run //builds/copybara:test    # 220/220 pass (Mercurial tests excluded)
bazel run //builds/googletest:test_local_linux_amd64   # 41/41 pass
bazel run //builds/flatbuffers:test_local_linux_amd64  # 1/1 pass (monolithic suite)
bazel run //builds/catch2:test_local_linux_amd64       # 500 pass / 6 skipped (self-test)
bazel run //builds/ortools:test_local_linux_amd64      # 89/89 pass (CP-SAT core)
# Build-only — no faithful Bazel test goal: grpc (549 network/polling tests, a
# separate effort), nlohmann/json & brotli (upstream tests are CMake/Go, not Bazel).

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
