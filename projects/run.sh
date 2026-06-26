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
# Runtime (WILD_RUNTIME):
#   crun   (default) daemonless + rootless via the pinned //tools/crun in an
#          OCI bundle over the rootfs staged by `bash wild/image/rootfs.sh`. No
#          dockerd, no host runtime.
#   docker the image loaded by `bazel run //wild/image:load` (needs a daemon).
# Env: WILD_CACHE (default ~/.cache/wild), WILD_IMAGE (docker tag).
set -euo pipefail

# Under `bazel run`, the repo root is $BUILD_WORKSPACE_DIRECTORY; fall back to
# deriving it from this script's location for direct CLI use.
ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
EXT="$ROOT/tools/fetch/extension.bzl"
RUNTIME="${WILD_RUNTIME:-crun}"
IMAGE="${WILD_IMAGE:-bazel-wild-baseline:latest}"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
SRC_CACHE="$CACHE/src"
ROOTFS="$CACHE/rootfs"
CRUN="$CACHE/crun"
mkdir -p "$SRC_CACHE" "$CACHE/home"

key="${1:?usage: run.sh <key> <version|-> <build|test> [targets...]}"
ver="${2:-}"; cmd="${3:-build}"; shift 3 || true
targets=("$@")

# Runtime present?
if [[ "$RUNTIME" == crun ]]; then
  if [[ ! -x "$CRUN" || ! -d "$ROOTFS" ]]; then
    echo "error: daemonless runtime not staged. Build it first with:" >&2
    echo "    bash wild/image/rootfs.sh   # (or: bazel run //wild/image:rootfs)" >&2
    exit 1
  fi
elif [[ "$RUNTIME" == docker ]]; then
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "error: image '$IMAGE' not loaded. Build it first with:" >&2
    echo "    bazel run //wild/image:load" >&2
    exit 1
  fi
else
  echo "error: unknown WILD_RUNTIME='$RUNTIME' (use crun or docker)" >&2; exit 2
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

# Every project mounts its source at /work, so give each its own Bazel output
# base (keyed by project) — otherwise they'd collide in one shared base and
# re-fetch each other's deps. Lives under the mounted $HOME so reruns stay warm.
startup=("--output_user_root=/home/wild/ob/$key")

# Extra bazel flags (e.g. --verbose_failures) go before the `--` marker; the
# targets go after it so negative patterns like `-//:exhaustive_test` parse as
# target patterns rather than options. A shared, content-addressed repository
# cache (under the mounted $HOME) means the BCR + toolchains download once
# across all projects rather than once per project's output base.
flags=("--repository_cache=/home/wild/repocache")
if [[ -n "${WILD_BAZEL_FLAGS:-}" ]]; then
  read -ra _extra <<<"$WILD_BAZEL_FLAGS"; flags+=("${_extra[@]}")
fi

echo ">> [$RUNTIME] bazelisk $cmd ${targets[*]}   (project=$key, bazel=${ver:--})"

# The full bazelisk argv, identical for both runtimes.
bazelisk=(/usr/local/bin/bazelisk "${startup[@]}" "$cmd" "${flags[@]}" -- "${targets[@]}")

if [[ "$RUNTIME" == docker ]]; then
  exec docker run --rm \
    -v "$workdir":/work \
    -v "$CACHE/home":/home/wild \
    "${env_args[@]}" \
    "$IMAGE" "${startup[@]}" "$cmd" "${flags[@]}" -- "${targets[@]}"
fi

# --- crun: a rootless OCI bundle over the staged rootfs, no daemon -------------
bundle="$(mktemp -d "$CACHE/bundle.XXXXXX")"
trap 'rm -rf "$bundle"' EXIT
"$CRUN" spec --rootless --bundle "$bundle" >/dev/null

ENV_JSON="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
HOME=/home/wild
JAVA_HOME=/usr/lib/jvm/default-java
SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt"
[[ -n "$ver" && "$ver" != "-" ]] && ENV_JSON+=$'\n'"USE_BAZEL_VERSION=$ver"

ROOTFS="$ROOTFS" WORKDIR="$workdir" HOMEDIR="$CACHE/home" ENVS="$ENV_JSON" \
python3 - "$bundle/config.json" "${bazelisk[@]}" <<'PY'
import json, os, sys
cfg, args = sys.argv[1], sys.argv[2:]
c = json.load(open(cfg))
c["root"] = {"path": os.environ["ROOTFS"], "readonly": True}
c["process"]["args"] = args
c["process"]["cwd"] = "/work"
c["process"]["terminal"] = False
c["process"]["env"] = [l for l in os.environ["ENVS"].splitlines() if l]
# Share the host network (so downloads resolve) — drop the network namespace.
c["linux"]["namespaces"] = [n for n in c["linux"]["namespaces"] if n["type"] != "network"]
c["linux"]["resources"] = {}  # rootless, no cgroup limits
c["mounts"] += [
    {"destination": "/work", "type": "bind", "source": os.environ["WORKDIR"], "options": ["rbind", "rw"]},
    {"destination": "/home/wild", "type": "bind", "source": os.environ["HOMEDIR"], "options": ["rbind", "rw"]},
    {"destination": "/etc/resolv.conf", "type": "bind", "source": "/etc/resolv.conf", "options": ["rbind", "ro"]},
]
json.dump(c, open(cfg, "w"), indent=2)
PY

exec "$CRUN" --cgroup-manager=disabled run -b "$bundle" "wild-$key-$$"
