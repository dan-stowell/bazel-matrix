#!/usr/bin/env python3
"""Web dashboard for the BBT traffic generator.

Serves a single HTML page on port 8000 (override with $PORT) that shows:
  • the currently-running target(s)
  • a recent-runs table with status, duration, and BuildBuddy invocation links
  • summary stats per endpoint

Data comes from the same SQLite store that traffic.sh writes to. The page
auto-refreshes every 5 s.
"""

import html
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB_PATH = os.environ.get(
    "TRAFFIC_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "traffic.sqlite"),
)
PORT = int(os.environ.get("PORT", "8000"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _row(d: sqlite3.Row) -> dict:
    return {k: d[k] for k in d.keys()}


def fetch_data() -> dict:
    with connect() as conn:
        running = [
            _row(r) for r in conn.execute(
                "SELECT * FROM runs WHERE status='running' ORDER BY id DESC"
            ).fetchall()
        ]
        recent = [
            _row(r) for r in conn.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT 100"
            ).fetchall()
        ]
        total = conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]
        by_status = {
            r["status"]: r["c"]
            for r in conn.execute(
                "SELECT status, COUNT(*) AS c FROM runs GROUP BY status"
            ).fetchall()
        }
        by_endpoint = {
            r["endpoint"]: {
                "total": r["c"],
                "passed": r["p"] or 0,
                "failed": r["f"] or 0,
            }
            for r in conn.execute(
                "SELECT endpoint, COUNT(*) AS c, "
                "SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) AS p, "
                "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS f "
                "FROM runs GROUP BY endpoint"
            ).fetchall()
        }
        rounds = conn.execute(
            "SELECT MAX(round) AS max_round FROM runs"
        ).fetchone()["max_round"] or 0
    return {
        "running": running,
        "recent": recent,
        "total": total,
        "by_status": by_status,
        "by_endpoint": by_endpoint,
        "max_round": rounds,
    }


_STATUS_CLASS = {
    "passed": "s-pass",
    "failed": "s-fail",
    "running": "s-run",
    "timed_out": "s-timeout",
    "skipped": "s-skip",
    "interrupted": "s-skip",
}


def _status_badge(status: str) -> str:
    cls = _STATUS_CLASS.get(status, "s-unk")
    return f'<span class="badge {cls}">{html.escape(status)}</span>'


def _invocation_link(row: dict) -> str:
    inv = row.get("invocation")
    if not inv:
        return '<span class="muted">—</span>'
    short = inv.rstrip("/").split("/")[-1]
    short = short[:8] + "…" if len(short) > 12 else short
    return f'<a href="{html.escape(inv)}" target="_blank" rel="noopener">{html.escape(short)}</a>'


def _fmt_duration(secs) -> str:
    if secs is None:
        return "—"
    if secs < 60:
        return f"{secs:.1f}s"
    m, s = divmod(int(secs), 60)
    return f"{m}m{s}s"


def _fmt_started(iso: str) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso


