# bazel-matrix

Builds and tests popular public Bazel projects together, in one Bazel module
graph. Each project is a module from the
[Bazel Central Registry](https://registry.bazel.build/) (BCR), declared as a
`bazel_dep` in `MODULE.bazel`, and gets a generated package at
`//<module>/`:

- one `alias` per buildable (non-test, non-manual) target of `@<module>//...`,
  named after its package path (`@abseil-cpp//absl/strings:strings` is
  `//abseil-cpp:absl_strings__strings`);
- one `test_suite` named `tests` that lists every test of `@<module>//...`.

So `//...` covers every project, and `//<module>/...` covers one.

## Commands

Everything runs on BuildBuddy RBE through `bb remote`. `bb remote` itself
must be told to use the same image as the executors, so the C++ toolchain
it autodetects on the runner works on them:

```sh
BB="bb remote --container_image=docker://gcr.io/flame-public/rbe-ubuntu22-04:latest"
$BB build //... --config=remote-minimal
$BB test //... --config=remote-minimal
$BB test //zlib/... --config=remote-minimal   # one project
```

`--config=remote-minimal` (in `.bazelrc`) sets the BuildBuddy endpoints,
`--remote_download_minimal`, `--jobs=100` and the executor image. Read test
logs with `bb view <invocation>`; `bb remote` pushes nothing, but its runner
clones from GitHub and applies your local diff, so commits must be pushed.

## Layout

- `MODULE.bazel`: the projects. Every non-dev `bazel_dep` is one. The block
  at the end is generated.
- `tools/sync.py`: regenerates everything else. Run `python3 tools/sync.py`
  after any change to `MODULE.bazel` or `exclusions.txt`; it should leave no
  diff when nothing changed. It
  1. fetches each project's `MODULE.bazel` from the BCR and, if it has dev
     dependencies, writes `patches/<module>.patch` making them regular
     dependencies, plus a `single_version_override` applying it. (Dev deps of
     non-root modules are ignored, so without this most tests don't even
     analyze.) Dev deps the module overrides itself or that the BCR lacks
     stay dev-only, along with anything that uses them;
  2. queries every project's targets with one `bb remote query`;
  3. drops what `exclusions.txt` matches, plus everything depending on it;
  4. writes `<module>/BUILD.bazel` and refreshes `MODULE.bazel.lock`.
- `exclusions.txt`: targets to leave out, each with a reason.
- `patches/`, `<module>/BUILD.bazel`, `MODULE.bazel.lock`: generated; don't
  edit by hand.

`.bazelrc` also sets `--nocheck_visibility` (the aliases point at targets
private to their modules) and a remote JDK (the executors have none).

## Adding a project

Add `bazel_dep(name = "<module>", version = "<latest BCR version>")` to
`MODULE.bazel`, run `python3 tools/sync.py`, then build and test `//...`.
Fix failures by excluding targets in `exclusions.txt` with the reason, then
sync again. To drop a project, comment out its `bazel_dep` with the reason.

## Dropped projects

None so far.
