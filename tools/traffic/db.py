#!/usr/bin/env python3
"""SQLite state store for the BBT traffic generator.

Schema and CLI subcommands used by traffic.sh:

    db.py init
    db.py start  --round N --endpoint NAME --target //...  [--project P]
        -> prints the run id on stdout
    db.py finish --id ID --status STATUS [--exit-code N] [--invocation URL]
    db.py running
        -> JSON array of currently-running rows
    db.py recent [--limit N] [--json]
        -> JSON array or plain-text table of recent runs
    db.py stats
        -> JSON summary counts

The DB path defaults to $TRAFFIC_DB or tools/traffic/traffic.sqlite.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traffic.sqlite")


def db_path() -> str:
    return os.environ.get("TRAFFIC_DB", DEFAULT_DB)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    round         INTEGER NOT NULL,
    endpoint      TEXT NOT NULL,
    endpoint_url  TEXT NOT NULL,
    target        TEXT NOT NULL,
    project       TEXT NOT NULL,
    status        TEXT NOT NULL,
    exit_code     INTEGER,
    invocation    TEXT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    duration_secs REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
CREATE INDEX IF NOT EXISTS idx_runs_endpoint ON runs(endpoint);
"""


def cmd_init(args):
    with connect() as conn:
        conn.executescript(_SCHEMA)
    print("ok", file=sys.stderr)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _project_from_target(target: str) -> str:
    # //projects/cctz/bbt:cctz_rbe_test -> cctz
    t = target
    if t.startswith("//projects/"):
        rest = t[len("//projects/"):]
        # rest = cctz/bbt:cctz_rbe_test
        return rest.split("/", 1)[0]
    return t


def cmd_start(args):
    project = args.project or _project_from_target(args.target)
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (round, endpoint, endpoint_url, target, project, "
            "status, started_at) VALUES (?,?,?,?,?,?,?)",
            (args.round, args.endpoint, args.endpoint_url or "",
             args.target, project, "running", _now()),
        )
        rid = cur.lastrowid
    print(rid)


def cmd_finish(args):
    now = _now()
    with connect() as conn:
        row = conn.execute(
            "SELECT started_at FROM runs WHERE id = ?", (args.id,)
        ).fetchone()
        dur = None
        if row:
            try:
                started = datetime.fromisoformat(row["started_at"])
                dur = (datetime.now(timezone.utc) - started).total_seconds()
            except Exception:
                pass
        conn.execute(
            "UPDATE runs SET status=?, exit_code=?, invocation=?, "
            "finished_at=?, duration_secs=? WHERE id=?",
            (args.status, args.exit_code, args.invocation, now, dur, args.id),
        )


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def cmd_running(args):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs WHERE status='running' ORDER BY id DESC"
        ).fetchall()
    print(json.dumps([_row_to_dict(r) for r in rows], indent=2))


def cmd_recent(args):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (args.limit,)
        ).fetchall()
    print(json.dumps([_row_to_dict(r) for r in rows], indent=2))


def cmd_stats(args):
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
        by_status = {
            r["status"]: r["c"]
            for r in conn.execute(
                "SELECT status, COUNT(*) AS c FROM runs GROUP BY status"
            ).fetchall()
        }
        by_endpoint = {
            r["endpoint"]: {"total": r["c"], "passed": r["p"] or 0}
            for r in conn.execute(
                "SELECT endpoint, COUNT(*) AS c, "
                "SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS p "
                "FROM runs GROUP BY endpoint"
            ).fetchall()
        }
        last = conn.execute(
            "SELECT finished_at FROM runs WHERE finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    print(json.dumps({
        "total": total,
        "by_status": by_status,
        "by_endpoint": by_endpoint,
        "last_finished_at": last["finished_at"] if last else None,
    }, indent=2))


def cmd_cleanup_orphans(args):
    """Mark any 'running' rows as 'interrupted' — they were left behind by a
    previous process that was killed/restarted before finishing."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE runs SET status='interrupted', "
            "finished_at=? WHERE status='running'",
            (_now(),),
        )
    print(json.dumps({"cleaned": cur.rowcount}), file=sys.stderr)


def main(argv=None):
    p = argparse.ArgumentParser(description="Traffic DB CLI")
    p.add_argument("--db", help="override DB path")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    s = sub.add_parser("start")
    s.add_argument("--round", type=int, required=True)
    s.add_argument("--endpoint", required=True)
    s.add_argument("--endpoint-url", default="")
    s.add_argument("--target", required=True)
    s.add_argument("--project", default=None)
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("finish")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--status", required=True)
    s.add_argument("--exit-code", type=int, default=None)
    s.add_argument("--invocation", default=None)
    s.set_defaults(func=cmd_finish)

    sub.add_parser("running").set_defaults(func=cmd_running)
    s = sub.add_parser("recent")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(func=cmd_recent)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    sub.add_parser("cleanup-orphans").set_defaults(func=cmd_cleanup_orphans)

    args = p.parse_args(argv)
    if args.db:
        os.environ["TRAFFIC_DB"] = args.db
    args.func(args)


if __name__ == "__main__":
    main()
