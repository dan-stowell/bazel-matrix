#!/usr/bin/env bash
# Runner behind the //wild/<project>:build and :test targets.
#
#   run.sh <key> <bazel-version|-> <build|test> [targets/flags...]
#
# Builds/tests a project "as upstream ships it": its pinned source (no museum
# overlays, no injected toolchain) run by bazelisk inside the //wild/image
# container (a pinned, ordinary CI machine). The project's source url+sha256 is
# read straight from //tools/fetch:extension.bzl, so the target needs no
# separate table. Source is fetched + verified on the host, mounted into the
# container, and bazelisk runs the upstream MODULE/BUILD as found.
#
# Env: WILD_IMAGE (default bazel-wild-baseline:latest, built by
# //wild/image:load), WILD_CACHE (default ~/.cache/wild).
set -euo pipefail

# Under `bazel run`, the repo root is $BUILD_WORKSPACE_DIRECTORY; fall back to
# deriving it from this script's location for direct CLI use.
ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EXT="$ROOT/tools/fetch/extension.bzl"
IMAGE="${WILD_IMAGE:-bazel-wild-baseline:latest}"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
SRC_CACHE="$CACHE/src"
mkdir -p "$SRC_CACHE" "$CACHE/home"

key="${1:?usage: run.sh <key> <version|-> <build|test> [targets...]}"
ver="${2:-}"; cmd="${3:-build}"; shift 3 || true
targets=("$@")

# Image present? (built + loaded by `bazel run //wild/image:load`).
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "error: image '$IMAGE' not loaded. Build it first with:" >&2
  echo "    bazel run //wild/image:load" >&2
  exit 1
fi

# Pull url/sha256/filename for "<key>_archive" out of extension.bzl.
read -r url sha filename < <(awk -v key="\"${key}_archive\":" '
  $0 ~ key {f=1}
  f && /"url":/      {u=$0}
  f && /"sha256":/   {s=$0}
  f && /"filename":/ {n=$0}
  f && /},/ {
    gsub(/.*"url": *"|".*/,"",u); gsub(/.*"sha256": *"|".*/,"",s); gsub(/.*"filename": *"|".*/,"",n)
    print u, s, n; exit
  }' "$EXT")
[[ -z "${url:-}" ]] && { echo "no '${key}_archive' in $EXT" >&2; exit 2; }

tarball="$SRC_CACHE/$filename"
if [[ ! -f "$tarball" ]]; then echo ">> fetching $url"; curl -fsSL -o "$tarball" "$url"; fi
echo "$sha  $tarball" | sha256sum -c - >/dev/null

# `|| true` so tar's SIGPIPE (head closes the pipe early) doesn't trip pipefail.
strip="$( { tar -tzf "$tarball" || true; } | head -1)"; strip="${strip%%/*}"
workdir="$SRC_CACHE/$strip"
[[ -d "$workdir" ]] || { echo ">> extracting $strip"; tar -xzf "$tarball" -C "$SRC_CACHE"; }

# Pin the project's known-good Bazel (the version column). "-" leaves bazelisk
# to honor the repo's .bazelversion (or its default).
env_args=()
[[ -n "$ver" && "$ver" != "-" ]] && env_args+=(-e "USE_BAZEL_VERSION=$ver")

echo ">> [$IMAGE] bazelisk $cmd ${targets[*]}   (project=$key, bazel=${ver:--})"
exec docker run --rm \
  -v "$workdir":/work \
  -v "$CACHE/home":/home/wild \
  "${env_args[@]}" \
  "$IMAGE" "$cmd" "${targets[@]}"
