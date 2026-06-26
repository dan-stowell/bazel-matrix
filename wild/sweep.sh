#!/usr/bin/env bash
# Sweep every museum project through the wild containers and record a matrix.
# For each project we build the museum's curated target under three configs:
#   A  as-is        baseline image, default bazelisk (whatever it picks)
#   B  +right-bazel baseline image, the project's known-good Bazel version
#   C  hermetic     STRICT image (nothing but bazelisk), known-good Bazel
#                   — only attempted when B builds (no point if it needs a host)
# Resumable (skips projects already in the TSV) and self-committing: after each
# project it regenerates wild/CATALOG.md and commits+pushes.
set -uo pipefail   # not -e: we expect builds to fail and must continue

cd "$(dirname "${BASH_SOURCE[0]}")/.."
TSV="wild/sweep-results.tsv"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
LOGS="$CACHE/sweeplogs"; mkdir -p "$LOGS"
TIMEOUT="${WILD_TIMEOUT:-900}"
DEFAULT_BAZEL="9.1.1"
[[ -f "$TSV" ]] || printf 'key\tversion\tas_is\tright_bazel\thermetic\tnote\n' > "$TSV"

classify() {  # <logfile> <rc>
  local f="$1" rc="$2"
  [[ "$rc" == 124 ]] && { echo timeout; return; }
  grep -q "Build completed successfully" "$f" && { echo ok; return; }
  grep -qE "is not defined|contains errors|not declared in package" "$f" && { echo drift; return; }
  grep -qE "Cannot find gcc|Auto-Configuration Error" "$f" && { echo no-host-cc; return; }
  grep -q "resolves to the workspace root" "$f" && { echo includes-dot; return; }
  grep -qE "No repository visible as '@|no such package '@" "$f" && { echo dep-shape; return; }
  echo fail
}

run_cfg() {  # <image> <version|-> <key> <cfg> <logfile> -- <targets...>
  local image="$1" ver="$2" key="$3" cfg="$4" log="$5"; shift 5; [[ "$1" == "--" ]] && shift
  (   # export in a subshell so a variable-expanded "VAR=val" isn't run as a command.
      # Distinct output base per config so the strict (C) build recompiles from
      # scratch instead of reusing the baseline (B) build's cached outputs.
    export WILD_IMAGE="$image"
    [[ "$ver" != "-" ]] && export USE_BAZEL_VERSION="$ver"
    timeout "$TIMEOUT" wild/build.sh "$key" --output_user_root=/home/wild/ob/"$key-$cfg" build "$@"
  ) >"$log" 2>&1
  local rc=$?
  classify "$log" "$rc"
}

clean_ob() {  # drop a project's output bases (root-owned, so via a container)
  docker run --rm --entrypoint sh -v "$CACHE/home":/home/wild bazel-wild-baseline \
    -c "rm -rf /home/wild/ob/$1-*" >/dev/null 2>&1 || true
}

regen() { python3 wild/_catalog.py "$TSV" > wild/CATALOG.md; }

while IFS=$'\t' read -r key ver targets; do
  grep -q "^${key}	" "$TSV" && { echo "skip $key (done)"; continue; }
  echo "==== $key (declared bazel $ver; targets: $targets) ===="
  read -ra T <<<"$targets"

  A=$(run_cfg bazel-wild-baseline - "$key" A "$LOGS/$key.A.log" -- "${T[@]}")
  echo "  A as-is        : $A"

  if [[ "$ver" == "$DEFAULT_BAZEL" ]]; then
    B="$A"; cp "$LOGS/$key.A.log" "$LOGS/$key.B.log"
  else
    B=$(run_cfg bazel-wild-baseline "$ver" "$key" B "$LOGS/$key.B.log" -- "${T[@]}")
  fi
  echo "  B +right-bazel : $B"

  if [[ "$B" == "ok" ]]; then
    C=$(run_cfg bazel-wild "$ver" "$key" C "$LOGS/$key.C.log" -- "${T[@]}")
  else
    C="-"
  fi
  echo "  C hermetic     : $C"

  note=$(grep -m1 -E "ERROR:|Auto-Configuration Error" "$LOGS/$key.B.log" \
           | sed -E 's#/work/##; s/^ERROR: //; s/\t/ /g' | cut -c1-90)
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$key" "$ver" "$A" "$B" "$C" "${note:-}" >> "$TSV"

  clean_ob "$key"
  regen
  git add "$TSV" wild/CATALOG.md
  git commit -q -m "wild sweep: $key (as-is=$A, right-bazel=$B, hermetic=$C)" || true
  git push -q origin linux || true
done < <(python3 wild/_projects.py)

echo "== sweep complete =="
column -t -s$'\t' "$TSV"
