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

Everything runs on BuildBuddy RBE through `bb remote`; `tools/bb.sh` adds
the runner image and `--config=remote-minimal`:

```sh
tools/bb.sh build //...          # every project's inner build
tools/bb.sh test //...           # every project's inner test
tools/bb.sh test //zlib/...      # one project
tools/bb.sh test //tools/...     # this repo's unit tests
tools/bb.sh test //re2:test --//:inner_flags=--test_tag_filters=-slow  # extra inner flags (repeatable)
tools/bb.sh test //zlib:test --//:inner_bazel_version=8.4.2            # another pinned inner Bazel
tools/bb.sh test //... --test_output=all  # print every project's summary and inner link
```

For the whole matrix, `tools/run.py` splits the projects over concurrent
`bb remote` runs (each gets its own runner) and prints each shard's
invocation links and a pass/fail row per project:

```sh
tools/run.py test --shards 8     # every project, 8 runners
tools/run.py build zlib re2      # some projects
tools/run.py test --known-failing  # also the known-failing ones
```

Like `//...`, it leaves out `known-failing build` projects, and for a
`known-failing test` project `test` runs its `:build` (row `BUILT`), so
regressions of its inner build still show. A known-failing project that
does run (named, or with `--known-failing`) shows its result with its mark:
`FAILED (known-failing build)` is expected and doesn't fail the run, while
`PASSED (known-failing build: candidate to un-mark)` is listed as a
candidate. `known-failing build` excuses build and test failures;
`known-failing test` only test failures, so its build failing is a
regression. A shard's result is its runner
Bazel's exit code: `bb remote` can exit 1 afterwards when downloading the
outputs fails, and run.py prints a warning when the two disagree. A project
whose inner `bazel test` finds no tests (exit 4) passes; its summary and
test.xml say `NO_TESTS` (run.py's table can't see that: it would need the
test logs).

`tools/bb.sh` asks for a 16-CPU, 32 GB runner
(`--runner_exec_properties=EstimatedCPU=16,EstimatedMemory=32GB`; the
default is 6 CPUs, 7 GB), which runs about 8 inner Bazels at once.

Passing projects' logs (summary, inner invocation link) only print with
`--test_output=all`; that flag isn't in the action key, so it replays cached
results. Read inner logs with `bb view <inner invocation>`.

Caveats: `bb remote` runs your local diff against the default branch on the
runner (commits need not be pushed). Afterwards it downloads the top-level
outputs from its own cache endpoint, which can fail with `download blob ...
NotFound` and exit 1 although the outer Bazel succeeded; the runner log's
`(command exited with code N)` is the real result.

## How an inner build runs

`tools/inner_bazel.py`, as the action or test, on the machine running the
outer Bazel (`no-remote-exec`, `no-sandbox`; not `local`, so results are
cached):

1. extracts the project's `source.tar` into a fresh work dir under
   `/var/tmp/bazel-matrix/work` (not `/tmp`, where Bazel 9's hermetic tmp
   breaks locally sandboxed inner actions);
2. runs the pinned inner Bazel there with `--batch`, its own output user
   root, a 2 GB JVM heap, a minimal explicit environment, the project's own
   `.bazelrc` (but no system or home rc), then
   `--bazelrc=tools/remote.bazelrc --bazelrc=tools/inner.bazelrc` (RBE with
   `--config=remote-minimal`), the project's flags and `--//:inner_flags`;
3. deletes the work dir, also on SIGTERM (it kills the inner Bazel first)
   and when a killed run left one behind, so a runner's disk doesn't grow
   per run. Nothing is cached on the runner between runs: fetches go
   through BuildBuddy's remote downloader, and reproducible repos come from
   the remote repo contents cache.

Each inner run is tagged `resources:cpu:2`/`resources:memory:2500`, so a
6-CPU, 7 GB runner runs two at a time and the 16-CPU, 32 GB one
`tools/bb.sh` requests about eight.

The BuildBuddy API key reaches the inner Bazels through a credential helper
(`tools/buildbuddy_credential_helper.py`) reading a file that the
`@buildbuddy_credentials` repo rule writes from the outer client
environment into the outer output base, and deletes when the variable is
unset (`tools/credentials.bzl`); `tools/inner_bazel.py` finds it from its
working directory. Neither the key nor its location is an action input or
environment variable, so the outer cache is shared across checkouts.

## Inner Bazels on RBE

Opt-in, and off by default (the matrix above is unchanged by it): with
`--config=inner-remote` (root `.bazelrc`) each project's `:test` runs on an
RBE executor, in the image of `tools/remote.bazelrc`, instead of on the
machine running the outer Bazel. Its inner Bazel's host is then the image
and arch under test, so an autodetected C++ toolchain matches the
executors, and inner Bazels run in parallel on RBE rather than on one
machine. `--config=inner-remote-arm64` does the same on arm64 executors: the
outer targets `//tools:linux_arm64` (also its execution platform, so the
test runs the linux-arm64 inner Bazel of `tools/versions.bzl`), with
`Arch=arm64` for outer and inner actions. `:build`
stays local, so it is incompatible (skipped) when targeting arm64, and a
pinned inner Bazel without a linux-arm64 binary fails analysis there.

```sh
bazel test //zlib:test --config=remote-minimal --config=inner-remote-arm64 \
  --credential_helper=*.buildbuddy.io=$PWD/tools/remote_exec_credential_helper.py
```

