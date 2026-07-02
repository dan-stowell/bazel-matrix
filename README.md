# bazel-matrix (🌿-💻)

## Quick Start

Install Bazel or Bazelisk, then run the as-is smoke tests:

```sh
bazel test //:smoke_as_is_local_tests
```

Outer and inner Bazel invocations publish public BuildBuddy invocation links on
buildbuddy.io by default. If `BUILDBUDDY_API_KEY` is set in your environment,
Bazel also uploads outer test logs so they are visible from the BuildBuddy
invocation page.

With a BuildBuddy API key configured, you can also run the hermetic LLVM smoke
tests through BuildBuddy RBE:

```sh
bazel test //:smoke_hermetic_llvm_rbe_tests
```

To inspect an individual project, run RE2's upstream tests:

```sh
bazel test //projects/re2/as_is:re2_local_test
```

Run RE2's upstream tests through BuildBuddy RBE:

```sh
bazel test //projects/re2/as_is:re2_rbe_test
```

Build RE2 and collect the inner Bazel build event stream, manifest, and
top-level build outputs:

```sh
bazel build //projects/re2/as_is:re2_local_build
```

The output is:

```text
bazel-bin/projects/re2/as_is/re2_local_build.tar
```

## Project Layout

Project packages live under `//projects/<project_name>/<modification_name>`.
The `as_is` package is the unmodified upstream source/module. Other packages,
such as `hermetic_llvm`, are explicit matrix modifications layered on top of
the shared `//projects/<project_name>:project.bzl` spec.

## Project Status

Legend:

- `✅` = matrix test target exists and the latest relevant sweep passed where applicable
- `❌` = latest relevant test sweep failed
- `🔍` = inspected, but no real upstream Bazel test target exists
- `💤` = no matrix test target is expected for this project/environment
- `🧰` = hermetic-llvm modification

The `local_test` column tracks upstream/as-is local test status. The `rbe_test`
column is from the 2026-07-02 sweeps of `//:hermetic_llvm_rbe_tests` (84 of 87
targets pass); `💤` there means the project has no hermetic_llvm rbe_test target
(no test spec, or no variant yet).

