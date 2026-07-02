# bazel-matrix (🌿-💻)

Here are working [Bazel](https://bazel.build/) builds and test suites for public projects.

## Quick Start

1. [Install Bazelisk](https://github.com/bazelbuild/bazelisk#installation)
2. `bazel test //:smoke_hermetic_llvm_local_tests`

With a [BuildBuddy API key](https://www.buildbuddy.io/docs/quickstart/) configured,
you can also run the hermetic LLVM smoke tests through BuildBuddy RBE:

```sh
bazel test //:smoke_hermetic_llvm_rbe_tests
```

To test an individual project, run that project's tests:

```sh
bazel test //projects/re2/hermetic_llvm:re2_local_test
```

## Project Layout

Project packages live under `//projects/<project_name>/<modification_name>`.
* `as_is` means using unmodified project source code or [Bazel Central Registry](https://registry-preview.bazel.build/) module.
* `hermetic_llvm` means modifying the project source or Bazel Central Registry module to use the [hermetic LLVM toolchain](https://github.com/hermeticbuild/hermetic-llvm) (does not rely on your laptop's C/C++ compiler).

## Project Status

Legend:

- `✅` = matrix test target exists and the latest relevant sweep passed where applicable
- `❌` = latest relevant test sweep failed
- `🔍` = inspected, but no real upstream Bazel test target exists
- `💤` = no matrix test target is expected for this project/environment
- `🧰` = hermetic-llvm modification

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

Notes are keyed by `(project, status cell)` for active non-green cells in the
status table above.

| project | cell | status | note |
| --- | --- | --- | --- |
| `aravis` | `rbe_test` | 🧰 ❌ | The hermetic LLVM variant fixes glib Python codegen and uses preinstalled `make`/`pkg-config`, but libxml2 still builds through `rules_foreign_cc` outside Bazel's C++ rule flow; the zero-sysroot hermetic clang cannot find crt objects such as `Scrt1.o`. |
| `bazel` | `rbe_test` | 💤 | No hermetic LLVM RBE test target is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `behaviortree_cpp` | `rbe_test` | 🧰 ❌ | Its BCR `sed` dependency uses gnulib code that does not parse under clang 22 (`_GL_ATTRIBUTE_FORMAT_PRINTF_STANDARD`). |
| `briansmith_ring` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
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
| `go_jsonnet` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `grpc` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `grpc_gateway` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `iceoryx2` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `llvm-project` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `ortools` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `rocksdb` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| `rsyslog` | `rbe_test` | 🧰 ❌ | The hermetic build issues are fixed, but the upstream smoke test drives `rsyslogd` with `nc -u -w 0`, which only the netcat-openbsd CLI accepts; the executor images provide a different variant. |
| `rules_multirun` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `trlc` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |
| `verilator` | `rbe_test` | 💤 | No hermetic LLVM variant is tracked yet. |

## Projects Not Tackled Right Now

These projects do not expose meaningful upstream tests that we can run with
Bazel today. They are intentionally out of scope for now; fixing them would
mean porting or re-wiring non-Bazel test suites.

| project | cells | status | why |
| --- | --- | --- | --- |
| `brotli` | `local_test / rbe_test` | 🔍 / 💤 | The C library/CLI has no upstream Bazel test target; its C tests are CMake/CTest-based. The nested Go module tests are tracked separately as `brotli_go`. |
| `gflags` | `local_test / rbe_test` | 🔍 / 💤 | Upstream's tests are CMake-only; the Bazel package exposes the library but no real Bazel test target. |
| `json` | `local_test / rbe_test` | 🔍 / 💤 | nlohmann/json exposes a header library through Bazel, but its real test suite is wired through CMake/CTest and would require porting many doctest sources plus external test data into Bazel. |
| `quill` | `local_test / rbe_test` | 🔍 / 💤 | Upstream's Bazel package exposes the library but no real Bazel test target. |
| `z3` | `local_test / rbe_test` | 🔍 / 💤 | Upstream's Bazel target is a `rules_foreign_cc` CMake build of the solver, with no upstream Bazel test target. |
| `zlib` | `local_test / rbe_test` | 🔍 / 💤 | Upstream's Bazel package exposes the library but declares no Bazel test targets. |
