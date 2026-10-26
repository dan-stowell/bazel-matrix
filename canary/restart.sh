#!/bin/bash
# Restarts the canary server with near-zero downtime: the old process
# releases port 8000 first and finishes its running step in the background,
# and the new one serves at once (its runner waits for the work dir's lock).
#   canary/restart.sh            # now (interrupts the running step)
#   canary/restart.sh --between  # once the running step has ended
set -u
here=$(cd "$(dirname "$0")" && pwd)
data=$HOME/canary-data
if [ "${1:-}" = --between ]; then
  shift
  id=$(tail -1 "$data/runs.jsonl" | python3 -c 'import json,sys; r=json.loads(sys.stdin.read()); print(r["id"] if r["status"]=="running" else "")')
  while [ -n "$id" ] && grep -F "\"id\": \"$id\"" "$data/runs.jsonl" | tail -1 | grep -q '"status": "running"'; do sleep 2; done
fi
old=$(pgrep -f "^python3 $here/server.py")
[ -n "$old" ] && kill -TERM $old
for _ in $(seq 100); do ss -ltn | grep -q ':8000 ' || break; sleep 0.1; done
nohup python3 "$here/server.py" "$@" >>"$data/server.log" 2>&1 &
echo "restarted: old ${old:-none}, new $!"