| project_name | local_test | rbe_test |
| --- | --- | --- |
| `abseil_cpp` | ✅ | 🧰 ✅ |
| `abseil_py` | ✅ | 🧰 ✅ |
| `aravis` | ✅ | 🧰 ❌ |
| `avro-cpp` | ✅ | 🧰 ✅ |
| `basis_universal` | ✅ | 🧰 ✅ |
| `bazel` | ✅ | 💤 |
| `behaviortree_cpp` | ✅ | 🧰 ❌ |
| `benchmark` | ✅ | 🧰 ✅ |
| `boringssl` | ✅ | 🧰 ✅ |
| `briansmith_ring` | ✅ | 💤 |
| `brotli` | 🔍 | 💤 |
| `brotli_go` | ✅ | 💤 |
| `buildtools` | ✅ | 💤 |
| `c-blosc2` | ✅ | 🧰 ✅ |
| `catch2` | ✅ | 🧰 ✅ |
| `ccronexpr` | ✅ | 🧰 ✅ |
| `cctz` | ✅ | 🧰 ✅ |
| `cityhash` | ✅ | 🧰 ✅ |
| `cjson` | ❌ | 🧰 ✅ |
| `cli11` | ✅ | 🧰 ✅ |
| `copybara` | ✅ | 💤 |
| `cpp-httplib` | ✅ | 🧰 ✅ |
| `cpptrace` | ✅ | 💤 |
| `cpu_features` | ✅ | 🧰 ✅ |
| `crow` | ✅ | 🧰 ✅ |
| `cucumber-cpp` | ✅ | 🧰 ✅ |
| `curl` | ✅ | 💤 |
| `cxx` | ✅ | 💤 |
| `cxxurl` | ✅ | 🧰 ✅ |
| `directxmath` | ✅ | 🧰 ✅ |
| `doctest` | ✅ | 💤 |
| `double_conversion` | ✅ | 🧰 ✅ |
| `effcee` | ✅ | 🧰 ✅ |
| `exprtk` | ✅ | 🧰 ✅ |
| `fast_float` | ✅ | 🧰 ✅ |
| `fftw` | ✅ | 💤 |
| `flatbuffers` | ✅ | 🧰 ✅ |
| `flex` | ✅ | 🧰 ✅ |
| `ftxui` | ✅ | 🧰 ✅ |
| `fuzztest` | ✅ | 🧰 ✅ |
| `fzf` | ✅ | 💤 |
| `gflags` | 🔍 | 💤 |
| `glm` | ✅ | 🧰 ✅ |
| `glog` | ✅ | 🧰 ✅ |
| `go_jsonnet` | ✅ | 💤 |
| `googletest` | ✅ | 🧰 ✅ |
| `gperftools` | ✅ | 🧰 ✅ |
| `grpc` | ✅ | 💤 |
| `grpc_gateway` | ✅ | 💤 |
| `gsl-lite` | ✅ | 🧰 ✅ |
| `hfsm2` | ✅ | 🧰 ✅ |
| `highs` | ✅ | 🧰 ✅ |
| `highway` | ✅ | 🧰 ✅ |
| `iceoryx2` | ✅ | 💤 |
| `icu` | ✅ | 🧰 ✅ |
| `iperf` | ✅ | 🧰 ✅ |
| `iverilog` | ✅ | 🧰 ✅ |
| `json` | 🔍 | 💤 |
| `jsoncpp` | ✅ | 🧰 ✅ |
| `jsonnet` | ✅ | 🧰 ✅ |
| `lcm` | ✅ | 🧰 ✅ |
| `lexbor` | ✅ | 🧰 ✅ |
| `lexy` | ✅ | 🧰 ✅ |
| `libavif` | ✅ | 🧰 ✅ |
| `libcreate` | ✅ | 🧰 ✅ |
| `libde265` | ✅ | 🧰 ✅ |
| `libdwarf` | ✅ | 🧰 ✅ |
| `libevent` | ✅ | 🧰 ✅ |
| `libfastjson` | ✅ | 🧰 ✅ |
| `libgd` | ✅ | 🧰 ✅ |
| `libgit2` | ✅ | 🧰 ✅ |
| `libheif` | ✅ | 🧰 ✅ |
| `libpcap` | ✅ | 🧰 ✅ |
| `libwebsockets` | ✅ | 🧰 ✅ |
| `llvm-project` | ✅ | 💤 |
| `magic_enum` | ✅ | 🧰 ✅ |
| `marisa-trie` | ✅ | 🧰 ✅ |
| `nsync` | ✅ | 🧰 ✅ |
| `ogg` | ✅ | 🧰 ✅ |
| `onetbb` | ✅ | 🧰 ✅ |
| `opencc` | ✅ | 🧰 ✅ |
| `opencl-sdk` | ✅ | 🧰 ✅ |
| `openexr` | ✅ | 🧰 ✅ |
| `openssl` | ✅ | 🧰 ✅ |
| `opentelemetry_cpp` | ✅ | 🧰 ✅ |
| `ortools` | ✅ | 💤 |
| `pcre2` | ✅ | 🧰 ✅ |
| `prometheus_cpp` | ✅ | 🧰 ✅ |
| `protobuf` | ✅ | 🧰 ✅ |
| `quill` | 🔍 | 💤 |
| `re2` | ✅ | 🧰 ✅ |
| `reflexxes-rmltype2` | ✅ | 🧰 ✅ |
| `rocksdb` | ✅ | 💤 |
| `rsyslog` | ✅ | 🧰 ❌ |
| `rules_multirun` | ✅ | 💤 |
| `s2geometry` | ✅ | 🧰 ✅ |
| `sdl2` | ✅ | 🧰 ✅ |
| `sdl2_mixer` | ✅ | 🧰 ✅ |
| `simdutf` | ✅ | 🧰 ✅ |
| `snappy` | ✅ | 🧰 ✅ |
| `squashfs-tools` | ✅ | 🧰 ✅ |
| `systemc` | ✅ | 🧰 ✅ |
| `tinyformat` | ✅ | 🧰 ✅ |
| `tinyxml2` | ✅ | 🧰 ✅ |
| `tomlplusplus` | ✅ | 🧰 ✅ |
| `trlc` | ✅ | 💤 |
| `universal-robots-client-library` | ✅ | 🧰 ✅ |
| `verible` | ✅ | 🧰 ✅ |
| `verilator` | ✅ | 💤 |
| `xkbcommon` | ✅ | 🧰 ✅ |
| `z3` | 🔍 | 💤 |
| `zlib` | 🔍 | 💤 |
| `zstd` | ✅ | 🧰 ✅ |
| `zziplib` | ✅ | 🧰 ✅ |

