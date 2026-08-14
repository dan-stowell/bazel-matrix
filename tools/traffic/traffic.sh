#!/usr/bin/env bash
#
# traffic.sh — loop over every BBT RBE test target and run it, one project at a
# time, against bazel-matrix.buildbuddy.dev. The goal is to generate a steady
# stream of real RBE action traffic on the BuildBuddy dev instance.
#
# To maximize the number of actual remote executions (not cache hits):
#   • --nocache_test_results      force re-running every test action
#   • --noremote_accept_cached    force re-executing every remote action
#   • fresh --remote_instance_name per test  prevents cross-test cache hits
#
# Endpoint (configured via environment, with the API key the caller sources):
#
#   bazel-matrix.buildbuddy.dev  — uses $DEV_BUILDBUDDY_API_KEY as the
#      BUILDBUDDY_API_KEY for the inner bazel runner.
#
# We query `bazel query` for all BBT RBE test targets, then run `bazel test`
# on them one at a time (sequential — the inner bazel_runner already
# parallelizes with --jobs=32 over RBE). Every run is recorded in a SQLite
# store (db.py) with start/finish time, status, and the BuildBuddy invocation
# URL.
#
# The loop repeats forever; a full pass over all targets is one "round".
# Logs go to stdout/stderr and are prefixed with the round number.
#
# Usage:
#   ./tools/traffic/traffic.sh [--rounds N] [--dry-run]
#
# Flags:
#   --rounds N   stop after N full rounds (default: loop forever)
#   --dry-run    print the commands instead of running them
#
# Environment:
#   DEV_BUILDBUDDY_API_KEY     key for bazel-matrix.buildbuddy.dev
#   BAZEL                      bazel binary (default: bazel)
#   REPO_ROOT                  repo root (default: cwd)
#   BAZEL_RUNNER_REPO_CACHE    shared inner repo cache (default: a temp dir)
#   TRAFFIC_DB                 SQLite path (default: tools/traffic/traffic.sqlite)
#

set -euo pipefail

ROUNDS=""
DRY_RUN=0
BAZEL_BIN="${BAZEL:-bazel}"
# Per-test wall-clock timeout in seconds. The inner bazel_runner's py_test has
# timeout="eternal", so without this a stuck inner bazel (hung RBE connection,
# deadlocked sandbox, etc.) blocks the loop forever. --test_timeout overrides
# the rule's eternal timeout, and the `timeout` wrapper is a belt-and-suspenders
# kill in case Bazel itself is the one that's stuck.
PER_TEST_TIMEOUT="${PER_TEST_TIMEOUT:-600}"

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB="${TRAFFIC_DB:-$SCRIPT_DIR/db.py}"

# Ensure the SQLite schema exists, then mark any runs left "running" by a
# previous (killed) process as interrupted.
python3 "$DB" init >/dev/null
python3 "$DB" cleanup-orphans >/dev/null 2>&1 || true

