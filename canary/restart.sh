#!/bin/bash
# Restarts the canary server with near-zero downtime: the old process
# releases port 8000 first and finishes its running step in the background,
# and the new one serves at once (its runner waits for the work dir's lock
# and for the old one's Bazel commands to end).
#   canary/restart.sh            # now (interrupts the running step)
#   canary/restart.sh --between  # once the running step has ended
set -u
here=$(cd "$(dirname "$0")" && pwd)
data=$HOME/canary-data
port=8000
if [ "${1:-}" = --between ]; then
  shift
  # Until every step running now has ended (an image's amd64 and arm64
  # batches run at once); a step started meanwhile is seconds old.
  ids=$(python3 -c '
import json, sys
last = {}
for line in open(sys.argv[1]):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    last[r["id"]] = r["status"]
print(" ".join(i for i, s in last.items() if s == "running"))' "$data/runs.jsonl")
  for id in $ids; do
    while grep -F "\"id\": \"$id\"" "$data/runs.jsonl" | tail -1 | grep -q '"status": "running"'; do sleep 2; done
  done
fi
old=$(cat "$data/server.pid" 2>/dev/null)
if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
  kill -TERM "$old"
fi
for _ in $(seq 100); do ss -ltn | grep -q ":$port " || break; sleep 0.1; done
if ss -ltn | grep -q ":$port "; then
  echo "port $port is still bound (old server ${old:-unknown} didn't release it); not starting another" >&2
  exit 1
fi
nohup python3 "$here/server.py" "$@" >>"$data/server.log" 2>&1 &
echo "restarted: old ${old:-none}, new $!"