## Project Notes

Notes are keyed by `(project, status cell)` for every `🔍`, `❌`, or `💤` in
the status table above.

| project | cell | status | note |
| --- | --- | --- | --- |
| `aravis` | `rbe_test` | 🧰 ❌ | The hermetic LLVM variant fixes glib Python codegen and uses preinstalled `make`/`pkg-config`, but libxml2 still builds through `rules_foreign_cc` outside Bazel's C++ rule flow; the zero-sysroot hermetic clang cannot find crt objects such as `Scrt1.o`. |
| `bazel` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `behaviortree_cpp` | `rbe_test` | 🧰 ❌ | Its BCR `sed` dependency uses gnulib code that does not parse under clang 22 (`_GL_ATTRIBUTE_FORMAT_PRINTF_STANDARD`). |
| `briansmith_ring` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `brotli` | `local_test` | 🔍 | The C library/CLI has no upstream Bazel test target; its C tests are CMake/CTest-based. The nested Go module tests are tracked separately as `brotli_go`. |
| `brotli` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected for this build-only C package. |
| `brotli_go` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet for the nested Go-module test package. |
| `buildtools` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `cjson` | `local_test` | ❌ | One of the 22 upstream tests is sensitive to the host compiler/libc; the hermetic LLVM variant passes and is the reproducible result. |
| `copybara` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `cpptrace` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `curl` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `cxx` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `doctest` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `fftw` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `fzf` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `gflags` | `local_test` | 🔍 | Upstream's tests are CMake-only; the Bazel package exposes the library but no real Bazel test target. |
| `gflags` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected because the project is build-only in Bazel. |
| `go_jsonnet` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `grpc` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `grpc_gateway` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `iceoryx2` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `json` | `local_test` | 🔍 | nlohmann/json exposes a header library through Bazel, but its real test suite is wired through CMake/CTest and would require porting many doctest sources plus external test data into Bazel. |
| `json` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected because the upstream Bazel package is build-only. |
| `llvm-project` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `ortools` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `quill` | `local_test` | 🔍 | Upstream's Bazel package exposes the library but no real Bazel test target. |
| `quill` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected because the project is build-only in Bazel. |
| `rocksdb` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `rsyslog` | `rbe_test` | 🧰 ❌ | The hermetic build issues are fixed, but the upstream smoke test drives `rsyslogd` with `nc -u -w 0`, which only the netcat-openbsd CLI accepts; the executor images provide a different variant. |
| `rules_multirun` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `trlc` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `verilator` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `z3` | `local_test` | 🔍 | Upstream's Bazel target is a `rules_foreign_cc` CMake build of the solver, with no upstream Bazel test target. |
| `z3` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected because the upstream Bazel package is build-only. |
| `zlib` | `local_test` | 🔍 | Upstream's Bazel package exposes the library but declares no Bazel test targets. |
| `zlib` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is expected because the project is build-only in Bazel. |