That runs the outer Bazel itself rather than through `bb remote` (whose
runners can't target arm64); use the Bazel binary, not the bb CLI, which
puts the key in Bazel's argv. `--//:inner_remote` drops the test's
`no-remote-exec`/`no-sandbox`/`requires-network` and runs
`tools/remote_inner_bazel.py` with the image's `python3` (a py_binary
would need a zipper, so a C++ toolchain, built for the executor); the config also asks for 4 CPUs, 8 GB and
20 GB of disk (BuildBuddy may size the task by its own prediction).

The key: `tools/remote_exec_credential_helper.py` (with
`$BAZEL_MATRIX_KEY_FILE` naming a 0600 file with the key) adds the header
`x-buildbuddy-platform.env-overrides: BUILDBUDDY_API_KEY=<key>`, which
BuildBuddy sets in the remote test's environment but keeps out of the
action key and redacts. `tools/remote_inner_bazel.py` moves it into a 0600
file for the inner Bazel's credential helper. As a helper's header it isn't
on Bazel's command line, so not in its logs or build event files (a
`--remote_exec_header` flag would be). Bazel caches helper results in its
server: after switching helpers, `bazel shutdown`. The header reaches
every remote action of the invocation, so run only `//<project>:test`
targets with these configs: the tests of `//tools` and `//canary` are
incompatible under `--//:inner_remote`.

Remotely the inner work dir is under `$TEST_TMPDIR` (the action's disk,
which `EstimatedFreeDiskBytes` covers), and the inner Bazel gets
`--local_resources=cpu=4,memory=6000` rather than sizing itself from the
executor host. A wrapper that ran to the end prints
`bazel-matrix: inner bazel finished (exit N)` last; one killed from outside
(OOM, lost executor, signal) doesn't, and its test.xml is the one written
first, whose only testcase is `infra_killed`. Count such a run as an
infrastructure failure, not the project's, and retry it. (BuildBuddy itself
reruns a task whose executor was lost: one aspect_rules_js test action had
three inner invocations, the first two cut off.)

## Layout

- `projects.txt`: the projects, and per project the inner targets to leave
  out, extra inner flags and an optional pinned inner Bazel, each with a
  reason. The one hand-edited input.
- `tools/sync.py`: run `python3 tools/sync.py` after changing
  `projects.txt`; re-running it changes nothing. It keeps a sparse clone of
  the BCR in `~/.cache/bazel-matrix/bcr` at the commit `projects.json`
  records (`--update` moves to the BCR's HEAD), picks each project's version
  (pinned, else the newest stable, non-yanked one whose
  `bazel_compatibility` admits `DEFAULT_INNER_BAZEL`), and writes
  - `projects.json`: the BCR commit and each project's version and source
    (archive, integrity, overlay, patches and the registry's MODULE.bazel,
    as `bcr.bazel.build` URLs with integrity), and the projects it skipped
    (deprecated, no compatible version, unsupported source type) with why;
  - `<module>/BUILD.bazel`, deleting those of projects no longer listed.

  `//tools:generated_test` fails when the committed `projects.json` or
  `<module>/BUILD.bazel` files don't match `projects.txt` (sync wasn't
  re-run). A blank line ends a project's indented lines. Changes that only
  matter through the BCR (unpinning a project, `bazel <v>` lines,
  `DEFAULT_INNER_BAZEL`) aren't checked.
- `tools/sources.bzl`: the module extension reading `projects.json`; one
  lazily fetched repo per project (`@projects//:<module>` is its
  `source.tar`: the archive with the overlay, then the patches, then the
  registry's MODULE.bazel applied, as http_archive does for a registry
  module, as a deterministic tar), and the inner Bazels.
- `tools/project.bzl`: the `build` and `test` rules.
- `tools/run.py`: shards `build` or `test` over concurrent `bb remote` runs.
- `tools/versions.bzl`: the pinned inner Bazels (version, sha256, startup
  flags) and `DEFAULT_INNER_BAZEL`; the one place they're defined.
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
with `--deleted_packages=<pkg>` instead. A project that is fundamentally broken here
(doesn't load under Bazel 9, needs macOS or a tool the images lack) gets
`known-failing build` (both targets) or `known-failing test` (`:test` only)
with the first error as the reason: those targets are tagged `manual`, so
`//...` skips them, but `tools/bb.sh test //<module>:test` still runs them. Prefer exclusions when
only a few targets fail. A project that needs a different
inner Bazel gets `bazel <version>` (add the version to
`tools/versions.bzl` first). A project whose resolved dependency is too
old for it as the root module gets `override <module> <version>`: sync
records it in `projects.json` and `tools/sources.bzl` appends a
`single_version_override()` to its MODULE.bazel (e.g. rules_cc before
0.2.25 rejects `includes = ["."]` in the main repo's root package).
If the registry's MODULE.bazel `local_path_override()`s that module (a
monorepo submodule pointing at `..`, outside its archive), sync records
that call's exact lines and `tools/sources.bzl` removes them first; any
other override of it, or one sync can't find literally, is an error. A
project whose rc files set a flag this Bazel rejects, or import a file
outside its archive, gets ``rc-drop <file> `<exact line>` <reason>``:
`tools/sources.bzl` removes that line, which must occur exactly once
(compared whitespace-trimmed), and fails the fetch otherwise.

Only `archive` BCR sources are supported so far; sync skips
`git_repository` ones.
