#!/usr/bin/env bash
#
# traffic.sh — loop over every BBT RBE test target and run it, one project at a
# time, against two BuildBuddy endpoints in sequence. The goal is to generate a
# steady stream of test traffic on both instances.
#
# Endpoints (configured via environment, with the API keys the caller sources):
#
#   1. bazel-matrix.buildbuddy.dev  — uses $DEV_BUILDBUDDY_API_KEY as the
#      BUILDBUDDY_API_KEY for the inner bazel runner.
#   2. bazel-matrix.buildbuddy.io   — uses $BUILDBUDDY_API_KEY.
#
# For each endpoint, we query `bazel query` for all BBT RBE test targets, then
# run `bazel test` on them one at a time (sequential — the inner bazel_runner
# already parallelizes with --jobs=32 over RBE).
#
# The loop repeats forever; a full pass over all targets on both endpoints is
# one "round". Logs go to stdout/stderr and are prefixed with the round number
# and endpoint.
#
# Usage:
#   ./tools/traffic/traffic.sh [--rounds N] [--dry-run]
#
# Flags:
#   --rounds N   stop after N full rounds (default: loop forever)
#   --dry-run    print the commands instead of running them
#
# Environment:
#   BUILDBUDDY_API_KEY         key for bazel-matrix.buildbuddy.io
#   DEV_BUILDBUDDY_API_KEY     key for bazel-matrix.buildbuddy.dev
#   BAZEL                      bazel binary (default: bazel)
#   REPO_ROOT                  repo root (default: cwd)
#   BAZEL_RUNNER_REPO_CACHE    shared inner repo cache (default: a temp dir)
#

set -euo pipefail

ROUNDS=""
DRY_RUN=0
BAZEL_BIN="${BAZEL:-bazel}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rounds) ROUNDS="$2"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
REPO_CACHE="${BAZEL_RUNNER_REPO_CACHE:-/tmp/bazel-matrix-traffic-repo-cache}"
mkdir -p "$REPO_CACHE"

# --- Endpoint definitions ---------------------------------------------------
# Each endpoint is: name|results_url|grpc_endpoint|api_key_env
ENDPOINTS=(
  "dev|https://bazel-matrix.buildbuddy.dev/invocation/|grpcs://bazel-matrix.buildbuddy.dev|DEV_BUILDBUDDY_API_KEY"
  "io|https://app.buildbuddy.io/invocation/|grpcs://remote.buildbuddy.io|BUILDBUDDY_API_KEY"
)

log() { echo "[traffic] $*" >&2; }

# Resolve the API key value from the named env var, failing loudly.
resolve_key() {
  local env_name="$1"
  local val
  val="${!env_name:-}"
  if [[ -z "$val" ]]; then
    log "ERROR: \$$env_name is not set; cannot run against this endpoint."
    return 1
  fi
  printf '%s' "$val"
}

# Run a single bazel test target against a given endpoint config.
# Args: round endpoint_name results_url grpc_endpoint api_key target
run_target() {
  local round="$1" name="$2" results_url="$3" grpc="$4" api_key="$5" target="$6"
  local prefix="[round ${round} ${name}]"

  local cmd=(
    "$BAZEL_BIN"
    --ignore_all_rc_files
    test
    --enable_bzlmod
    --noenable_workspace
    --jobs=1
    --sandbox_writable_path="$REPO_CACHE"
    --test_env=BAZEL_RUNNER_REPO_CACHE="$REPO_CACHE"
    --test_env=BUILDBUDDY_API_KEY="$api_key"
    --test_env=BUILDBUDDY_BES_RESULTS_URL="$results_url"
    --test_env=BUILDBUDDY_GRPC_ENDPOINT="$grpc"
    --build_metadata=USER=bazel-matrix-traffic
    --build_metadata=VISIBILITY=PUBLIC
    "$target"
  )

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "${prefix} DRY-RUN: ${cmd[*]}"
    return 0
  fi

  log "${prefix} target: $target"
  if ! "${cmd[@]}"; then
    log "${prefix} FAILED: $target (continuing)"
    return 1
  fi
  log "${prefix} PASSED: $target"
  return 0
}

# Query the list of BBT RBE test targets once; the set is stable per checkout.
query_targets() {
  "$BAZEL_BIN" --ignore_all_rc_files query 'tests(//:all_bbt_rbe_tests)' \
    --output=label --keep_going 2>/dev/null | sort
}

# --- Main loop --------------------------------------------------------------

log "repo root: $REPO_ROOT"
log "repo cache: $REPO_CACHE"
log "bazel: $BAZEL_BIN"
log "querying BBT RBE test targets..."

cd "$REPO_ROOT"
TARGETS_FILE="$(mktemp)"
if ! query_targets > "$TARGETS_FILE"; then
  log "ERROR: bazel query failed."
  rm -f "$TARGETS_FILE"
  exit 1
fi
TARGET_COUNT="$(wc -l < "$TARGETS_FILE")"
log "found ${TARGET_COUNT} BBT RBE test targets."
if [[ "$TARGET_COUNT" -eq 0 ]]; then
  log "ERROR: no targets found."
  rm -f "$TARGETS_FILE"
  exit 1
fi

round=0
while true; do
  round=$((round + 1))
  if [[ -n "$ROUNDS" && "$round" -gt "$ROUNDS" ]]; then
    log "reached --rounds ${ROUNDS}; stopping."
    break
  fi

  for ep_line in "${ENDPOINTS[@]}"; do
    IFS='|' read -r ep_name results_url grpc key_env <<< "$ep_line"
    log "=== round ${round} → endpoint '${ep_name}' (${grpc}) ==="

    api_key="$(resolve_key "$key_env")" || continue

    i=0
    while IFS= read -r target; do
      i=$((i + 1))
      log "round ${round} ${ep_name} [$i/$TARGET_COUNT]"
      run_target "$round" "$ep_name" "$results_url" "$grpc" "$api_key" "$target" \
        || true   # never let a single failure stop the loop
    done < "$TARGETS_FILE"
  done
  log "=== round ${round} complete ==="
done

rm -f "$TARGETS_FILE"
log "done."
