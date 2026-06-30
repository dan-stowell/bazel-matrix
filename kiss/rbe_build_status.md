# RBE Build Status

Last sweep: 2026-06-30, as-is `//projects/...:kiss_rbe_build` targets using BuildBuddy remote execution.

The root `kiss_rbe_build` target intentionally uses the upstream source/module without adding a C/C++ toolchain overlay. Modification-specific results should live under modification subpackages, for example `//projects/<name>/buildbuddy_toolchain:kiss_build` or `//projects/<name>/hermetic_llvm:kiss_build`.

## Cause Buckets

- `pass`: 10 projects; as-is RBE build passed.
- `missing-remote-cc`: 97 projects; inner build uses an autodetected local C/C++ toolchain, but the remote worker does not provide `/bin/gcc`/`cc`.
- `go-cgo-cc`: 3 projects; rules_go stdlib/cgo expects `cc` on the remote worker.
- `source-overlay-required`: 2 projects; source tree needs a `MODULE.bazel`/`WORKSPACE` overlay before Bazel can run.
- `missing-remote-jdk`: 1 project; inner build autoconfigured a local JDK that is absent on the remote worker.
- `project-toolchain-runtime`: 1 project; project-selected toolchain reaches the remote worker, but required runtime libraries are too old.
- `other`: 0 projects; needs a closer look at the failing inner build output.

## Projects

| project | rbe_build | cause | note |
| --- | --- | --- | --- |
| `abseil_cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `abseil_py` | ✅ | `pass` | as-is RBE build passed |
| `aravis` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `avro-cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `basis_universal` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `bazel` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `behaviortree_cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `benchmark` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `boringssl` | ✅ | `pass` | as-is RBE build passed |
| `briansmith_ring` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `brotli` | ❌ | `source-overlay-required` | source tree needs a MODULE.bazel/WORKSPACE overlay before Bazel can run |
| `brotli_go` | ❌ | `source-overlay-required` | source tree needs a MODULE.bazel/WORKSPACE overlay before Bazel can run |
| `buildtools` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `c-blosc2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `catch2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `ccronexpr` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cctz` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cityhash` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cjson` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cli11` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `copybara` | ❌ | `missing-remote-jdk` | inner build autoconfigured a local JDK that is absent on the remote worker |
| `cpp-httplib` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cpptrace` | ❌ | `project-toolchain-runtime` | project-selected LLVM toolchain reaches the remote worker, but its runtime libraries are too old |
| `cpu_features` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `crow` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cucumber-cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `curl` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cxx` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `cxxurl` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `directxmath` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `doctest` | ✅ | `pass` | as-is RBE build passed |
| `double_conversion` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `effcee` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `exprtk` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `fast_float` | ✅ | `pass` | as-is RBE build passed |
| `fftw` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `flatbuffers` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `flex` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `ftxui` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `fuzztest` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `fzf` | ❌ | `go-cgo-cc` | rules_go stdlib/cgo expects cc on the remote worker |
| `gflags` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `glm` | ✅ | `pass` | as-is RBE build passed |
| `glog` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `go_jsonnet` | ❌ | `go-cgo-cc` | rules_go stdlib/cgo expects cc on the remote worker |
| `googletest` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `gperftools` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `grpc` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `grpc_gateway` | ❌ | `go-cgo-cc` | rules_go stdlib/cgo expects cc on the remote worker |
| `gsl-lite` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `hfsm2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `highs` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `highway` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `iceoryx2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `icu` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `iperf` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `iverilog` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `json` | ✅ | `pass` | as-is RBE build passed |
| `jsoncpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `jsonnet` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `lcm` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `lexbor` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `lexy` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libavif` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libcreate` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libde265` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libdwarf` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libevent` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libfastjson` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libgd` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libgit2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libheif` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libpcap` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `libwebsockets` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `llvm-project` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `magic_enum` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `marisa-trie` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `nsync` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `ogg` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `onetbb` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `opencc` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `opencl-sdk` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `openexr` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `openssl` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `opentelemetry_cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `ortools` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `pcre2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `prometheus_cpp` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `protobuf` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `quill` | ✅ | `pass` | as-is RBE build passed |
| `re2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `reflexxes-rmltype2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `rocksdb` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `rsyslog` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `rules_multirun` | ✅ | `pass` | as-is RBE build passed |
| `s2geometry` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `sdl2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `sdl2_mixer` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `simdutf` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `snappy` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `squashfs-tools` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `systemc` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `tinyformat` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `tinyxml2` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `tomlplusplus` | ✅ | `pass` | as-is RBE build passed |
| `trlc` | ✅ | `pass` | as-is RBE build passed |
| `universal-robots-client-library` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `verible` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `verilator` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `xkbcommon` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `z3` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `zlib` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `zstd` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
| `zziplib` | ❌ | `missing-remote-cc` | inner build uses autodetected local C/C++ toolchain; remote worker does not provide /bin/gcc/cc |
