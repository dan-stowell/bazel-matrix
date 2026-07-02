# RBE Test Status

Goal: get upstream project test suites passing on BuildBuddy RBE, preferring the
hermetic-llvm toolchain (`bazel_dep(name = "llvm")`, hermeticbuild/hermetic-llvm)
over toolchains_buildbuddy.

## Finding: dynamic C++ runtime linking breaks RBE tests (2026-07-02)

With the hermetic-llvm toolchain, `*_rbe_build` targets passed but every
`*_rbe_test` target with C++ test binaries failed at runtime with:

```
symbol lookup error: /usr/local/lib/libc++abi.so.1: undefined symbol: __msan_va_arg_overflow_size_tls
```

Chain of causes:

1. `cc_test` defaults to `linkstatic = 0`, so test binaries link the C++
   runtime (`libc++.so.1`, `libc++abi.so.1`) dynamically. `cc_binary` defaults
   to `linkstatic = 1`, which is why RBE *builds* passed while RBE *tests*
   failed.
2. On the BuildBuddy worker the dynamic loader does not resolve the hermetic
   toolchain's solib entries from the test's runfiles layout, and falls back to
   the ld.so search path.
3. The default BuildBuddy executor image ships its own
   `/usr/local/lib/libc++abi.so.1` that is incompatible (appears
   msan-instrumented), so the lookup fails with the msan TLS symbol error.
   Locally the runfiles solib symlinks resolve, so `*_local_test` never sees
   this.

## Decision: force static linking in the hermetic_llvm modification

`--dynamic_mode=off` is added to the `hermetic_llvm` overlay's `build_flags`
(see `_HERMETIC_LLVM_MODIFICATION` in `bazel_runner/defs.bzl`). Test binaries
then statically link libc++/libc++abi/libunwind and only depend on the worker's
glibc (hermetic-llvm targets glibc 2.28, old enough for any current image).

Verified: `//projects/fast_float/hermetic_llvm:fast_float_rbe_test` went from
2 remote test failures to passing with only this flag changed
(https://app.buildbuddy.io/invocation/b0a4d3ff-ff70-4cff-865a-5f930c4757eb).

Alternatives considered:

- **Per-target `linkstatic`/rpath fixes inside each upstream project**: not
  viable; the matrix intentionally runs upstream sources unmodified apart from
  declared overlays.
- **`--remote_default_exec_properties=container-image=docker://ubuntu:22.04`**
  (hermetic-llvm even ships `rbe.bzl` doing exactly this): avoids the *broken*
  system libc++abi, but the hermetic solibs still fail to resolve from
  runfiles, so dynamically linked tests would fail with "cannot open shared
  object file" instead. Static linking fixes the root cause and keeps the test
  independent of the worker image.
- **toolchains_buildbuddy**: works only on BuildBuddy's images and is the
  non-preferred option for this repo.

## Finding: default executor image is too old (2026-07-02)

With static linking in place, glm still failed 2 of 117 tests with
`libm.so.6: version GLIBC_2.27 not found`: BuildBuddy's default executor image
is Ubuntu 16.04 (glibc 2.23), older than hermetic-llvm's default glibc 2.28
target. Decision: the `buildbuddy_rbe` overlay now sets
`--remote_default_exec_properties=container-image=docker://ubuntu:22.04`
(hermetic-llvm's own `rbe.bzl` pins the same image). This only applies when the
execution platform defines no exec_properties, so RBE-aware projects keep their
own image. glm then passes 117/117.

## Finding: llvm 0.7.3 is incompatible with rules_cc 0.2.19+ (2026-07-02)

boringssl (which pins rules_cc 0.2.19) failed analysis: hermetic-llvm 0.7.3's
toolchain `select()`s on `@rules_cc//cc/toolchains/args/archiver_flags:use_libtool_on_macos_setting`,
which rules_cc 0.2.19 removed. Decision: bump the appended module to
`llvm` 0.8.11 (2026-06-26; depends on rules_cc 0.2.20). boringssl's
hermetic_llvm rbe_test then passes.

## Finding: python needs a hermetic interpreter and the script bootstrap

Anything python touches fails on RBE workers because the images ship no
`python3`:

- Projects registering `@rules_python//python/runtime_env_toolchains:all`
  (abseil_py) resolve `python3` from PATH at runtime. Fix: overlay the
  variant's MODULE.bazel to request a hermetic interpreter instead
  (`projects/abseil_py/hermetic.MODULE.bazel`).
- Even with a hermetic runtime, rules_python's default
  `bootstrap_impl=system_python` stage-1 stub execs `/usr/bin/env python3`.
  Fix: `--@rules_python//python/config_settings:bootstrap_impl=script`. Two
  reusable overlays exist: `HERMETIC_PYTHON` (appends a root rules_python dep
  so the flag's repo is addressable + the flag) and `HERMETIC_PYTHON_FLAGS`
  (flag only, for projects whose MODULE already declares rules_python —
  appending a duplicate bazel_dep is an error). This covers py_test wrappers
  (effcee, googletest) and build-time py_binary codegen tools (lcm's glib,
  opencc), since the flag reaches exec-config tools too.

## Environmental exclusions (exclude_on = {"rbe": [...]})

- `abseil_cpp` `//absl/time:time_test`: reads the host timezone database and
  has no zoneinfo data dep (the cctz tests bundle testdata/zoneinfo and pass
  with `--test_env=TZDIR=...`).
- `abseil_py` `//absl/flags:tests/flags_test`: its no-permissions test chmods
  a file unreadable; RBE executors run as root, which ignores permissions.
- `protobuf` `//src/google/protobuf/compiler:protoc_x86_64_test`: shells out
  to the `file` utility, absent on executor images.

## Sweep results (2026-07-02)

`bazel test //:hermetic_llvm_rbe_tests`: **47 of 47 pass**
(https://app.buildbuddy.io/invocation/18f1e442-7034-4bcb-bb81-aec97b5e2d1d).

Passing projects (hermetic_llvm variant, RBE test):
abseil_cpp, abseil_py, benchmark, boringssl, ccronexpr, cctz, cityhash,
cjson, cpp-httplib, cpu_features, cxxurl, directxmath, double_conversion,
effcee, exprtk, fast_float, flatbuffers, ftxui, fuzztest, glm, googletest,
gperftools, gsl-lite, hfsm2, highway, jsoncpp, lcm, lexbor, libfastjson,
marisa-trie, nsync, ogg, onetbb, opencc, openexr, pcre2, prometheus_cpp,
protobuf, re2, s2geometry, simdutf, snappy, tinyformat, tinyxml2,
tomlplusplus, verible, zstd.
