# bazel-museum

**A collection of real open-source projects you can build and test *as they
ship* — with nothing but [bazelisk] and the handful of host tools that
real-world Bazel projects quietly assume. The point is to enumerate exactly what
those tools are.**

Almost no Bazel project in the wild builds with bazelisk *alone*: the moment
anything compiles, Bazel's C/C++ toolchain auto-configuration probes the host
for `gcc`/`cc` — and that's just the start (some projects also reach for a JDK,
python, git, or curl). This repo pins that "ordinary CI machine" into a single
container image built **entirely with Bazel** ([rules_img] + [rules_distroless]),
then builds and tests each project's *upstream* `MODULE`/`BUILD` inside it — no
overlays, no patches, no injected toolchains. What works, and what host tool
each project leans on, is the result.

> Looking for the hermetic-by-injection builds, remote execution on BuildBuddy,
> the local `actiond` RE worker, or the project-discovery pipeline? Those go
> past this headline goal and live under **[explorations/](explorations)**.

[bazelisk]: https://github.com/bazelbuild/bazelisk
[rules_img]: https://github.com/bazel-contrib/rules_img
[rules_distroless]: https://github.com/bazel-contrib/rules_distroless

## Quick start

All you need is **bazelisk** — no compiler, no docker, no daemon, no root. The
toolchain lives in the image; the image runs **rootless and daemonless** via a
pinned `crun` (everything is fetched by Bazel).

```sh
# 1. Get bazelisk (it becomes your `bazel`; it downloads the exact Bazel each
#    project pins). On a bare Linux box:
sudo curl -fsSL -o /usr/local/bin/bazel \
    https://github.com/bazelbuild/bazelisk/releases/download/v1.25.0/bazelisk-linux-amd64
sudo chmod +x /usr/local/bin/bazel
#    (macOS/Windows/other arches: see the bazelisk releases page.)

# 2. Stage the run environment once: rules_img builds the image (no daemon) and
#    this extracts its rootfs + the pinned crun runtime into ~/.cache/wild:
bazel run //wild/image:rootfs

# 3. Build and test any project, exactly as upstream ships it (rootless crun):
bazel run //projects/re2:build      # fetches re2's pinned source, runs its own BUILD
bazel run //projects/re2:test       # runs re2's upstream test suite in the image
```

