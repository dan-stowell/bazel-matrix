# bazel-matrix

Builds and tests popular public Bazel projects from the
[Bazel Central Registry](https://registry.bazel.build/) (BCR). Each project
is built as the root module of its own workspace, from its own source at its
BCR release, by an inner Bazel; an outer Bazel (this repo) drives the inner
ones. Every project gets a generated package `//<module>/` with two targets:

- `//<module>:build` runs inner `bazel build -- //... <exclusions>` and
  writes a summary (inner invocation link, counts) and the inner log;
- `//<module>:test` runs inner `bazel test -- //... <exclusions>` and writes
  one test.xml testcase per inner test target (plus one per non-test target
  that failed to build), so per-target results show in the outer invocation.
  The test log has the inner output and the inner invocation link.

Both are outer actions, so the outer remote cache serves a project whose
inputs (source, flags, inner Bazel, rc files, runner) haven't changed.

## Commands

Everything runs on BuildBuddy RBE through `bb remote`, which must be told to
use the same image as the executors, so the C++ toolchain the inner Bazels
autodetect on the runner works on them:

```sh
BB="bb remote --container_image=$(grep -o 'container-image=[^ ]*' tools/remote.bazelrc | cut -d= -f2)"
$BB build //... --config=remote-minimal     # every project's inner build
$BB test //... --config=remote-minimal      # every project's inner test
$BB test //zlib/... --config=remote-minimal # one project
$BB test //tools/... --config=remote-minimal # this repo's unit tests
```

Extra flags for every inner Bazel, without editing files:

```sh
$BB test //re2/... --config=remote-minimal --//:inner_flags=--test_tag_filters=-slow --//:inner_flags=--copt=-O1
$BB test //zlib/... --config=remote-minimal --//:inner_bazel_version=8.4.2
```

`bb remote` downloads the top-level outputs afterwards from its own cache
endpoint, which may report `download blob ... NotFound` and exit 1 even
though the outer Bazel succeeded; the runner log's `(command exited with
code N)` is the real result. Read inner logs with `bb view <inner
invocation>`; `bb remote`'s runner clones from GitHub and applies your local
diff.

## How an inner build runs

`tools/inner_bazel.py`, as the action or test, on the machine running the
outer Bazel (`no-remote-exec`, `no-sandbox`; not `local`, so results are
cached):

1. extracts the project's `source.tar` into a fresh work dir under
   `/tmp/bazel-matrix/work`;
2. runs the pinned inner Bazel there with `--batch`, its own output user
   root, the project's own `.bazelrc` (but no system or home rc), then
   `--bazelrc=tools/remote.bazelrc --bazelrc=tools/inner.bazelrc` (RBE with
   `--config=remote-minimal`), the project's flags and `--//:inner_flags`;
3. deletes the work dir (also on timeout or SIGTERM, and stale ones left by
   killed runs), so a runner's disk doesn't grow per run. Downloads go to a
   repository cache shared on the machine
   (`/tmp/bazel-matrix/repository_cache`) and through BuildBuddy's remote
   downloader; reproducible repos come from the remote repo contents cache.

Each inner run is tagged `resources:cpu:2`/`resources:memory:2500`, so a
6-CPU, 7 GB runner runs two at a time.

The BuildBuddy API key reaches the inner Bazels through a credential helper
(`tools/buildbuddy_credential_helper.py`), which reads a file that the
`@buildbuddy_credentials` repo rule writes from the outer client
environment (`tools/credentials.bzl`). The key is never an action input or
environment variable, so it's in no action key.

## Layout

- `projects.txt`: the projects, and per project the inner targets to leave
  out, extra inner flags and an optional pinned inner Bazel, each with a
  reason. The one hand-edited input.
- `tools/sync.py`: run `python3 tools/sync.py` after changing
  `projects.txt`; re-running it changes nothing. It keeps a sparse clone of
  the BCR in `~/.cache/bazel-matrix/bcr` at the commit `projects.json`
  records (`--update` moves to the BCR's HEAD), picks each project's version
  (pinned, else the latest stable, non-yanked one whose
  `bazel_compatibility` admits `.bazelversion`), and writes
  - `projects.json`: the BCR commit and each project's version and source
    (archive, integrity, patches, overlay and the registry's MODULE.bazel,
    as `bcr.bazel.build` URLs with integrity);
  - `<module>/BUILD.bazel`, deleting those of projects no longer listed.
- `tools/sources.bzl`: the module extension reading `projects.json`; one
  lazily fetched repo per project (`@projects//:<module>` is its
  `source.tar`: the archive with patches and overlay applied and the
  registry's MODULE.bazel, as a deterministic tar).
- `tools/project.bzl`: the `build` and `test` rules and the pinned inner
  Bazel versions (`INNER_BAZELS`, fetched in `MODULE.bazel`).
- `tools/remote.bazelrc`: `--config=remote-minimal` (BuildBuddy endpoints,
  `--remote_download_minimal`, `--jobs=100`, the executor image pinned by
  digest, remote downloader, `--rewind_lost_inputs`, remote JDK), for the
  outer and every inner Bazel. The one place the image is defined.
- `tools/inner.bazelrc`: flags for every inner Bazel.

## Adding or fixing a project

Add its module name to `projects.txt`, run `python3 tools/sync.py`, then
build and test `//<module>/...`. Fix failures with an exclusion
(`-//pattern`) or a flag (`--flag`), each with the reason, then sync again.
A package that fails to load breaks `//...` even when excluded; delete it
with `--deleted_packages=<pkg>` instead. A project that needs a different
inner Bazel gets `bazel <version>` (add the version to `INNER_BAZELS` and
`MODULE.bazel` first).

Only `archive` BCR sources are supported so far; sync fails for
`git_repository` ones.
