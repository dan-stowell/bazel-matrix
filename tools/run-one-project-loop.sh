#!/usr/bin/env bash
set -euo pipefail

REPO=${BAZEL_MATRIX_REPO:-/home/exedev/bazel-matrix}
LOCK=${BAZEL_MATRIX_LOCK:-/tmp/bazel-matrix-project-loop.lock}
PROMPT=${BAZEL_MATRIX_PROMPT:-$REPO/tools/prompts/add-one-project.md}
MODEL=${CODEX_PROJECT_MODEL:-gpt-5-mini}
TIMEOUT=${CODEX_PROJECT_TIMEOUT:-6h}
CODEX_BIN=${CODEX_BIN:-/home/exedev/.local/bin/codex}

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

if [[ -f "$HOME/.profile" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.profile"
fi

cd "$REPO"

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "$(date -Is) another project loop is already running; exiting"
  exit 0
fi

echo "$(date -Is) starting bazel-matrix project loop"

git pull --ff-only

timeout "$TIMEOUT" "$CODEX_BIN" \
  -m "$MODEL" \
  -s danger-full-access \
  -a never \
  --search \
  exec \
  -C "$REPO" \
  - < "$PROMPT"

echo "$(date -Is) finished bazel-matrix project loop"
