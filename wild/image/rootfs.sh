#!/usr/bin/env bash
# Materialise the daemonless run path from Bazel — no docker, no host runtime.
#
#   bash wild/image/rootfs.sh        # or: bazel run //wild/image:rootfs
#
# Produces, under $WILD_CACHE (default ~/.cache/wild):
#   rootfs/   the //wild/image filesystem, extracted from the OCI layout that
#             rules_img builds *without a daemon* (bazel --output_groups=oci_layout).
#   crun      the pinned static OCI runtime (//tools/crun), copied out of Bazel's
#             cache so projects/run.sh can exec it.
#
# After this, `bazel run //wild/<project>:build` runs rootless via crun. Re-run
# this whenever the image changes (idempotent: keyed on the manifest digest).
set -euo pipefail

ROOT="${BUILD_WORKSPACE_DIRECTORY:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
ROOTFS="$CACHE/rootfs"
case "$(uname -m)" in
  x86_64) ARCH=amd64 ;; aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac
mkdir -p "$CACHE"
cd "$ROOT"

echo ">> building image OCI layout + crun (daemonless)…"
bazel build //wild/image:image --output_groups=oci_layout "@crun_linux_${ARCH}//file" >/dev/null 2>&1

# Stage the pinned crun next to the rootfs so run.sh can exec it without Bazel.
ob="$(bazel info output_base 2>/dev/null)"
crun_rel="$(bazel cquery --output=files "@crun_linux_${ARCH}//file" 2>/dev/null | head -1)"
install -m 0755 "$ob/$crun_rel" "$CACHE/crun"
echo ">> staged crun -> $CACHE/crun ($("$CACHE/crun" --version | head -1))"

layout="$ROOT/bazel-bin/wild/image/image_oci_layout"
[[ -d "$layout" ]] || { echo "OCI layout not found at $layout" >&2; exit 1; }
mani=$(python3 -c "import json;print(json.load(open('$layout/index.json'))['manifests'][0]['digest'].split(':')[1])")
digest_file="$ROOTFS/.manifest-digest"
if [[ -f "$digest_file" && "$(cat "$digest_file")" == "$mani" ]]; then
  echo ">> rootfs up-to-date ($ROOTFS, manifest $mani)"; exit 0
fi

# Ordered list of "<blob-hex> gz|raw" for the manifest's layers.
mapfile -t layers < <(python3 - "$layout" "$mani" <<'PY'
import json, sys
layout, mani = sys.argv[1], sys.argv[2]
m = json.load(open(f"{layout}/blobs/sha256/{mani}"))
for l in m["layers"]:
    print(l["digest"].split(":")[1], "gz" if l["mediaType"].endswith("gzip") else "raw")
PY
)

echo ">> extracting ${#layers[@]} layers into $ROOTFS …"
rm -rf "$ROOTFS"; mkdir -p "$ROOTFS"

# Extract each layer in order, reproducing what docker's overlayfs produces.
#
# The base (debian-slim) is merged-/usr: /bin,/lib,/lib64,/sbin are symlinks to
# /usr/*. The rules_distroless apt layer is NOT merged: it ships real /bin and
# real /lib/.../libc.so.6. Under overlayfs the apt dirs simply shadow the base
# symlinks, so /lib ends up a real dir *containing* libc. Plain `tar` instead
# writes libc *through* the live symlink into /usr/lib and then blanks /lib —
# breaking the loader. So after the base layer we drop those four merge symlinks;
# the apt layer's real dirs then materialise correctly (and the fixups layer's
# /bin/sh,/bin/bash land in a real /bin, as in the image).
extract() {  # <blob> <gz>
  local blob="$1" z=""; [[ "$2" == gz ]] && z="z"
  tar --overwrite -p${z}xf "$blob" -C "$ROOTFS" \
      --warning=no-unknown-keyword --no-same-owner 2>/dev/null || true
}

first=1
for entry in "${layers[@]}"; do
  read -r hex gz <<<"$entry"
  extract "$layout/blobs/sha256/$hex" "$gz"
  if [[ "$first" == 1 ]]; then  # just applied the base: un-merge /usr
    for d in bin lib lib64 sbin; do
      [[ -L "$ROOTFS/$d" ]] && rm -f "$ROOTFS/$d"
    done
    first=0
  fi
done

echo "$mani" > "$digest_file"
echo ">> done: $ROOTFS  ($(du -sh "$ROOTFS" | cut -f1), manifest $mani)"
