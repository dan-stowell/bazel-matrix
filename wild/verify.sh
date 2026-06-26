#!/usr/bin/env bash
# Verify every museum project "as it is" inside //wild/image: run its upstream
# BUILD target, then (if the build is green) its upstream TEST target, and
# record the result. This is the source of truth for the README's "projects
# that work" table — a test command is only listed if it genuinely passes here.
#
# Resumable: skips projects already in the results TSV. Per-project, per-goal
# Bazel output bases (run.sh) keep reruns warm.
#
#   bazel run //wild/image:load     # once
#   bash wild/verify.sh             # the whole matrix
#   WILD_ONLY="re2 snappy" bash wild/verify.sh   # just these
set -uo pipefail   # not -e: builds/tests are expected to fail and must continue

cd "$(dirname "${BASH_SOURCE[0]}")/.."
TSV="wild/verify-results.tsv"
CACHE="${WILD_CACHE:-$HOME/.cache/wild}"
LOGS="$CACHE/verifylogs"; mkdir -p "$LOGS"
BUILD_TIMEOUT="${WILD_BUILD_TIMEOUT:-1500}"
TEST_TIMEOUT="${WILD_TEST_TIMEOUT:-1500}"
ONLY="${WILD_ONLY:-}"
[[ -f "$TSV" ]] || printf 'proj\tkey\tversion\tbuild\ttest\ttest_summary\n' > "$TSV"

classify_build() {  # <logfile> <rc>
  local f="$1" rc="$2"
  [[ "$rc" == 124 ]] && { echo timeout; return; }
  grep -q "Build completed successfully" "$f" && { echo ok; return; }
  grep -qE "is not defined|not declared in package|cannot load" "$f" && { echo drift; return; }
  grep -qE "Cannot find gcc|Auto-Configuration Error" "$f" && { echo no-host-cc; return; }
  grep -q "resolves to the workspace root" "$f" && { echo includes-dot; return; }
  grep -qE "No repository visible as '@|no such package '@" "$f" && { echo dep-shape; return; }
  echo fail
}

# Pull "Executed N out of M tests: ..." (or build failure) from a test log.
test_summary() {  # <logfile>
  grep -m1 -E "Executed [0-9]+ out of [0-9]+ tests" "$1" \
    || grep -m1 -E "tests? pass" "$1" \
    || echo ""
}

classify_test() {  # <logfile> <rc>
  local f="$1" rc="$2"
  [[ "$rc" == 124 ]] && { echo timeout; return; }
  # bazel test rc: 0 all pass, 3 some tests fail, 4 no tests found.
  if grep -qE "Executed [0-9]+ out of [0-9]+ tests: .*(all tests pass|tests pass)\." "$f"; then echo ok; return; fi
  grep -qE "were skipped|out of .* tests:.*pass" "$f" && { echo ok; return; }
  [[ "$rc" == 0 ]] && { echo ok; return; }
  grep -qE "Cannot find gcc|Auto-Configuration Error" "$f" && { echo no-host-cc; return; }
  grep -qE "is not defined|not declared in package" "$f" && { echo drift; return; }
  echo fail
}

while IFS=$'\t' read -r proj key version build test; do
  [[ -n "$ONLY" && " $ONLY " != *" $proj "* ]] && continue
  grep -q "^${proj}	" "$TSV" && { echo "skip $proj (done)"; continue; }
  echo "==== $proj (key=$key bazel=$version) ===="

  bstat="n/a"
  if [[ -n "$build" ]]; then
    read -ra BT <<<"$build"
    timeout "$BUILD_TIMEOUT" wild/run.sh "$key" "$version" build "${BT[@]}" \
      >"$LOGS/$proj.build.log" 2>&1
    bstat=$(classify_build "$LOGS/$proj.build.log" $?)
  fi
  echo "  build: $bstat"

  tstat="none"; tsum=""
  if [[ -n "$test" ]]; then
    if [[ "$build" && "$bstat" != "ok" ]]; then
      tstat="skip-build"
    else
      read -ra TT <<<"$test"
      timeout "$TEST_TIMEOUT" wild/run.sh "$key" "$version" test "${TT[@]}" \
        >"$LOGS/$proj.test.log" 2>&1
      rc=$?
      tstat=$(classify_test "$LOGS/$proj.test.log" $rc)
      tsum=$(test_summary "$LOGS/$proj.test.log" | sed -E 's/\t/ /g; s/INFO: //' | cut -c1-80)
    fi
  fi
  echo "  test:  $tstat   $tsum"

  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$proj" "$key" "$version" "$bstat" "$tstat" "$tsum" >> "$TSV"
done < <(python3 wild/_sweep_projects.py)

echo "== verify complete =="
column -t -s$'\t' "$TSV"