def render_page(data: dict) -> str:
    running = data["running"]
    recent = data["recent"]
    stats = data["by_status"]
    ep_stats = data["by_endpoint"]

    # --- Summary cards ---
    cards = []
    cards.append(
        f'<div class="card"><div class="card-num">{data["total"]}</div>'
        f'<div class="card-label">total runs</div></div>'
    )
    cards.append(
        f'<div class="card"><div class="card-num">{data["max_round"]}</div>'
        f'<div class="card-label">rounds</div></div>'
    )
    for st in ("running", "passed", "failed", "timed_out", "interrupted"):
        cards.append(
            f'<div class="card"><div class="card-num">{stats.get(st, 0)}</div>'
            f'<div class="card-label">{st}</div></div>'
        )
    cards_html = "\n".join(cards)

    # --- Endpoint stats ---
    ep_rows = []
    for ep in sorted(ep_stats):
        s = ep_stats[ep]
        ep_rows.append(
            f"<tr><td><code>{html.escape(ep)}</code></td>"
            f"<td>{s['total']}</td><td class=\"pass\">{s['passed']}</td>"
            f"<td class=\"fail\">{s['failed']}</td></tr>"
        )
    ep_table = "\n".join(ep_rows) or '<tr><td colspan="4" class="muted">no data</td></tr>'

    # --- Currently running ---
    if running:
        run_rows = []
        for r in running:
            run_rows.append(
                f"<tr><td><code>{html.escape(r['target'])}</code></td>"
                f"<td><span class=\"ep ep-{html.escape(r['endpoint'])}\">{html.escape(r['endpoint'])}</span></td>"
                f"<td>R{r['round']}</td>"
                f"<td>{_status_badge(r['status'])}</td>"
                f"<td class=\"muted\">{_fmt_started(r['started_at'])}</td></tr>"
            )
        running_html = (
            '<table class="grid"><thead><tr>'
            '<th>target</th><th>endpoint</th><th>round</th>'
            '<th>status</th><th>started</th></tr></thead>'
            f'<tbody>{"".join(run_rows)}</tbody></table>'
        )
    else:
        running_html = '<div class="muted empty">nothing running right now</div>'

    # --- Recent runs ---
    recent_rows = []
    for r in recent:
        recent_rows.append(
            f"<tr>"
            f"<td>{r['id']}</td>"
            f"<td>R{r['round']}</td>"
            f"<td><span class=\"ep ep-{html.escape(r['endpoint'])}\">{html.escape(r['endpoint'])}</span></td>"
            f"<td class=\"mono\">{html.escape(r['target'])}</td>"
            f"<td>{_status_badge(r['status'])}</td>"
            f"<td>{r['exit_code'] if r['exit_code'] is not None else '—'}</td>"
            f"<td>{_fmt_duration(r['duration_secs'])}</td>"
            f"<td class=\"muted\">{_fmt_started(r['started_at'])}</td>"
            f"<td>{_invocation_link(r)}</td>"
            f"</tr>"
        )
    recent_body = "\n".join(recent_rows) or '<tr><td colspan="9" class="muted">no runs yet</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BBT Traffic Dashboard</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --pass: #3fb950; --fail: #f85149; --run: #d29922; --skip: #8b949e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
      Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text);
    font-size: 14px; line-height: 1.5;
  }}
  .wrap {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; font-weight: 600; margin: 28px 0 10px;
       color: var(--muted); text-transform: uppercase; letter-spacing: .5px; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 24px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px 20px; min-width: 100px;
  }}
  .card-num {{ font-size: 24px; font-weight: 700; }}
  .card-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
  table.grid {{
    width: 100%; border-collapse: collapse; background: var(--card);
    border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
  }}
  table.grid th, table.grid td {{
    padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border);
  }}
  table.grid th {{
    background: #21262d; font-weight: 600; font-size: 12px;
    text-transform: uppercase; color: var(--muted); letter-spacing: .5px;
  }}
  table.grid tbody tr:last-child td {{ border-bottom: none; }}
  table.grid tbody tr:hover {{ background: #1c2128; }}
  .mono, code {{ font-family: "SF Mono", Consolas, "Liberation Mono", monospace;
                font-size: 12.5px; }}
  .muted {{ color: var(--muted); }}
  .empty {{ padding: 18px; text-align: center; }}
  .pass {{ color: var(--pass); }}
  .fail {{ color: var(--fail); }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
  }}
  .s-pass {{ background: rgba(63,185,80,.15); color: var(--pass); }}
  .s-fail {{ background: rgba(248,81,73,.15); color: var(--fail); }}
  .s-run  {{ background: rgba(210,153,34,.15); color: var(--run); }}
  .s-skip    {{ background: rgba(139,148,158,.15); color: var(--skip); }}
  .s-timeout {{ background: rgba(210,153,34,.15); color: var(--run); }}
  .s-unk  {{ background: rgba(139,148,158,.15); color: var(--muted); }}
  .ep {{
    display: inline-block; padding: 1px 7px; border-radius: 4px;
    font-size: 11px; font-weight: 600; border: 1px solid var(--border);
  }}
  .ep-dev {{ color: #a371f7; border-color: #6e40c9; }}
  .ep-io  {{ color: #58a6ff; border-color: #1f6feb; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .recent-wrap {{ overflow-x: auto; }}
  .recent-wrap table {{ min-width: 800px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>BBT Traffic Dashboard</h1>
  <div class="sub">bazel-matrix test traffic generator · auto-refresh 5s</div>

  <div class="cards">{cards_html}</div>

  <h2>By endpoint</h2>
  <table class="grid">
    <thead><tr><th>endpoint</th><th>total</th><th>passed</th><th>failed</th></tr></thead>
    <tbody>{ep_table}</tbody>
  </table>

  <h2>Currently running</h2>
  {running_html}

  <h2>Recent runs</h2>
  <div class="recent-wrap">
  <table class="grid">
    <thead><tr>
      <th>#</th><th>round</th><th>endpoint</th><th>target</th>
      <th>status</th><th>rc</th><th>dur</th><th>started</th><th>invocation</th>
    </tr></thead>
    <tbody>{recent_body}</tbody>
  </table>
  </div>
</div>
<script>setTimeout(function(){{location.reload()}},5000);</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            try:
                data = fetch_data()
                body = render_page(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                msg = f"dashboard error: {e}".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)
        elif self.path == "/api/state":
            try:
                body = json.dumps(fetch_data(), indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # quiet


def main():
    if not os.path.exists(DB_PATH):
        print(f"WARNING: DB not found at {DB_PATH}; will create on first write",
              file=sys.stderr)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"dashboard listening on http://0.0.0.0:{PORT} "
          f"(db: {DB_PATH})", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
