#!/usr/bin/env bash
# Build a museum project "as it is" — its pinned source, its own build files,
# inside a wild container (no museum overlays, no injected toolchain).
#
#   wild/build.sh <project> [bazel-args...]
#
# The project's pinned source (url + sha256) is read straight from the museum's
# //tools/fetch:extension.bzl, so every museum project is buildable here without a
# separate table. Source is fetched + verified on the host, mounted into the
# container, and `bazelisk` is run against the upstream MODULE/BUILD as found.
#
# Image (the reproducibility boundary):
#   WILD_IMAGE=bazel-wild-baseline  (default) — bazelisk + a normal CI machine
#                                     (C/C++ toolchain, JDK, python, git, zip).
#   WILD_IMAGE=bazel-wild           — strict: nothing but bazelisk (the
#                                     "is it hermetic in nature?" probe).
# USE_BAZEL_VERSION=<v> forces a Bazel version (else bazelisk honors the repo's
# .bazelversion, or the latest if it pins none).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$ROOT/tools/fetch/extension.bzl"
IMAGE="${WILD_IMAGE:-bazel-wild-baseline}"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
SRC_CACHE="$CACHE/src"
mkdir -p "$SRC_CACHE" "$CACHE/home"          # pre-create so docker -v doesn't (as root)

proj="${1:-}"; shift || true
[[ -z "$proj" ]] && { echo "usage: wild/build.sh <project> [bazel-args...]" >&2; exit 2; }

# Pull url/sha256/filename for "<proj>_archive" out of extension.bzl.
read -r url sha filename < <(awk -v key="\"${proj}_archive\":" '
  $0 ~ key {f=1}
  f && /"url":/      {u=$0}
  f && /"sha256":/   {s=$0}
  f && /"filename":/ {n=$0}
  f && /},/ {
    gsub(/.*"url": *"|".*/,"",u); gsub(/.*"sha256": *"|".*/,"",s); gsub(/.*"filename": *"|".*/,"",n)
    print u, s, n; exit
  }' "$EXT")
[[ -z "${url:-}" ]] && { echo "no '${proj}_archive' in $EXT" >&2; exit 2; }

tarball="$SRC_CACHE/$filename"
if [[ ! -f "$tarball" ]]; then echo ">> fetching $url"; curl -fsSL -o "$tarball" "$url"; fi
echo "$sha  $tarball" | sha256sum -c - >/dev/null

# `|| true` so tar's SIGPIPE (head closes the pipe early) doesn't trip pipefail.
strip="$( { tar -tzf "$tarball" || true; } | head -1)"; strip="${strip%%/*}"
workdir="$SRC_CACHE/$strip"
[[ -d "$workdir" ]] || { echo ">> extracting $strip"; tar -xzf "$tarball" -C "$SRC_CACHE"; }

args=("$@"); [[ ${#args[@]} -eq 0 ]] && args=(build //...)   # "as it is": build everything

echo ">> [$IMAGE] bazelisk ${args[*]}   (project=$proj${USE_BAZEL_VERSION:+, bazel=$USE_BAZEL_VERSION})"
exec docker run --rm \
  -v "$workdir":/work \
  -v "$CACHE/home":/home/wild \
  ${USE_BAZEL_VERSION:+-e USE_BAZEL_VERSION="$USE_BAZEL_VERSION"} \
  "$IMAGE" "${args[@]}"
