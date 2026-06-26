# wild — build it as it is

The implementation behind the top-level [README](../README.md): build & test each
museum project **exactly as upstream ships it** (its pinned source, its own
`MODULE`/`BUILD`, no overlays, no injected toolchain) inside one reproducible
container. The container is the only reproducibility boundary; everything a build
needs beyond bazelisk, the image must supply — which is precisely what we're
enumerating.

## Layout

- **[`image/`](image)** — the "build it as it is" container, assembled entirely
  with Bazel. [rules_img] stacks layers onto a pinned `debian:bookworm-slim`
  base; the host toolchain (gcc/g++, JDK, python, git, curl, zip) rides on top as
  hermetic `.deb` layers resolved by [rules_distroless] from a pinned Debian
  snapshot ([`image/toolchain.yaml`](image/toolchain.yaml)). No `apt install` at
  build time, no Dockerfile.

  ```sh
  bazel run //wild/image:rootfs            # daemonless: stage rootfs + crun into ~/.cache/wild
  bazel run //wild/image:load              # docker: build + load bazel-wild-baseline:latest
  bazel run @toolchain_apt//:lock          # regenerate the apt lock after editing toolchain.yaml
  ```

  The default run path is **daemonless and rootless**: [`rootfs.sh`](image/rootfs.sh)
  extracts the image's filesystem from the OCI layout rules_img builds (no
  daemon) and stages it alongside a pinned static `crun` ([`//tools/crun`](../../tools/crun)).
  No dockerd, no host runtime, no root — just a single-id user namespace.

- **[`//projects/<project>`](../projects)** — one package per project with
  `:build` and `:test` targets (e.g. [`re2`](../projects/re2),
  [`cpu_features`](../projects/cpu_features)). Generated from the museum project
  list by [`gen_targets.py`](gen_targets.py); each target is a thin wrapper over
  [`//projects:run.sh`](../projects/run.sh).

  ```sh
  bazel run //projects/re2:build
  bazel run //projects/re2:test
  ```

- **[`//projects:run.sh`](../projects/run.sh)** — the shared runner. Reads a
  project's pinned `url+sha256` straight from [`//tools/fetch`](../tools/fetch),
  fetches + verifies
  the source on the host, mounts it into the image, and runs `bazelisk` against
  the upstream `MODULE`/`BUILD` with the project's known-good Bazel pinned
  (`USE_BAZEL_VERSION`). Each project gets its own Bazel output base; a shared
  content-addressed `--repository_cache` keeps the BCR + toolchain downloads warm
  across projects. `WILD_RUNTIME` selects `crun` (default, rootless OCI bundle
  over the staged rootfs) or `docker`.

- **[`verify.sh`](verify.sh)** — the build+test sweep. Runs every project's
  upstream build, then (if green) its upstream test, and records the result to
  `verify-results.tsv`. [`_readme_table.py`](_readme_table.py) renders that into
  the README table — a test command is only listed if it genuinely passes here.

  ```sh
  bash wild/verify.sh                       # the whole matrix (resumable)
  WILD_ONLY="re2 snappy" bash wild/verify.sh # just these
  python3 wild/_readme_table.py --notes      # regenerate the README table
  ```

## The two walls

Two things stand between a project's green BUILD and a clean-machine build:

1. **Bazel-version drift.** A repo that pins no `.bazelversion` gets whatever
   bazelisk thinks is latest (Bazel 9), which removed the autoloaded
   `cc_*`/`sh_test` built-ins — so `load`-less BUILD files fail at *load* time.
   `run.sh` sidesteps this by pinning each project's known-good Bazel.

2. **The host toolchain.** Past the drift, *everything that compiles* needs
   Bazel's C/C++ toolchain auto-configuration to find a host `gcc`/`cc` — even
   pure-Go (buildifier) and Rust (`cxx`) projects, via `rules_go`/`rules_rust`.
   With **bazelisk alone**, nothing builds; the [`image`](image) supplies exactly
   the host tools these projects reach for (see the table in the top-level
   README).

[rules_img]: https://github.com/bazel-contrib/rules_img
[rules_distroless]: https://github.com/bazel-contrib/rules_distroless
