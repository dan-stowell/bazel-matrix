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
- `📦` = as-is modification
- `🧰` = hermetic-llvm modification
- `N / M` = upstream tests passing out of the meaningful test suite tracked here

| project_name | local_test | rbe_test |
| --- | --- | --- |
| [`abseil_cpp`](https://github.com/abseil/abseil-cpp) | 📦 ✅ [251 / 251](https://app.buildbuddy.io/invocation/3ecd9d6d-2a8e-4c6f-b690-23b82ff03bdd) | 🧰 ✅ |
| [`abseil_py`](https://github.com/abseil/abseil-py) | 📦 ✅ [27 / 27](https://app.buildbuddy.io/invocation/26c52517-ee87-4bef-81e1-1fe41b000024) | 🧰 ✅ |
| [`aravis`](https://registry-preview.bazel.build/modules/aravis/0.9.2-20251111063445-57983d013883/) | 📦 ✅ [7 / 7](https://app.buildbuddy.io/invocation/69ae8c8f-1470-42a6-9c18-d716310c98d0) | 🧰 ❌ |
| [`avro-cpp`](https://registry-preview.bazel.build/modules/avro-cpp/1.12.0/) | 📦 ✅ [6 / 6](https://app.buildbuddy.io/invocation/7244b93a-4730-4199-bc74-bc1200150f60) | 🧰 ✅ |
| [`basis_universal`](https://registry-preview.bazel.build/modules/basis_universal/2.0.3/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/ba54c6d2-91cb-475e-a727-185d8de521cc) | 🧰 ✅ |
| [`bazel`](https://github.com/bazelbuild/bazel) | 📦 ✅ | 💤 |
| [`behaviortree_cpp`](https://registry-preview.bazel.build/modules/behaviortree_cpp/4.7.0.bcr.3/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/ff30c3b3-57cf-4e47-9a76-3bed40859c84) | 🧰 ❌ |
| [`benchmark`](https://github.com/google/benchmark) | 📦 ✅ [49 / 49](https://app.buildbuddy.io/invocation/77e59fe1-8dbc-4682-9898-9d5a6fedaa74) | 🧰 ✅ |
| [`boringssl`](https://github.com/google/boringssl) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/0e9e619f-b6e0-4f2a-bc08-b1c9d6d29fc6) | 🧰 ✅ |
| [`briansmith_ring`](https://registry-preview.bazel.build/modules/briansmith_ring/0.17.14.bcr.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/fe954775-ba38-475b-86f4-5c7e9a009b66) | 🧰 ✅ |
| [`brotli`](https://github.com/google/brotli) | 🚫 | 🚫 |
| [`brotli_go`](https://github.com/google/brotli) | 📦 ✅ [4 / 4](https://app.buildbuddy.io/invocation/d0ed49a7-65f7-4ef9-ab6b-46d4d705c193) | 🧰 ❌ |
| [`buildtools`](https://github.com/bazelbuild/buildtools) | 📦 ✅ [5 / 5](https://app.buildbuddy.io/invocation/80c81fcd-c6d8-413e-bd93-bc94f816fcaf) | 🧰 ✅ |
| [`c-blosc2`](https://registry-preview.bazel.build/modules/c-blosc2/2.22.0/) | 📦 ✅ [37 / 37](https://app.buildbuddy.io/invocation/255941ac-c024-4df8-aece-9b7778b207bd) | 🧰 ✅ |
| [`catch2`](https://github.com/catchorg/Catch2) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/ed4426eb-9c66-49fc-897d-d9160783e459) | 🧰 ✅ |
| [`ccronexpr`](https://registry-preview.bazel.build/modules/ccronexpr/2.1.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/d695ff42-93bc-480e-a2b9-19ff450177b5) | 🧰 ✅ |
| [`cctz`](https://github.com/google/cctz) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/d52c5f1d-8279-4cd0-842e-c8e8876e4a7b) | 🧰 ✅ |
| [`cityhash`](https://registry-preview.bazel.build/modules/cityhash/1.1.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/07d882b4-ed3d-4cbb-b187-bea2a5556152) | 🧰 ✅ |
| [`cjson`](https://registry-preview.bazel.build/modules/cjson/1.7.19-0.20240923110858-12c4bf1986c2.bcr.4/) | 📦 ✅ [21 / 21](https://app.buildbuddy.io/invocation/e1387d22-95e9-4b7a-b619-66fcaefacc7d) | 🧰 ✅ |
| [`cli11`](https://github.com/CLIUtils/CLI11) | 📦 ✅ [9 / 9](https://app.buildbuddy.io/invocation/d8df4037-81d2-476e-bba3-70930c609928) | 🧰 ✅ |
| [`copybara`](https://github.com/google/copybara) | 📦 ❌ [0 / 1](https://app.buildbuddy.io/invocation/e3b93272-ffa9-411e-b679-b584ed20e42c) | 🧰 ✅ |
| [`cpp-httplib`](https://registry-preview.bazel.build/modules/cpp-httplib/0.46.0/) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/15ca3b44-0c02-42e3-b45b-73ff4e7f1bd2) | 🧰 ✅ |
| [`cpptrace`](https://github.com/jeremy-rifkin/cpptrace) | 📦 ❌ [0 / 1](https://app.buildbuddy.io/invocation/9bc6a206-7aec-4ee1-82c2-7d017215e6fd) | 🧰 ❌ |
| [`cpu_features`](https://github.com/google/cpu_features) | 📦 ✅ [4 / 4](https://app.buildbuddy.io/invocation/e4e50218-81cf-4349-b5ca-a6737f2c5094) | 🧰 ✅ |
| [`crow`](https://github.com/CrowCpp/Crow) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/9f889ad8-e611-4d28-bf8b-704452215209) | 🧰 ✅ |
| [`cucumber-cpp`](https://registry-preview.bazel.build/modules/cucumber-cpp/0.8.0.bcr.1/) | 📦 ✅ [9 / 9](https://app.buildbuddy.io/invocation/cc5c991f-6800-4513-ab8b-32b5aa492437) | 🧰 ✅ |
| [`curl`](https://registry-preview.bazel.build/modules/curl/8.12.0.bcr.1/) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/5ef98629-173c-4ab1-a12a-7d0058ab803a) | 🧰 ✅ |
| [`cxx`](https://github.com/dtolnay/cxx) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/9bcc3aa8-fbdb-44cd-97dc-3000ce4f82eb) | 🧰 ✅ |
| [`cxxurl`](https://registry-preview.bazel.build/modules/cxxurl/0.3/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/024a5541-e0ca-4784-a0a9-51119fd04b60) | 🧰 ✅ |
| [`directxmath`](https://registry-preview.bazel.build/modules/directxmath/3.20/) | 📦 ✅ [10 / 10](https://app.buildbuddy.io/invocation/ceb1f9cf-3356-45da-ae3c-278a832c47b4) | 🧰 ✅ |
| [`doctest`](https://github.com/doctest/doctest) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/e726738c-2f38-4956-b4b5-c38cfa97c3b9) | 🧰 ❌ |
| [`double_conversion`](https://github.com/google/double-conversion) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/a14e2a07-1991-41a8-a92a-aab32c3c0d83) | 🧰 ✅ |
| [`effcee`](https://registry-preview.bazel.build/modules/effcee/0.0.0-20250222/) | 📦 ✅ [7 / 7](https://app.buildbuddy.io/invocation/57d577a5-6b32-4bcf-b17e-6bfb15c8ee49) | 🧰 ✅ |
| [`exprtk`](https://registry-preview.bazel.build/modules/exprtk/0.0.3.bcr.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/adbaf030-23d4-4077-81ae-af5c456d2b96) | 🧰 ✅ |
| [`fast_float`](https://github.com/fastfloat/fast_float) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/e2438734-cf9f-4a19-a74f-70d3aaf1e9f0) | 🧰 ✅ |
| [`fftw`](https://registry-preview.bazel.build/modules/fftw/3.3.10/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/818a786f-1f2b-472a-9bb0-7e425b8e90db) | 🧰 ✅ |
| [`flatbuffers`](https://github.com/google/flatbuffers) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/4981df14-54c5-49cb-99c2-c9a072de964e) | 🧰 ✅ |
| [`flex`](https://registry-preview.bazel.build/modules/flex/2.6.4.bcr.5/) | 📦 ✅ [16 / 16](https://app.buildbuddy.io/invocation/4088a03b-2fe7-422e-8911-ff612c2dedc3) | 🧰 ✅ |
| [`ftxui`](https://github.com/ArthurSonzogni/FTXUI) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/57783f0f-a8fe-460b-a584-a206bdf4969a) | 🧰 ✅ |
| [`fuzztest`](https://github.com/google/fuzztest) | 📦 ✅ [10 / 10](https://app.buildbuddy.io/invocation/e7c51910-1643-43af-a0c8-35ac3ee70a84) | 🧰 ✅ |
| [`fzf`](https://registry-preview.bazel.build/modules/fzf/0.71.0/) | 📦 ✅ [4 / 4](https://app.buildbuddy.io/invocation/3a7df7b3-2d4a-4043-8c8a-f17d7d4e4fac) | 🧰 ❌ |
| [`gflags`](https://github.com/gflags/gflags) | 🚫 | 🚫 |
| [`glm`](https://registry-preview.bazel.build/modules/glm/1.0.3/) | 📦 ✅ [117 / 117](https://app.buildbuddy.io/invocation/2796121d-1810-4eb9-949e-464bf3295147) | 🧰 ✅ |
| [`glog`](https://github.com/google/glog) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/4d82f8c7-7f29-45e9-88d7-3d32dd576e2b) | 🧰 ✅ |
| [`go_jsonnet`](https://github.com/google/go-jsonnet) | 📦 ✅ [8 / 8](https://app.buildbuddy.io/invocation/30c19e71-cbbc-4d30-9d82-8a0b0e1dae7f) | 🧰 ✅ |
| [`googletest`](https://github.com/google/googletest) | 📦 ✅ [41 / 41](https://app.buildbuddy.io/invocation/e949899f-e558-4698-a2ac-3b8caccc528c) | 🧰 ✅ |
| [`gperftools`](https://github.com/gperftools/gperftools) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/a1dd6390-bc86-46c3-969c-c078e1885f37) | 🧰 ✅ |
| [`grpc`](https://github.com/grpc/grpc) | 📦 ❌ [49 / 100](https://app.buildbuddy.io/invocation/e1617d2a-eeb6-49e6-a60e-7ff0c1986fd3) | 🧰 ✅ |
| [`grpc_gateway`](https://github.com/grpc-ecosystem/grpc-gateway) | 📦 ✅ [8 / 8](https://app.buildbuddy.io/invocation/4b61860b-9197-4284-a5c4-7ff5aab2cf0d) | 🧰 ❌ |
| [`gsl-lite`](https://registry-preview.bazel.build/modules/gsl-lite/1.1.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/ca38731b-3157-40e6-ba61-736014e83689) | 🧰 ✅ |
| [`hfsm2`](https://registry-preview.bazel.build/modules/hfsm2/2.10.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/32b18158-520f-4290-914b-a9f45944a306) | 🧰 ✅ |
| [`highs`](https://github.com/ERGO-Code/HiGHS) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/e03e6258-992b-4e43-a776-1bf3e6e841aa) | 🧰 ✅ |
| [`highway`](https://github.com/google/highway) | 📦 ✅ [5 / 5](https://app.buildbuddy.io/invocation/0020d934-aaec-417a-b693-385eb2dc46f1) | 🧰 ✅ |
| [`iceoryx2`](https://github.com/eclipse-iceoryx/iceoryx2) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/fbbd1192-d4f9-4e01-b653-f131c0551474) | 🧰 ✅ |
| [`icu`](https://registry-preview.bazel.build/modules/icu/78.2.bcr.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/04327330-558c-409a-b12d-e197bd426c30) | 🧰 ✅ |
| [`iperf`](https://registry-preview.bazel.build/modules/iperf/3.18.0/) | 📦 ✅ [4 / 4](https://app.buildbuddy.io/invocation/5cd98178-b2ec-42e2-9f0b-5cf91ca5234a) | 🧰 ✅ |
| [`iverilog`](https://registry-preview.bazel.build/modules/iverilog/13.0.bcr.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/880a4f5b-84cc-419c-a9b2-2090c067abd0) | 🧰 ✅ |
| [`json`](https://github.com/nlohmann/json) | 🚫 | 🚫 |
| [`jsoncpp`](https://github.com/open-source-parsers/jsoncpp) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/bb2ad7ac-759c-4e6a-9779-0d75494bc3fe) | 🧰 ✅ |
| [`jsonnet`](https://github.com/google/jsonnet) | 📦 ✅ [3 / 3](https://app.buildbuddy.io/invocation/b0fa0818-1523-4c11-b5fe-cf39c5e51e16) | 🧰 ✅ |
| [`lcm`](https://github.com/lcm-proj/lcm) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/a76bce9e-e67d-4c2f-aea1-5bbf09115a99) | 🧰 ✅ |
| [`lexbor`](https://registry-preview.bazel.build/modules/lexbor/2.4.0/) | 📦 ✅ [120 / 120](https://app.buildbuddy.io/invocation/49c86bc9-e8f7-4e02-b9c7-f7c1b19077b4) | 🧰 ✅ |
| [`lexy`](https://registry-preview.bazel.build/modules/lexy/2025.05.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/5ad5ec2f-5c73-450f-b902-a9add30757ad) | 🧰 ✅ |
| [`libavif`](https://registry-preview.bazel.build/modules/libavif/1.4.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/97c7dae7-a526-45c4-b497-b12015552328) | 🧰 ✅ |
| [`libcreate`](https://registry-preview.bazel.build/modules/libcreate/3.1.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/b4a60294-0712-4413-9850-a6e09a926766) | 🧰 ✅ |
| [`libde265`](https://registry-preview.bazel.build/modules/libde265/1.0.18/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/dd503d08-1ba5-4182-9a80-600f8d5ece7f) | 🧰 ✅ |
| [`libdwarf`](https://registry-preview.bazel.build/modules/libdwarf/2.2.0.bcr.1/) | 📦 ✅ [18 / 18](https://app.buildbuddy.io/invocation/bdf7766f-93af-4230-bfd0-fa5931f10dc5) | 🧰 ✅ |
| [`libevent`](https://registry-preview.bazel.build/modules/libevent/2.1.12-stable.bcr.0/) | 📦 ✅ [10 / 10](https://app.buildbuddy.io/invocation/34978759-6979-4c26-b262-61787fb5896b) | 🧰 ✅ |
| [`libfastjson`](https://registry-preview.bazel.build/modules/libfastjson/1.2304.0/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/939e40d9-dee2-4ad4-a236-6a3cf91bf43a) | 🧰 ✅ |
| [`libgd`](https://registry-preview.bazel.build/modules/libgd/2.3.3/) | 📦 ✅ [6 / 6](https://app.buildbuddy.io/invocation/4e8305ee-6097-48d7-a41d-4fd75ee63c6c) | 🧰 ✅ |
| [`libgit2`](https://registry-preview.bazel.build/modules/libgit2/1.9.2.bcr.1/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/b66adc39-ded7-41dd-a0f6-d0a35d8f4cea) | 🧰 ✅ |
| [`libheif`](https://registry-preview.bazel.build/modules/libheif/1.21.2/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/98921ed1-9365-41e2-953c-693a31b1e7c0) | 🧰 ✅ |
| [`libpcap`](https://registry-preview.bazel.build/modules/libpcap/1.10.5.bcr.3/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/a8955539-1a3c-43c2-b68f-34a77315768d) | 🧰 ✅ |
| [`libwebsockets`](https://registry-preview.bazel.build/modules/libwebsockets/4.5.2/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/4912c6d4-b2c5-4561-9d1e-7889b6a0ddc6) | 🧰 ✅ |
| [`llvm-project`](https://registry-preview.bazel.build/modules/llvm-project/17.0.4.bcr.1/) | 📦 ✅ [5 / 5](https://app.buildbuddy.io/invocation/d5885dd1-a810-4a61-a207-eecd2efe6f0e) | 🧰 ❌ |
| [`magic_enum`](https://github.com/Neargye/magic_enum) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/dc9be948-ed76-4b76-844c-045862e5aeb8) | 🧰 ✅ |
| [`marisa-trie`](https://registry-preview.bazel.build/modules/marisa-trie/0.3.1.bcr.2/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/4b7151a6-9716-4379-a0c6-41edec1bc07c) | 🧰 ✅ |
| [`nsync`](https://github.com/google/nsync) | 📦 ✅ [7 / 7](https://app.buildbuddy.io/invocation/173364a7-6379-4127-b984-a24892fe0461) | 🧰 ✅ |
| [`ogg`](https://registry-preview.bazel.build/modules/ogg/1.3.5.bcr.3/) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/94f6e436-9ddb-4e0d-aff9-69edb1556280) | 🧰 ✅ |
| [`onetbb`](https://github.com/uxlfoundation/oneTBB) | 📦 ✅ [4 / 4](https://app.buildbuddy.io/invocation/da8f7282-2d67-49d9-afa0-ca6938b99b0c) | 🧰 ✅ |
| [`opencc`](https://github.com/BYVoid/OpenCC) | 📦 ✅ [19 / 19](https://app.buildbuddy.io/invocation/5364edda-6605-472d-9f07-d2aea0816295) | 🧰 ✅ |
| [`opencl-sdk`](https://registry-preview.bazel.build/modules/opencl-sdk/2025.07.23/) | 📦 ✅ [10 / 10](https://app.buildbuddy.io/invocation/7b365e25-2db9-4380-9be1-10b2422474ce) | 🧰 ✅ |
| [`openexr`](https://github.com/AcademySoftwareFoundation/openexr) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/49309456-99d9-4885-a612-f9da2315a9af) | 🧰 ✅ |
| [`openssl`](https://registry-preview.bazel.build/modules/openssl/3.5.5.bcr.4/) | 📦 ✅ [2 / 2](https://app.buildbuddy.io/invocation/7c8e6377-b0d8-4ddc-8411-ce001c246011) | 🧰 ✅ |
| [`opentelemetry_cpp`](https://github.com/open-telemetry/opentelemetry-cpp) | 📦 ✅ [42 / 42](https://app.buildbuddy.io/invocation/cbee6888-dc1e-406f-807e-5f8130a6f31b) | 🧰 ✅ |
| [`ortools`](https://github.com/google/or-tools) | 📦 ✅ [89 / 89](https://app.buildbuddy.io/invocation/e140fb78-050f-492f-abb3-a3f5ece0abfb) | 🧰 ✅ [87 / 89](https://app.buildbuddy.io/invocation/7ecbdebc-d5e0-4810-8508-a146477fb8cf) |
| [`pcre2`](https://github.com/PCRE2Project/pcre2) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/dc946879-2000-4a29-b160-271eb1b98dad) | 🧰 ✅ |
| [`prometheus_cpp`](https://github.com/jupp0r/prometheus-cpp) | 📦 ✅ [1 / 1](https://app.buildbuddy.io/invocation/35b4ecc6-7c5c-4d57-ad03-e2b5c58df5bb) | 🧰 ✅ |
| [`protobuf`](https://github.com/protocolbuffers/protobuf) | 📦 ✅ [101 / 102](https://app.buildbuddy.io/invocation/59828833-9399-408f-84b9-022d02533f46) | 🧰 ✅ |
| [`quill`](https://github.com/odygrd/quill) | 🚫 | 🚫 |
| [`re2`](https://github.com/google/re2) | 📦 ✅ [16 / 16](https://app.buildbuddy.io/invocation/078fe8ea-dee1-4a63-a936-3729d540f165) | 🧰 ✅ |
| [`reflexxes-rmltype2`](https://registry-preview.bazel.build/modules/reflexxes-rmltype2/1.2.7/) | 📦 ✅ | 🧰 ✅ |
| [`rocksdb`](https://registry-preview.bazel.build/modules/rocksdb/9.11.2/) | 📦 ✅ | 🧰 ✅ [10 / 10](https://app.buildbuddy.io/invocation/f5f77e34-30d7-455a-85a0-1dd0e8de6514) |
| [`rsyslog`](https://registry-preview.bazel.build/modules/rsyslog/8.2504.0/) | 📦 ✅ | 🧰 ❌ |
| [`rules_multirun`](https://registry-preview.bazel.build/modules/rules_multirun/0.14.0/) | 📦 ✅ | 🧰 ✅ |
| [`s2geometry`](https://github.com/google/s2geometry) | 📦 ✅ | 🧰 ✅ |
| [`sdl2`](https://registry-preview.bazel.build/modules/sdl2/2.32.0.bcr.beta.6/) | 📦 ✅ | 🧰 ✅ |
| [`sdl2_mixer`](https://registry-preview.bazel.build/modules/sdl2_mixer/2.8.1.bcr.beta.2/) | 📦 ✅ | 🧰 ✅ |
| [`simdutf`](https://registry-preview.bazel.build/modules/simdutf/7.7.0/) | 📦 ✅ | 🧰 ✅ |
| [`snappy`](https://github.com/google/snappy) | 📦 ✅ | 🧰 ✅ |
| [`squashfs-tools`](https://registry-preview.bazel.build/modules/squashfs-tools/4.7.5/) | 📦 ✅ | 🧰 ✅ |
| [`systemc`](https://registry-preview.bazel.build/modules/systemc/3.0.2.bcr.1/) | 📦 ✅ | 🧰 ✅ |
| [`tinyformat`](https://registry-preview.bazel.build/modules/tinyformat/2.3.0/) | 📦 ✅ | 🧰 ✅ |
| [`tinyxml2`](https://registry-preview.bazel.build/modules/tinyxml2/11.0.0/) | 📦 ✅ | 🧰 ✅ |
| [`tomlplusplus`](https://registry-preview.bazel.build/modules/tomlplusplus/3.4.0/) | 📦 ✅ | 🧰 ✅ |
| [`trlc`](https://registry-preview.bazel.build/modules/trlc/2.0.5/) | 📦 ✅ | 🧰 ✅ |
| [`universal-robots-client-library`](https://registry-preview.bazel.build/modules/universal-robots-client-library/2.4.0/) | 📦 ✅ | 🧰 ✅ |
| [`verible`](https://github.com/chipsalliance/verible) | 📦 ✅ | 🧰 ✅ |
| [`verilator`](https://registry-preview.bazel.build/modules/verilator/5.046.bcr.5/) | 📦 ✅ | 🧰 ❌ [0 / 3](https://app.buildbuddy.io/invocation/d672774e-7791-4219-b09d-71f9be5fe4f1) |
| [`xkbcommon`](https://registry-preview.bazel.build/modules/xkbcommon/1.9.2.bcr.beta.1/) | 📦 ✅ | 🧰 ✅ |
| [`z3`](https://github.com/Z3Prover/z3) | 🚫 | 🚫 |
| [`zlib`](https://github.com/madler/zlib) | 🚫 | 🚫 |
| [`zstd`](https://registry-preview.bazel.build/modules/zstd/1.5.7.bcr.1/) | 📦 ✅ | 🧰 ✅ |
| [`zziplib`](https://registry-preview.bazel.build/modules/zziplib/0.13.72/) | 📦 ✅ | 🧰 ✅ |

## Project Notes

Notes are keyed by `(project, test env)` for active non-green cells in the
status table above.

| project | test env | status | note |
| --- | --- | --- | --- |
| [`aravis`](https://registry-preview.bazel.build/modules/aravis/0.9.2-20251111063445-57983d013883/) | `rbe` | 🧰 ❌ | The hermetic LLVM variant fixes glib Python codegen and uses preinstalled `make`/`pkg-config`, but libxml2 still builds through `rules_foreign_cc` outside Bazel's C++ rule flow; the zero-sysroot hermetic clang cannot find crt objects such as `Scrt1.o`. |
| [`bazel`](https://github.com/bazelbuild/bazel) | `rbe` | 💤 | No hermetic LLVM RBE test target is tracked yet; this large project is kept out of the regular hermetic RBE test sweep. |
| [`behaviortree_cpp`](https://registry-preview.bazel.build/modules/behaviortree_cpp/4.7.0.bcr.3/) | `rbe` | 🧰 ❌ | Its BCR `sed` dependency uses gnulib code that does not parse under clang 22 (`_GL_ATTRIBUTE_FORMAT_PRINTF_STANDARD`). |
| [`copybara`](https://github.com/google/copybara) | `local` | 📦 ❌ [0 / 1](https://app.buildbuddy.io/invocation/e3b93272-ffa9-411e-b679-b584ed20e42c) | The as-is local wrapper reaches Copybara analysis, but `rules_java` selects `local_jdk` inside the sandbox and analysis fails before upstream test targets are found. |
| [`cpptrace`](https://github.com/jeremy-rifkin/cpptrace) | `local` | 📦 ❌ [0 / 1](https://app.buildbuddy.io/invocation/9bc6a206-7aec-4ee1-82c2-7d017215e6fd) | The as-is local Bazel test target fails. The underlying gtest binary runs 91 cases and reports 85 passing and 6 failing, all in stack-trace resolution/current-trace behavior. |
| [`grpc`](https://github.com/grpc/grpc) | `local` | 📦 ❌ [49 / 100](https://app.buildbuddy.io/invocation/e1617d2a-eeb6-49e6-a60e-7ff0c1986fd3) | The as-is local suite ran 100 Bazel test targets: 49 passed, 1 failed to build, and 50 were skipped. |
| [`llvm-project`](https://registry-preview.bazel.build/modules/llvm-project/17.0.4.bcr.1/) | `rbe` | 🧰 ❌ | The hermetic LLVM RBE variant analyzes and one unit test target passes, but several LLVM unit test targets fail to build: `SupportHelpers.h` includes private `gtest/gtest-printers.h`, and later Hexagon code hits libc++ comparator errors involving deleted `operator<` for `llvm::rdf::RegisterRef`. |
| [`rsyslog`](https://registry-preview.bazel.build/modules/rsyslog/8.2504.0/) | `rbe` | 🧰 ❌ | The hermetic build issues are fixed, but the upstream smoke test drives `rsyslogd` with `nc -u -w 0`, which only the netcat-openbsd CLI accepts; the executor images provide a different variant. |
| [`verilator`](https://registry-preview.bazel.build/modules/verilator/5.046.bcr.5/) | `rbe` | 🧰 ❌ [0 / 3](https://app.buildbuddy.io/invocation/d672774e-7791-4219-b09d-71f9be5fe4f1) | The hermetic LLVM RBE variant analyzes the test suite, but all three regression tests fail to build because Verilator binaries link with `-latomic` and hermetic `ld.lld` cannot find `libatomic` on the RBE image. |
| [`brotli_go`](https://github.com/google/brotli) | `rbe` | 🧰 ❌ | The nested Go module pulls in the parent C brotli library, but that nested module still selects host C/C++ tools on RBE (`/bin/gcc`/`cc`), so the hermetic LLVM variant fails before the Go tests build. |
| [`cpptrace`](https://github.com/jeremy-rifkin/cpptrace) | `rbe` | 🧰 ❌ | The transitive `toolchains_llvm` clang used by dependencies such as `xz` and `zstd` needs `libtinfo.so.5` on the RBE image; `rules_foreign_cc` make bootstrap also fails because that compiler cannot create executables. |
| [`doctest`](https://github.com/doctest/doctest) | `rbe` | 🧰 ❌ | The nested `examples/` module still selects `/bin/gcc` on RBE instead of the injected hermetic LLVM toolchain, so the example test fails to compile. |
| [`fzf`](https://registry-preview.bazel.build/modules/fzf/0.71.0/) | `rbe` | 🧰 ❌ | The Go targets build through hermetic clang on RBE, but cgo-style Go linking fails with non-PIC relocation errors from `ld.lld`. |
| [`grpc_gateway`](https://github.com/grpc-ecosystem/grpc-gateway) | `rbe` | 🧰 ❌ | The Go tests pass, but top-level Go binaries built during the sweep fail to link through hermetic clang with non-PIC relocation errors from `ld.lld`. |
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