Each `//projects/<project>:build` / `:test` target fetches the project's pinned
source, runs `bazelisk` against the upstream `MODULE`/`BUILD` inside the image
(via [crun](https://github.com/containers/crun) in a rootless OCI bundle) with
the project's known-good Bazel pinned. The first build compiles from scratch;
reruns hit a warm cache.

> **Daemonless by default.** The runtime is a pinned, statically-linked `crun`
> ([`//tools/crun`](tools/crun)) fetched by Bazel — no host runtime, no dockerd,
> no root (single-id user namespace). Prefer Docker? Set `WILD_RUNTIME=docker`
> and `bazel run //wild/image:load` once instead of `:rootfs`.

## Projects that build as they are

<!-- BEGIN GENERATED TABLE (wild/_readme_table.py) -->
| Project | Description | Bazel | Build | Test |
|---------|-------------|:-----:|-------|------|
| [abseil-cpp](https://github.com/abseil/abseil-cpp) | Google's C++ standard-library extensions | 9.1.1 | `bazel run //projects/abseil_cpp:build` | `bazel run //projects/abseil_cpp:test` |
| [bazel](https://github.com/bazelbuild/bazel) | The Bazel build system itself (Java/C++) | 9.1.1 | `bazel run //projects/bazel:build` | `bazel run //projects/bazel:test` (14/15 pass) |
| [BoringSSL](https://github.com/google/boringssl) | Google's fork of OpenSSL | 9.1.1 | `bazel run //projects/boringssl:build` | `bazel run //projects/boringssl:test` |
| [buildtools](https://github.com/bazelbuild/buildtools) | Bazel BUILD formatter/linter, buildifier (Go) | 8.7.0 | `bazel run //projects/buildtools:build` | `bazel run //projects/buildtools:test` |
| [Catch2](https://github.com/catchorg/Catch2) | C++ unit-testing framework | 9.1.1 | `bazel run //projects/catch2:build` | — (test fails as-is) |
| [cctz](https://github.com/google/cctz) | C++ civil-time and time-zone library | 8.7.0 | `bazel run //projects/cctz:build` | `bazel run //projects/cctz:test` |
| [CLI11](https://github.com/CLIUtils/CLI11) | Command-line parser for C++11 | 8.7.0 | `bazel run //projects/cli11:build` | `bazel run //projects/cli11:test` |
| [copybara](https://github.com/google/copybara) | Transforms and moves code between repositories (Java) | 9.1.1 | `bazel run //projects/copybara:build` | `bazel run //projects/copybara:test` (216/220 pass) |
| [cpu_features](https://github.com/google/cpu_features) | Cross-platform CPU feature detection | 8.7.0 | `bazel run //projects/cpu_features:build` | `bazel run //projects/cpu_features:test` |
| [cxx](https://github.com/dtolnay/cxx) | Safe interop between Rust and C++ (Rust) | 9.1.1 | `bazel run //projects/cxx:build` | — (test fails as-is) |
| [fast_float](https://github.com/fastfloat/fast_float) | Fast number parsing from strings | 8.7.0 | `bazel run //projects/fast_float:build` | `bazel run //projects/fast_float:test` |
| [FlatBuffers](https://github.com/google/flatbuffers) | Memory-efficient serialization library | 8.7.0 | `bazel run //projects/flatbuffers:build` | `bazel run //projects/flatbuffers:test` |
| [FTXUI](https://github.com/ArthurSonzogni/FTXUI) | Functional terminal-UI library for C++ | 8.7.0 | `bazel run //projects/ftxui:build` | `bazel run //projects/ftxui:test` |
| [glog](https://github.com/google/glog) | Google application-level logging library | 8.7.0 | `bazel run //projects/glog:build` | `bazel run //projects/glog:test` |
| [google/benchmark](https://github.com/google/benchmark) | Microbenchmark support library | 8.7.0 | `bazel run //projects/benchmark:build` | `bazel run //projects/benchmark:test` |
| [GoogleTest](https://github.com/google/googletest) | Google's C++ test & mocking framework | 8.7.0 | `bazel run //projects/googletest:build` | `bazel run //projects/googletest:test` |
| [gperftools](https://github.com/gperftools/gperftools) | tcmalloc and performance profilers | 8.7.0 | `bazel run //projects/gperftools:build` | `bazel run //projects/gperftools:test` |
| [highway](https://github.com/google/highway) | Portable SIMD/vector intrinsics | 8.7.0 | `bazel run //projects/highway:build` | `bazel run //projects/highway:test` |
| [jsoncpp](https://github.com/open-source-parsers/jsoncpp) | C++ library for reading/writing JSON | 9.1.1 | `bazel run //projects/jsoncpp:build` | `bazel run //projects/jsoncpp:test` |
| [jsonnet](https://github.com/google/jsonnet) | Data-templating language | 8.7.0 | `bazel run //projects/jsonnet:build` | `bazel run //projects/jsonnet:test` |
| [magic_enum](https://github.com/Neargye/magic_enum) | Static reflection for C++ enums | 9.1.1 | `bazel run //projects/magic_enum:build` | — (test fails as-is) |
| [nlohmann/json](https://github.com/nlohmann/json) | JSON for Modern C++ | 9.1.1 | `bazel run //projects/json:build` | — (no upstream test target) |
| [nsync](https://github.com/google/nsync) | C library of synchronization primitives | 8.7.0 | `bazel run //projects/nsync:build` | `bazel run //projects/nsync:test` |
| [oneTBB](https://github.com/uxlfoundation/oneTBB) | Intel's Threading Building Blocks | 8.7.0 | `bazel run //projects/onetbb:build` | `bazel run //projects/onetbb:test` |
| [OpenCC](https://github.com/BYVoid/OpenCC) | Traditional/Simplified Chinese conversion | 8.7.0 | `bazel run //projects/opencc:build` | — (no upstream test target) |
| [OR-Tools](https://github.com/google/or-tools) | Google's optimization suite (CP-SAT) | 8.7.0 | `bazel run //projects/ortools:build` | `bazel run //projects/ortools:test` (88/89 pass) |
| [protobuf](https://github.com/protocolbuffers/protobuf) | Protocol Buffers serialization | 9.1.1 | `bazel run //projects/protobuf:build` | `bazel run //projects/protobuf:test` (100/101 pass) |
| [re2](https://github.com/google/re2) | Fast, safe regular-expression engine | 8.7.0 | `bazel run //projects/re2:build` | `bazel run //projects/re2:test` |
| [snappy](https://github.com/google/snappy) | Fast compression/decompression library | 8.7.0 | `bazel run //projects/snappy:build` | `bazel run //projects/snappy:test` |
| [zlib](https://github.com/madler/zlib) | The zlib compression library | 9.1.1 | `bazel run //projects/zlib:build` | — (no upstream test target) |

_30 projects build as they are; 24 also run their upstream test suite in the image — most fully green, a few with environment-sensitive local failures noted inline (`N/M pass`)._

### Doesn't build as-is

- **brotli** — ships no `MODULE.bazel` (WORKSPACE-only), so bzlmod sees no workspace
- **brotli (Go)** — same archive as brotli — no `MODULE.bazel`
- **doctest** — root `//:doctest` uses `includes=["."]`, rejected for the main module (it's meant to be consumed as a dep)
- **gRPC** — its `tools/bazel` wrapper downloads its own Bazel, which then can't find the host `gcc`
<!-- END GENERATED TABLE -->

The Bazel column is the version bazelisk pins for that project (its known-good
inner). Most projects that don't pin a `.bazelversion` need it: bazelisk would
otherwise pick the latest Bazel, which dropped the autoloaded `cc_*`/`sh_test`
built-ins and breaks their `load`-less BUILD files.

## The host tools, enumerated

The whole exercise is to make the host dependency *explicit*. With **bazelisk
alone** — a strict image of a libc, CA certs, and the bazelisk binary, nothing
else ([`bazel run //wild/image:strict_load`](wild/image/BUILD.bazel)) — **zero**
of these projects build. The wall is always the same:

```
Auto-Configuration Error: Cannot find gcc or CC; either correct your path
or set the CC environment variable
```

Even pure-Go (buildifier) and Rust (`cxx`) projects hit it — `rules_go` and
`rules_rust` eagerly configure a host C toolchain for cgo/linking. So the image
([`//wild/image`](wild/image)) carries the set of host tools a real CI runner has
and that these projects reach for:

| Tool | Why a Bazel project reaches for it | Seen with |
|------|------------------------------------|-----------|
| **gcc / g++** (build-essential) | Bazel's C/C++ toolchain auto-configuration | **every compiling project** — the universal wall (proven by the strict image) |
| **python3** | build-time scripts in the build graph | protobuf, grpc, … |
| **git** | a `git_repository` fetch at build time | ortools |
| **curl** | a `tools/bazel` wrapper that downloads its own Bazel | grpc |
| **zip / unzip** | genrules that shell out to archivers | bazel (install-base) |
| **JDK** (default-jdk-headless) | host `java` for Java projects / genrules | copybara, bazel (a generic CI machine has one) |

That table *is* the finding: the gap between "has a green BUILD" and "builds on
a clean machine" is a short, nameable list of host assumptions — and the
container is where they're pinned down reproducibly. Only the compiler is
*proven* universal here (remove it → the strict image fails everything); the
rest are the assumptions these specific projects exercised.

## How it works

- **[`wild/image`](wild/image)** — the container, assembled entirely with Bazel.
  [rules_img] stacks the layers onto a pinned `debian:bookworm-slim`; the host
  toolchain rides on top as hermetic `.deb` layers resolved by
  [rules_distroless] from a pinned Debian snapshot
  ([`toolchain.yaml`](wild/image/toolchain.yaml)). No `apt install` at image
  build time, no Dockerfile.
- **[`projects/<project>`](projects)** — one `:build` and `:test` target per
  project, generated by [`wild/gen_targets.py`](wild/gen_targets.py) from the
  project list. Each runs [`projects/run.sh`](projects/run.sh): fetch the pinned
  source (verified against [`tools/fetch`](tools/fetch)), mount it, run `bazelisk`
  in the image.
- **Daemonless runtime** — [`wild/image/rootfs.sh`](wild/image/rootfs.sh) pulls
  the image's rootfs straight from the OCI layout rules_img builds (no daemon)
  and stages it with a pinned static `crun` ([`//tools/crun`](tools/crun)).
  `run.sh` then runs each build in a rootless OCI bundle — no dockerd, no root.
  (`WILD_RUNTIME=docker` switches back to a `docker run` against `:load`.)
- **[`wild/verify.sh`](wild/verify.sh)** — the build+test sweep that produces the
  table above; a test command is listed only when its upstream suite actually runs
  and passes in the image (partial passes are annotated `N/M pass` inline).

## Explorations

Earlier directions that proved out real capability but go beyond the headline
goal are documented under **[explorations/](explorations)**:

- **[The hermetic museum](explorations#1-the-hermetic-museum-builds)** — the same
  projects built *hermetically by injection* (pinned inner Bazel + fully-hermetic
  LLVM, no host toolchain at all), including Bazel itself.
- **[Remote execution on BuildBuddy](explorations#2-remote-execution-on-buildbuddy-rbe)**
  and **[actiond](explorations#3-actiond--a-local-linux-re-worker-toolsactiond)** —
  the hermetic builds run on cloud and local RE.
- **[The discovery pipeline](explorations#4-the-discovery-pipeline-pipeline)** —
  how the projects were chosen, ranked by recognition × maintained × buildability.

See [docs/DESIGN.md](docs/DESIGN.md) for the hermetic architecture and
[docs/KICKOFF.md](docs/KICKOFF.md) for the project's original intent.
