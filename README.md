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
(no test spec, or no variant yet). See
[bazel_runner/rbe_test_status.md](bazel_runner/rbe_test_status.md) for the RBE
test findings, fixes, and environmental exclusions.

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
