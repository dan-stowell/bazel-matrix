# bazel-museum

**Clone onto any machine that has only Bazel, and build & test 29 real
open-source projects — including Bazel itself — across 3 execution backends, 2
operating systems, and 2 CPU architectures.** No host compiler, no host Python,
no `gh`, no daemons — every toolchain is hermetic and pinned, and the inner
Bazel is pinned too.

```sh
bazel run //builds/abseil_cpp:test                       # 251 tests, hermetic LLVM, on this host
bazel run //builds/abseil_cpp:test_rbe_linux_amd64       # …the same, on BuildBuddy's cloud
bazel run //builds/abseil_cpp:build_actiond_linux_arm64  # …or in a local Linux VM
```

### What builds where

Each project is a pinned source tarball + hermetic toolchain, built by a pinned,
daemonless inner Bazel in an isolated build root. ✅ = wired and green; most
projects also run their upstream test suite hermetically (numbers below).

| Project | Lang | Toolchain | local | BuildBuddy RBE | actiond (local VM) |
|---------|------|-----------|:-----:|:--------------:|:------------------:|
| [abseil-cpp](builds/abseil_cpp/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [protobuf](builds/protobuf/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [grpc](builds/grpc/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [googletest](builds/googletest/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [flatbuffers](builds/flatbuffers/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [OR-Tools](builds/ortools/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [Catch2](builds/catch2/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [brotli](builds/brotli/BUILD.bazel) | C++ / Go | hermetic LLVM | ✅ | ✅ | ✅ |
| [nlohmann/json](builds/json/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | ✅ |
| [re2](builds/re2/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [snappy](builds/snappy/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [google/benchmark](builds/benchmark/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [zlib](builds/zlib/BUILD.bazel) | C | hermetic LLVM | ✅ | ✅ | — |
| [highway](builds/highway/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [jsoncpp](builds/jsoncpp/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [magic_enum](builds/magic_enum/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [FTXUI](builds/ftxui/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [jsonnet](builds/jsonnet/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [gperftools](builds/gperftools/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [OpenCC](builds/opencc/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [cpu_features](builds/cpu_features/BUILD.bazel) | C | hermetic LLVM | ✅ | ✅ | — |
| [fast_float](builds/fast_float/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [CLI11](builds/cli11/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [glog](builds/glog/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [oneTBB](builds/onetbb/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [doctest](builds/doctest/BUILD.bazel) | C++ | hermetic LLVM | ✅ | ✅ | — |
| [copybara](builds/copybara/BUILD.bazel) | Java | rules_java + hermetic JDK | ✅ | ✅ | — |
| [cxx](builds/cxx/BUILD.bazel) | Rust | rules_rust + hermetic LLVM | ✅ | ✅ | ✅ |
| [bazel](builds/bazel/BUILD.bazel) | Java / C++ | hermetic LLVM + bundled JDK | ✅¹ | ✅¹ | —² |

¹ **Bazel itself** — `//src:bazel-bin`, 6768 actions, built with the hermetic
LLVM toolchain (Java side uses Bazel's bundled JDK), green both locally and on
RBE. Its genrules shell out to `zip` (72×); rather than require a host `zip`, the
museum builds one from Info-ZIP source with hermetic LLVM
([`//tools/zip`](tools/zip)) and stages it on the inner build's PATH (the
`HERMETIC_ZIP` overlay) — verified green with `zip` absent from the host (on RBE
the executor image's own `zip` serves instead). The **test** goal runs Bazel's
C++ client unit tests (`//src/test/cpp/...`): **15/15** local, **14/14** on RBE
(`file_test`, whose permission/large-file asserts invert under the root executor,
runs local-only).

² **Not actiond yet.** The C++ tests run there, but Bazel's install-base genrule
calls system `zip`, which actiond's minimal guest chroot lacks — and the
`--tool` lever stages `zip` on a *local* PATH that doesn't reach the remote
guest. Closing it needs `zip` as a real action input in the guest.

**Dimensions:** *local* = the host itself (linux x86_64 or macOS arm64, one at a
time). *RBE* = BuildBuddy's cloud executors (linux amd64/arm64 + darwin arm64),
host-neutral. *actiond* = a Linux VM on this machine ([hermeticbuild/actiond])
that runs arm64 (or amd64) actions locally. New backends, caches, OSes, and
arches drop into [`builds/environments.bzl`](builds/environments.bzl) and
[`builds/platforms.bzl`](builds/platforms.bzl).

[hermeticbuild/actiond]: https://github.com/hermeticbuild/actiond

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
bazel run //builds/protobuf:test_local_linux_amd64     # 101/102 pass (1 skipped)
bazel run //builds/googletest:test_local_linux_amd64   # 41/41 pass
bazel run //builds/flatbuffers:test_local_linux_amd64  # 1/1 pass (monolithic suite)
bazel run //builds/catch2:test_local_linux_amd64       # 500 pass / 6 skipped (self-test)
bazel run //builds/ortools:test_local_linux_amd64      # 89/89 pass (CP-SAT core)
bazel run //builds/grpc:test_local_linux_amd64         # 50 pass / 50 skipped (//test/core/promise/...)
bazel run //builds/brotli_go:test_local_linux_amd64    # 4/4 go_test (cgo round-trips the C lib)
# Build-only: nlohmann/json — it's a CMake project whose BUILD.bazel is a
# library-consumption shim; its doctest suite has no Bazel test rules and no
# minimal way to run it under `bazel test` (Gazelle is Go/proto-only).

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
