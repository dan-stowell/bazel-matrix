# bazel-museum: reproducible real-world Bazel builds

## Quick start

```sh
# 1. Get bazelisk.
sudo curl -fsSL -o /usr/local/bin/bazel \
    https://github.com/bazelbuild/bazelisk/releases/download/v1.25.0/bazelisk-linux-amd64
sudo chmod +x /usr/local/bin/bazel

# 2. Optionally prebuild the container image artifact:
bazel build //runner/image:oci_layout

# 3. Build and test a project; this also builds the image artifact if needed:
bazel run //projects/re2:build      # fetches re2's pinned source, runs its own BUILD
bazel run //projects/re2:test       # runs re2's upstream test suite in the image

# Optional: run the same upstream build/test directly on the local host:
bazel run //projects/re2:local_build
bazel run //projects/re2:local_test
```

Each `//projects/<project>:build` / `:test` target fetches the project's pinned
source, builds the shared image artifact as a Bazel dependency, extracts that
image rootfs into `~/.cache/runner` by manifest digest, then runs `bazelisk`
against the upstream `MODULE`/`BUILD` inside it (via
[crun](https://github.com/containers/crun) in a rootless OCI bundle) with the
project's known-good Bazel pinned. The first build compiles from scratch; reruns
hit a warm cache.

The `:local_build` / `:local_test` variants use the same pinned source, Bazel
version, targets, and cache layout, but run directly on the host with the host's
toolchain and installed tools.

## Projects that build as they are

<!-- BEGIN GENERATED TABLE (runner/_readme_table.py) -->
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
| [OpenCC](https://github.com/BYVoid/OpenCC) | Traditional/Simplified Chinese conversion | 8.7.0 | `bazel run //projects/opencc:build` | `bazel run //projects/opencc:test` |
| [OR-Tools](https://github.com/google/or-tools) | Google's optimization suite (CP-SAT) | 8.7.0 | `bazel run //projects/ortools:build` | `bazel run //projects/ortools:test` (88/89 pass) |
| [protobuf](https://github.com/protocolbuffers/protobuf) | Protocol Buffers serialization | 9.1.1 | `bazel run //projects/protobuf:build` | `bazel run //projects/protobuf:test` (100/101 pass) |
| [re2](https://github.com/google/re2) | Fast, safe regular-expression engine | 8.7.0 | `bazel run //projects/re2:build` | `bazel run //projects/re2:test` |
| [snappy](https://github.com/google/snappy) | Fast compression/decompression library | 8.7.0 | `bazel run //projects/snappy:build` | `bazel run //projects/snappy:test` |
| [zlib](https://github.com/madler/zlib) | The zlib compression library | 9.1.1 | `bazel run //projects/zlib:build` | — (no upstream test target) |