# --- Endpoint definitions ---------------------------------------------------
# Each endpoint is: name|results_url|grpc_endpoint|api_key_env
# Only buildbuddy.dev — the io endpoint is intentionally omitted.
ENDPOINTS=(
  "dev|https://bazel-matrix.buildbuddy.dev/invocation/|grpcs://bazel-matrix.buildbuddy.dev|DEV_BUILDBUDDY_API_KEY"
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
# Writes bazel output to a temp log, captures the invocation URL, records
# start/finish in the SQLite store, and prints the run id on stdout.
run_target() {
  local round="$1" name="$2" results_url="$3" grpc="$4" api_key="$5" target="$6"
  local prefix="[round ${round} ${name}]"

  local project
  project="${target#//projects/}"      # cctz/bbt:cctz_rbe_test
  project="${project%%/*}"              # cctz

  # Record start in the DB; capture the run id.
  local run_id
  run_id="$(python3 "$DB" start \
    --round "$round" --endpoint "$name" \
    --endpoint-url "$results_url" \
    --target "$target" --project "$project")"

  # The inner bazel_runner's py_test uses env_inherit to pick up
  # BUILDBUDDY_API_KEY / BUILDBUDDY_BES_RESULTS_URL / BUILDBUDDY_GRPC_ENDPOINT
  # from the *outer* bazel client's environment. --test_env does NOT override
  # env_inherit, so we must export these vars in the shell before invoking bazel.
  # Save and restore the originals so each endpoint gets its own key.
  local _saved_key="${BUILDBUDDY_API_KEY:-}"
  local _saved_url="${BUILDBUDDY_BES_RESULTS_URL:-}"
  local _saved_grpc="${BUILDBUDDY_GRPC_ENDPOINT:-}"
  export BUILDBUDDY_API_KEY="$api_key"
  export BUILDBUDDY_BES_RESULTS_URL="$results_url"
  export BUILDBUDDY_GRPC_ENDPOINT="$grpc"

  # Flags injected into the *inner* bazel_runner via --test_arg=--flag=...
  # These force real RBE action execution instead of cache hits:
  #   --nocache_test_results     re-run every test action (not just build)
  #   --noremote_accept_cached   re-execute every remote action (build + test)
  #   --remote_instance_name     fresh per test so the remote cache key is
  #                              unique — prevents cross-test cache hits on
  #                              BuildBuddy's shared remote cache.
  local instance_name="traffic-r${round}-${run_id}-$(date +%s)-$RANDOM"
  local inner_flags=(
    --test_arg=--flag=--nocache_test_results
    --test_arg=--flag=--noremote_accept_cached
    "--test_arg=--flag=--remote_instance_name=${instance_name}"
  )

  local cmd=(
    "$BAZEL_BIN"
    --ignore_all_rc_files
    test
    --enable_bzlmod
    --noenable_workspace
    --jobs=1
    --sandbox_writable_path="$REPO_CACHE"
    --test_env=BAZEL_RUNNER_REPO_CACHE="$REPO_CACHE"
    --test_timeout="$PER_TEST_TIMEOUT"
    "${inner_flags[@]}"
    --build_metadata=USER=bazel-matrix-traffic
    --build_metadata=VISIBILITY=PUBLIC
    "$target"
  )

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "${prefix} DRY-RUN (run #${run_id}): ${cmd[*]}"
    python3 "$DB" finish --id "$run_id" --status skipped
    return 0
  fi

  log "${prefix} run #${run_id} target: $target"

  # Run bazel under `timeout` so a stuck invocation is killed even if
  # Bazel itself ignores --test_timeout (e.g. the bazel server hangs during
  # analysis). Give a small grace margin beyond --test_timeout so Bazel's own
  # timeout fires first and produces a proper test result.
  local out_log
  out_log="$(mktemp)"
  local rc=0
  local wall=$((PER_TEST_TIMEOUT + 60))
  timeout --kill-after=10s "${wall}s" "${cmd[@]}" 2>&1 | tee "$out_log" || rc=${PIPESTATUS[0]}
  # timeout returns 124 when the time limit is reached, 137 when SIGKILL is sent.
  if [[ "$rc" -eq 124 || "$rc" -eq 137 ]]; then
    log "${prefix} TIMEOUT run #${run_id}: $target (killed after ${wall}s)"
  fi

  # Scrape the inner invocation URL. The inner bazel prints (in the test.log,
  # not outer stdout):
  #   INFO: Streaming build results to: https://.../invocation/<uuid>
  # Fall back to the outer bazel's own line in the tee'd output.
  local invocation=""
  invocation="$(grep -m1 'Streaming build results to:' "$out_log" \
    | sed -n 's/.*Streaming build results to: //p' || true)"
  if [[ -z "$invocation" && -n "$TESTLOGS_ROOT" ]]; then
    # test.log path: <testlogs>/<package-path>/<target-name>/test.log
    local pkg_path="${target#//}"            # projects/cctz/bbt:cctz_rbe_test
    local tname="${pkg_path##*:}"            # cctz_rbe_test
    local ppath="${pkg_path%:*}"             # projects/cctz/bbt
    local tlog="$TESTLOGS_ROOT/$ppath/$tname/test.log"
    if [[ -f "$tlog" ]]; then
      invocation="$(grep -m1 'Streaming build results to:' "$tlog" \
        | sed -n 's/.*Streaming build results to: //p' || true)"
    fi
  fi
  rm -f "$out_log"

  # Restore the outer environment so the next endpoint iteration starts clean.
  export BUILDBUDDY_API_KEY="$_saved_key"
  export BUILDBUDDY_BES_RESULTS_URL="$_saved_url"
  export BUILDBUDDY_GRPC_ENDPOINT="$_saved_grpc"

  local status
  if [[ "$rc" -eq 0 ]]; then
    status="passed"
  elif [[ "$rc" -eq 124 || "$rc" -eq 137 ]]; then
    status="timed_out"
  else
    status="failed"
  fi

  python3 "$DB" finish --id "$run_id" --status "$status" \
    --exit-code "$rc" ${invocation:+--invocation "$invocation"}

  if [[ "$rc" -ne 0 ]]; then
    log "${prefix} FAILED run #${run_id}: $target (rc=$rc, continuing)"
  else
    log "${prefix} PASSED run #${run_id}: $target"
  fi
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
log "DB: $DB"
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

# Resolve the outer bazel testlogs root once, for scraping inner invocation URLs.
TESTLOGS_ROOT="$("$BAZEL_BIN" --ignore_all_rc_files info bazel-testlogs 2>/dev/null || true)"
log "testlogs root: ${TESTLOGS_ROOT:-<unknown>}"

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
