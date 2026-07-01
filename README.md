# bazel-matrix (🌿-💻)

## Quick Start

Install Bazel or Bazelisk, then run the RE2 build:

```sh
bazel build //projects/re2:kiss_build
```

The output is:

```text
bazel-bin/projects/re2/kiss_build.tar
```

That tarball contains the inner Bazel build event stream, a manifest, and RE2's
top-level build outputs.

Run RE2's upstream tests:

```sh
bazel test //projects/re2:kiss_test
```

Run upstream tests through BuildBuddy RBE when a project has a test target:

```sh
bazel test --test_env=BUILDBUDDY_API_KEY //projects/re2:kiss_rbe_test
```

## Project Status

Legend:

- `✅` = KISS target exists and the latest relevant sweep passed where applicable
- `❌` = latest relevant sweep failed
- `🔍` = inspected, but no real upstream Bazel test target exists
- `💤` = no KISS target is expected for this project/command
- `📦` = as-is source/module
- `☁️` = BuildBuddy toolchain modification
- `🧰` = hermetic-llvm modification

RBE cells combine variant/result pairs, for example `📦 ❌ / 🧰 ✅`.

Detailed RBE build failure buckets are tracked in [kiss/rbe_build_status.md](kiss/rbe_build_status.md).

| project_name | build | test | rbe_build |
| --- | --- | --- | --- |
| `abseil_cpp` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `abseil_py` | ✅ | ✅ | 📦 ✅ |
| `aravis` | ✅ | ✅ | 📦 ❌ |
| `avro-cpp` | ✅ | ✅ | 📦 ❌ |
| `basis_universal` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `bazel` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `behaviortree_cpp` | ✅ | ✅ | 📦 ❌ |
| `benchmark` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `boringssl` | ✅ | ✅ | 📦 ✅ |
| `briansmith_ring` | ✅ | ✅ | 📦 ❌ |
| `brotli` | ✅ | 🔍 | 📦 ❌ / 🧰 ✅ |
| `brotli_go` | ✅ | ✅ | 📦 ❌ |
| `buildtools` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `c-blosc2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `catch2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `ccronexpr` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cctz` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cityhash` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cjson` | 💤 | ❌ | 📦 ❌ / 🧰 ✅ |
| `cli11` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `copybara` | ✅ | ✅ | 📦 ❌ |
| `cpp-httplib` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cpptrace` | ✅ | ✅ | 📦 ❌ |
| `cpu_features` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `crow` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cucumber-cpp` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `curl` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `cxx` | ✅ | ✅ | 📦 ❌ |
| `cxxurl` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `directxmath` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `doctest` | ✅ | ✅ | 📦 ✅ |
| `double_conversion` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `effcee` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `exprtk` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `fast_float` | ✅ | ✅ | 📦 ✅ |
| `fftw` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `flatbuffers` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `flex` | ✅ | ✅ | 📦 ❌ |
| `ftxui` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `fuzztest` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `fzf` | ✅ | ✅ | 📦 ❌ |
| `gflags` | ✅ | 🔍 | 📦 ❌ / 🧰 ✅ |
| `glm` | ✅ | ✅ | 📦 ✅ |
| `glog` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `go_jsonnet` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `googletest` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `gperftools` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `grpc` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `grpc_gateway` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `gsl-lite` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `hfsm2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `highs` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `highway` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `iceoryx2` | ✅ | ✅ | 📦 ❌ |
| `icu` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `iperf` | ✅ | ✅ | 📦 ❌ |
| `iverilog` | ✅ | ✅ | 📦 ❌ |
| `json` | ✅ | 🔍 | 📦 ✅ |
| `jsoncpp` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `jsonnet` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `lcm` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `lexbor` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `lexy` | 💤 | ✅ | 📦 ❌ / 🧰 ✅ |
| `libavif` | ✅ | ✅ | 📦 ❌ |
| `libcreate` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `libde265` | ✅ | ✅ | 📦 ❌ |
| `libdwarf` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `libevent` | ✅ | ✅ | 📦 ❌ |
| `libfastjson` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `libgd` | ✅ | ✅ | 📦 ❌ |
| `libgit2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `libheif` | ✅ | ✅ | 📦 ❌ |
| `libpcap` | ✅ | ✅ | 📦 ❌ |
| `libwebsockets` | ✅ | ✅ | 📦 ❌ |
| `llvm-project` | ✅ | ✅ | 📦 ❌ |
| `magic_enum` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `marisa-trie` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `nsync` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `ogg` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `onetbb` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `opencc` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `opencl-sdk` | ✅ | ✅ | 📦 ❌ |
| `openexr` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `openssl` | ✅ | ✅ | 📦 ❌ |
| `opentelemetry_cpp` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `ortools` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `pcre2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `prometheus_cpp` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `protobuf` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `quill` | ✅ | 🔍 | 📦 ✅ |
| `re2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `reflexxes-rmltype2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `rocksdb` | 💤 | ✅ | 📦 ❌ / 🧰 ✅ |
| `rsyslog` | ✅ | ✅ | 📦 ❌ |
| `rules_multirun` | ✅ | ✅ | 📦 ✅ |
| `s2geometry` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `sdl2` | ✅ | ✅ | 📦 ❌ |
| `sdl2_mixer` | ✅ | ✅ | 📦 ❌ |
| `simdutf` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `snappy` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `squashfs-tools` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `systemc` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `tinyformat` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `tinyxml2` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `tomlplusplus` | 💤 | ✅ | 📦 ✅ |
| `trlc` | ✅ | ✅ | 📦 ✅ |
| `universal-robots-client-library` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `verible` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `verilator` | ✅ | ✅ | 📦 ❌ |
| `xkbcommon` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `z3` | ✅ | 🔍 | 📦 ❌ |
| `zlib` | ✅ | 🔍 | 📦 ❌ / 🧰 ✅ |
| `zstd` | ✅ | ✅ | 📦 ❌ / 🧰 ✅ |
| `zziplib` | ✅ | ✅ | 📦 ❌ |
