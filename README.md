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
- `🚫` = no real upstream Bazel test target exists
- `💤` = no matrix test target is expected for this project/environment
- `🧰` = hermetic-llvm modification

| project_name | local_test | rbe_test |
| --- | --- | --- |
| [`abseil_cpp`](https://github.com/abseil/abseil-cpp) | ✅ | 🧰 ✅ |
| [`abseil_py`](https://github.com/abseil/abseil-py) | ✅ | 🧰 ✅ |
| [`aravis`](https://registry-preview.bazel.build/modules/aravis/0.9.2-20251111063445-57983d013883/) | ✅ | 🧰 ❌ |
| [`avro-cpp`](https://registry-preview.bazel.build/modules/avro-cpp/1.12.0/) | ✅ | 🧰 ✅ |
| [`basis_universal`](https://registry-preview.bazel.build/modules/basis_universal/2.0.3/) | ✅ | 🧰 ✅ |
| [`bazel`](https://github.com/bazelbuild/bazel) | ✅ | 💤 |
| [`behaviortree_cpp`](https://registry-preview.bazel.build/modules/behaviortree_cpp/4.7.0.bcr.3/) | ✅ | 🧰 ❌ |
| [`benchmark`](https://github.com/google/benchmark) | ✅ | 🧰 ✅ |
| [`boringssl`](https://github.com/google/boringssl) | ✅ | 🧰 ✅ |
| [`briansmith_ring`](https://registry-preview.bazel.build/modules/briansmith_ring/0.17.14.bcr.1/) | ✅ | 💤 |
| [`brotli`](https://github.com/google/brotli) | 🚫 | 🚫 |
| [`brotli_go`](https://github.com/google/brotli) | ✅ | 💤 |
| [`buildtools`](https://github.com/bazelbuild/buildtools) | ✅ | 💤 |
| [`c-blosc2`](https://registry-preview.bazel.build/modules/c-blosc2/2.22.0/) | ✅ | 🧰 ✅ |
| [`catch2`](https://github.com/catchorg/Catch2) | ✅ | 🧰 ✅ |
| [`ccronexpr`](https://registry-preview.bazel.build/modules/ccronexpr/2.1.0/) | ✅ | 🧰 ✅ |
| [`cctz`](https://github.com/google/cctz) | ✅ | 🧰 ✅ |
| [`cityhash`](https://registry-preview.bazel.build/modules/cityhash/1.1.1/) | ✅ | 🧰 ✅ |
| [`cjson`](https://registry-preview.bazel.build/modules/cjson/1.7.19-0.20240923110858-12c4bf1986c2.bcr.4/) | ❌ | 🧰 ✅ |
| [`cli11`](https://github.com/CLIUtils/CLI11) | ✅ | 🧰 ✅ |
| [`copybara`](https://github.com/google/copybara) | ✅ | 💤 |
| [`cpp-httplib`](https://registry-preview.bazel.build/modules/cpp-httplib/0.46.0/) | ✅ | 🧰 ✅ |
| [`cpptrace`](https://github.com/jeremy-rifkin/cpptrace) | ✅ | 💤 |
| [`cpu_features`](https://github.com/google/cpu_features) | ✅ | 🧰 ✅ |
| [`crow`](https://github.com/CrowCpp/Crow) | ✅ | 🧰 ✅ |
| [`cucumber-cpp`](https://registry-preview.bazel.build/modules/cucumber-cpp/0.8.0.bcr.1/) | ✅ | 🧰 ✅ |
| [`curl`](https://registry-preview.bazel.build/modules/curl/8.12.0.bcr.1/) | ✅ | 💤 |
| [`cxx`](https://github.com/dtolnay/cxx) | ✅ | 💤 |
| [`cxxurl`](https://registry-preview.bazel.build/modules/cxxurl/0.3/) | ✅ | 🧰 ✅ |
| [`directxmath`](https://registry-preview.bazel.build/modules/directxmath/3.20/) | ✅ | 🧰 ✅ |
| [`doctest`](https://github.com/doctest/doctest) | ✅ | 💤 |
| [`double_conversion`](https://github.com/google/double-conversion) | ✅ | 🧰 ✅ |
| [`effcee`](https://registry-preview.bazel.build/modules/effcee/0.0.0-20250222/) | ✅ | 🧰 ✅ |
| [`exprtk`](https://registry-preview.bazel.build/modules/exprtk/0.0.3.bcr.1/) | ✅ | 🧰 ✅ |
| [`fast_float`](https://github.com/fastfloat/fast_float) | ✅ | 🧰 ✅ |
| [`fftw`](https://registry-preview.bazel.build/modules/fftw/3.3.10/) | ✅ | 💤 |
| [`flatbuffers`](https://github.com/google/flatbuffers) | ✅ | 🧰 ✅ |
| [`flex`](https://registry-preview.bazel.build/modules/flex/2.6.4.bcr.5/) | ✅ | 🧰 ✅ |
| [`ftxui`](https://github.com/ArthurSonzogni/FTXUI) | ✅ | 🧰 ✅ |
| [`fuzztest`](https://github.com/google/fuzztest) | ✅ | 🧰 ✅ |
| [`fzf`](https://registry-preview.bazel.build/modules/fzf/0.71.0/) | ✅ | 💤 |
| [`gflags`](https://github.com/gflags/gflags) | 🚫 | 🚫 |
| [`glm`](https://registry-preview.bazel.build/modules/glm/1.0.3/) | ✅ | 🧰 ✅ |
| [`glog`](https://github.com/google/glog) | ✅ | 🧰 ✅ |
| [`go_jsonnet`](https://github.com/google/go-jsonnet) | ✅ | 💤 |
| [`googletest`](https://github.com/google/googletest) | ✅ | 🧰 ✅ |
| [`gperftools`](https://github.com/gperftools/gperftools) | ✅ | 🧰 ✅ |
| [`grpc`](https://github.com/grpc/grpc) | ✅ | 💤 |
| [`grpc_gateway`](https://github.com/grpc-ecosystem/grpc-gateway) | ✅ | 💤 |
| [`gsl-lite`](https://registry-preview.bazel.build/modules/gsl-lite/1.1.0/) | ✅ | 🧰 ✅ |
| [`hfsm2`](https://registry-preview.bazel.build/modules/hfsm2/2.10.0/) | ✅ | 🧰 ✅ |
| [`highs`](https://github.com/ERGO-Code/HiGHS) | ✅ | 🧰 ✅ |
| [`highway`](https://github.com/google/highway) | ✅ | 🧰 ✅ |
| [`iceoryx2`](https://github.com/eclipse-iceoryx/iceoryx2) | ✅ | 💤 |
| [`icu`](https://registry-preview.bazel.build/modules/icu/78.2.bcr.1/) | ✅ | 🧰 ✅ |
| [`iperf`](https://registry-preview.bazel.build/modules/iperf/3.18.0/) | ✅ | 🧰 ✅ |
| [`iverilog`](https://registry-preview.bazel.build/modules/iverilog/13.0.bcr.1/) | ✅ | 🧰 ✅ |
| [`json`](https://github.com/nlohmann/json) | 🚫 | 🚫 |
| [`jsoncpp`](https://github.com/open-source-parsers/jsoncpp) | ✅ | 🧰 ✅ |
| [`jsonnet`](https://github.com/google/jsonnet) | ✅ | 🧰 ✅ |
| [`lcm`](https://github.com/lcm-proj/lcm) | ✅ | 🧰 ✅ |
| [`lexbor`](https://registry-preview.bazel.build/modules/lexbor/2.4.0/) | ✅ | 🧰 ✅ |
| [`lexy`](https://registry-preview.bazel.build/modules/lexy/2025.05.0/) | ✅ | 🧰 ✅ |
| [`libavif`](https://registry-preview.bazel.build/modules/libavif/1.4.1/) | ✅ | 🧰 ✅ |
| [`libcreate`](https://registry-preview.bazel.build/modules/libcreate/3.1.0/) | ✅ | 🧰 ✅ |
| [`libde265`](https://registry-preview.bazel.build/modules/libde265/1.0.18/) | ✅ | 🧰 ✅ |
| [`libdwarf`](https://registry-preview.bazel.build/modules/libdwarf/2.2.0.bcr.1/) | ✅ | 🧰 ✅ |
| [`libevent`](https://registry-preview.bazel.build/modules/libevent/2.1.12-stable.bcr.0/) | ✅ | 🧰 ✅ |
| [`libfastjson`](https://registry-preview.bazel.build/modules/libfastjson/1.2304.0/) | ✅ | 🧰 ✅ |
| [`libgd`](https://registry-preview.bazel.build/modules/libgd/2.3.3/) | ✅ | 🧰 ✅ |
| [`libgit2`](https://registry-preview.bazel.build/modules/libgit2/1.9.2.bcr.1/) | ✅ | 🧰 ✅ |
| [`libheif`](https://registry-preview.bazel.build/modules/libheif/1.21.2/) | ✅ | 🧰 ✅ |
| [`libpcap`](https://registry-preview.bazel.build/modules/libpcap/1.10.5.bcr.3/) | ✅ | 🧰 ✅ |
| [`libwebsockets`](https://registry-preview.bazel.build/modules/libwebsockets/4.5.2/) | ✅ | 🧰 ✅ |
| [`llvm-project`](https://registry-preview.bazel.build/modules/llvm-project/17.0.4.bcr.1/) | ✅ | 💤 |
| [`magic_enum`](https://github.com/Neargye/magic_enum) | ✅ | 🧰 ✅ |
| [`marisa-trie`](https://registry-preview.bazel.build/modules/marisa-trie/0.3.1.bcr.2/) | ✅ | 🧰 ✅ |
| [`nsync`](https://github.com/google/nsync) | ✅ | 🧰 ✅ |
| [`ogg`](https://registry-preview.bazel.build/modules/ogg/1.3.5.bcr.3/) | ✅ | 🧰 ✅ |
| [`onetbb`](https://github.com/uxlfoundation/oneTBB) | ✅ | 🧰 ✅ |
| [`opencc`](https://github.com/BYVoid/OpenCC) | ✅ | 🧰 ✅ |
| [`opencl-sdk`](https://registry-preview.bazel.build/modules/opencl-sdk/2025.07.23/) | ✅ | 🧰 ✅ |
| [`openexr`](https://github.com/AcademySoftwareFoundation/openexr) | ✅ | 🧰 ✅ |
| [`openssl`](https://registry-preview.bazel.build/modules/openssl/3.5.5.bcr.4/) | ✅ | 🧰 ✅ |
| [`opentelemetry_cpp`](https://github.com/open-telemetry/opentelemetry-cpp) | ✅ | 🧰 ✅ |
| [`ortools`](https://github.com/google/or-tools) | ✅ | 💤 |
| [`pcre2`](https://github.com/PCRE2Project/pcre2) | ✅ | 🧰 ✅ |
| [`prometheus_cpp`](https://github.com/jupp0r/prometheus-cpp) | ✅ | 🧰 ✅ |
| [`protobuf`](https://github.com/protocolbuffers/protobuf) | ✅ | 🧰 ✅ |
| [`quill`](https://github.com/odygrd/quill) | 🚫 | 🚫 |
| [`re2`](https://github.com/google/re2) | ✅ | 🧰 ✅ |
| [`reflexxes-rmltype2`](https://registry-preview.bazel.build/modules/reflexxes-rmltype2/1.2.7/) | ✅ | 🧰 ✅ |
| [`rocksdb`](https://registry-preview.bazel.build/modules/rocksdb/9.11.2/) | ✅ | 💤 |
| [`rsyslog`](https://registry-preview.bazel.build/modules/rsyslog/8.2504.0/) | ✅ | 🧰 ❌ |
| [`rules_multirun`](https://registry-preview.bazel.build/modules/rules_multirun/0.14.0/) | ✅ | 💤 |
| [`s2geometry`](https://github.com/google/s2geometry) | ✅ | 🧰 ✅ |
| [`sdl2`](https://registry-preview.bazel.build/modules/sdl2/2.32.0.bcr.beta.6/) | ✅ | 🧰 ✅ |
| [`sdl2_mixer`](https://registry-preview.bazel.build/modules/sdl2_mixer/2.8.1.bcr.beta.2/) | ✅ | 🧰 ✅ |
| [`simdutf`](https://registry-preview.bazel.build/modules/simdutf/7.7.0/) | ✅ | 🧰 ✅ |
| [`snappy`](https://github.com/google/snappy) | ✅ | 🧰 ✅ |
| [`squashfs-tools`](https://registry-preview.bazel.build/modules/squashfs-tools/4.7.5/) | ✅ | 🧰 ✅ |
| [`systemc`](https://registry-preview.bazel.build/modules/systemc/3.0.2.bcr.1/) | ✅ | 🧰 ✅ |
| [`tinyformat`](https://registry-preview.bazel.build/modules/tinyformat/2.3.0/) | ✅ | 🧰 ✅ |
| [`tinyxml2`](https://registry-preview.bazel.build/modules/tinyxml2/11.0.0/) | ✅ | 🧰 ✅ |
| [`tomlplusplus`](https://registry-preview.bazel.build/modules/tomlplusplus/3.4.0/) | ✅ | 🧰 ✅ |
| [`trlc`](https://registry-preview.bazel.build/modules/trlc/2.0.5/) | ✅ | 💤 |
| [`universal-robots-client-library`](https://registry-preview.bazel.build/modules/universal-robots-client-library/2.4.0/) | ✅ | 🧰 ✅ |
| [`verible`](https://github.com/chipsalliance/verible) | ✅ | 🧰 ✅ |
| [`verilator`](https://registry-preview.bazel.build/modules/verilator/5.046.bcr.5/) | ✅ | 💤 |
| [`xkbcommon`](https://registry-preview.bazel.build/modules/xkbcommon/1.9.2.bcr.beta.1/) | ✅ | 🧰 ✅ |
| [`z3`](https://github.com/Z3Prover/z3) | 🚫 | 🚫 |
| [`zlib`](https://github.com/madler/zlib) | 🚫 | 🚫 |
| [`zstd`](https://registry-preview.bazel.build/modules/zstd/1.5.7.bcr.1/) | ✅ | 🧰 ✅ |
| [`zziplib`](https://registry-preview.bazel.build/modules/zziplib/0.13.72/) | ✅ | 🧰 ✅ |

## Project Notes

Notes are keyed by `(project, test env)` for active non-green cells in the
status table above.

| project | test env | status | note |
| --- | --- | --- | --- |
| [`aravis`](https://registry-preview.bazel.build/modules/aravis/0.9.2-20251111063445-57983d013883/) | `rbe` | 🧰 ❌ | The hermetic LLVM variant fixes glib Python codegen and uses preinstalled `make`/`pkg-config`, but libxml2 still builds through `rules_foreign_cc` outside Bazel's C++ rule flow; the zero-sysroot hermetic clang cannot find crt objects such as `Scrt1.o`. |
| [`bazel`](https://github.com/bazelbuild/bazel) | `rbe` | 💤 | No hermetic LLVM RBE test target is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| [`behaviortree_cpp`](https://registry-preview.bazel.build/modules/behaviortree_cpp/4.7.0.bcr.3/) | `rbe` | 🧰 ❌ | Its BCR `sed` dependency uses gnulib code that does not parse under clang 22 (`_GL_ATTRIBUTE_FORMAT_PRINTF_STANDARD`). |
| [`briansmith_ring`](https://registry-preview.bazel.build/modules/briansmith_ring/0.17.14.bcr.1/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`brotli_go`](https://github.com/google/brotli) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet for the nested Go-module test package. |
| [`buildtools`](https://github.com/bazelbuild/buildtools) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`cjson`](https://registry-preview.bazel.build/modules/cjson/1.7.19-0.20240923110858-12c4bf1986c2.bcr.4/) | `local` | ❌ | One of the 22 upstream tests is sensitive to the host compiler/libc; the hermetic LLVM variant passes and is the reproducible result. |
| [`copybara`](https://github.com/google/copybara) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`cpptrace`](https://github.com/jeremy-rifkin/cpptrace) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`curl`](https://registry-preview.bazel.build/modules/curl/8.12.0.bcr.1/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`cxx`](https://github.com/dtolnay/cxx) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`doctest`](https://github.com/doctest/doctest) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`fftw`](https://registry-preview.bazel.build/modules/fftw/3.3.10/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`fzf`](https://registry-preview.bazel.build/modules/fzf/0.71.0/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`go_jsonnet`](https://github.com/google/go-jsonnet) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`grpc`](https://github.com/grpc/grpc) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`grpc_gateway`](https://github.com/grpc-ecosystem/grpc-gateway) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`iceoryx2`](https://github.com/eclipse-iceoryx/iceoryx2) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`llvm-project`](https://registry-preview.bazel.build/modules/llvm-project/17.0.4.bcr.1/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| [`ortools`](https://github.com/google/or-tools) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`rocksdb`](https://registry-preview.bazel.build/modules/rocksdb/9.11.2/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| [`rsyslog`](https://registry-preview.bazel.build/modules/rsyslog/8.2504.0/) | `rbe` | 🧰 ❌ | The hermetic build issues are fixed, but the upstream smoke test drives `rsyslogd` with `nc -u -w 0`, which only the netcat-openbsd CLI accepts; the executor images provide a different variant. |
| [`rules_multirun`](https://registry-preview.bazel.build/modules/rules_multirun/0.14.0/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`trlc`](https://registry-preview.bazel.build/modules/trlc/2.0.5/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |
| [`verilator`](https://registry-preview.bazel.build/modules/verilator/5.046.bcr.5/) | `rbe` | 💤 | No hermetic LLVM variant is tracked yet. |

## Projects Not Tackled Right Now

These projects do not expose meaningful upstream tests that we can run with
Bazel today. They are intentionally out of scope for now; fixing them would
mean porting or re-wiring non-Bazel test suites.

| project | status | why |
| --- | --- | --- |
| [`brotli`](https://github.com/google/brotli) | 🚫 | The C library/CLI has no upstream Bazel test target; its C tests are CMake/CTest-based. The nested Go module tests are tracked separately as `brotli_go`. |
| [`gflags`](https://github.com/gflags/gflags) | 🚫 | Upstream's tests are CMake-only; the Bazel package exposes the library but no real Bazel test target. |
| [`json`](https://github.com/nlohmann/json) | 🚫 | nlohmann/json exposes a header library through Bazel, but its real test suite is wired through CMake/CTest and would require porting many doctest sources plus external test data into Bazel. |
| [`quill`](https://github.com/odygrd/quill) | 🚫 | Upstream's Bazel package exposes the library but no real Bazel test target. |
| [`z3`](https://github.com/Z3Prover/z3) | 🚫 | Upstream's Bazel target is a `rules_foreign_cc` CMake build of the solver, with no upstream Bazel test target. |
| [`zlib`](https://github.com/madler/zlib) | 🚫 | Upstream's Bazel package exposes the library but declares no Bazel test targets. |
