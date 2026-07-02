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

## Sweep results

See the table below; refreshed by running `bazel test //:hermetic_llvm_rbe_tests`
(and `//:as_is_rbe_tests` for the as-is column where projects pass as-is).

| project | variant | rbe_test | note |
| --- | --- | --- | --- |
| (pending sweep) | | | |
