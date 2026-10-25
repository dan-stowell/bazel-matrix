#!/usr/bin/env python3
"""Runs every project's build or test as K concurrent `bb remote` invocations.

    tools/run.py test                  # all projects, 4 shards
    tools/run.py build --shards 8
    tools/run.py test zlib re2         # only these projects
    tools/run.py test --known-failing  # also the known-failing ones
    tools/run.py test -- --test_output=all   # extra outer Bazel flags

Each shard is one `tools/bb.sh <command> //<m>:<command> ...` on its own
runner (concurrent remote runs get separate runners). Projects are dealt to
shards round-robin in name order. It prints each shard's invocation links as
it finishes, then one row per project and the totals; the logs are in
bb-out/run/. Exit status 0 when every project passed.

Without project names it skips the projects that projects.txt marks
known-failing for the command (known-failing build: both; known-failing
test: test only), as `//...` does.
"""

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync  # noqa: E402

RESULTS_URL = "https://buildbuddy.buildbuddy.io/invocation/"
# FLAKY: passed on a retry.
PASSING = {"PASSED", "FLAKY"}
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d+(?:;\d+)*m")
_EXIT = re.compile(r"\(command exited with code (\d+)\)")
_STREAM = re.compile(r"Streaming build results to: (\S+/invocation/[0-9a-f-]+)")
_TEST = re.compile(r"^(//[^:\s]+:test)\s+(?:\(cached\)\s+)?"
                   r"(PASSED|FAILED TO BUILD|FAILED|TIMEOUT|FLAKY|NO STATUS|INCOMPLETE|"
                   r"REMOTE FAILURE|SKIPPED)\b")
_BUILD_ERROR = re.compile(r"^ERROR: (?:\S*/)?([^/\s]+)/BUILD\.bazel:\d+:\d+: ")


def select_projects(projects, command, names, known_failing):
    """The projects (in projects.txt order) the command runs.

    Known-failing ones only when named or with known_failing set.
    """
    known = {p["name"] for p in projects}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError("not in projects.txt: " + ", ".join(unknown))
    out = []
    for p in projects:
        if names and p["name"] not in names:
            continue
        kf = p.get("known_failing")
        if kf and not (names or known_failing) and (command == "test" or kf[0] == "build"):
            continue
        out.append(p["name"])
    return out


def shard(names, k):
    """Round-robin over names in sorted order; no empty shards."""
    names = sorted(names)
    k = max(1, min(k, len(names)))
    return [names[i::k] for i in range(k)]


def parse_log(text, command, names):
    """(runner exit code or None, outer invocation link or "", {name: status})."""
    text = _ANSI.sub("", text)
    codes = _EXIT.findall(text)
    code = int(codes[-1]) if codes else None
    links = _STREAM.findall(text)
    status = {}
    for line in text.splitlines():
        line = line.strip()
        if command == "test":
            m = _TEST.match(line)
            if m:
                status[m.group(1)[2:].split(":")[0]] = m.group(2)
        else:
            m = _BUILD_ERROR.match(line)
            if m:
                status[m.group(1)] = "FAILED"
    status = {n: s for n, s in status.items() if n in names}
    failed_found = bool(status)
    for n in names:
        if n in status:
            continue
        if command == "build" and code == 0:
            status[n] = "PASSED"
        elif command == "build" and code == 1 and failed_found:
            # --keep_going: the projects not reported as failed built.
            status[n] = "PASSED"
        else:
            status[n] = "UNKNOWN"
    return code, links[0] if links else "", status


def run_shard(i, command, names, extra, out_dir):
    targets = ["//%s:%s" % (n, command) for n in names]
    if not targets:
        raise ValueError("shard %d is empty" % i)
    log_path = os.path.join(out_dir, "%s-%d.log" % (command, i))
    id_path = os.path.join(out_dir, "%s-%d.id" % (command, i))
    if os.path.exists(id_path):
        os.remove(id_path)
    start = time.time()
    with open(log_path, "w") as log:
        proc = subprocess.run([os.path.join(ROOT, "tools", "bb.sh"), "--invocation_id_file=" + id_path,
                               command] + targets + extra,
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    wall = time.time() - start
    with open(log_path, errors="replace") as f:
        code, outer, status = parse_log(f.read(), command, names)
    remote = ""
    if os.path.exists(id_path):
        with open(id_path) as f:
            remote = RESULTS_URL + f.read().strip()
    return {"shard": i, "bb_exit": proc.returncode, "code": code, "remote": remote,
            "outer": outer, "status": status, "wall": wall, "log": log_path}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 2)[2])
    ap.add_argument("command", choices=["build", "test"])
    ap.add_argument("projects", nargs="*", help="only these projects (default: all)")
    ap.add_argument("--shards", type=int, default=4)
    ap.add_argument("--known-failing", action="store_true",
                    help="also run the projects marked known-failing")
    argv = sys.argv[1:] if argv is None else argv
    extra = []
    if "--" in argv:
        extra = argv[argv.index("--") + 1:]
        argv = argv[:argv.index("--")]
    args = ap.parse_intermixed_args(argv)

    projects = sync.parse_projects_txt(sync.read("projects.txt"))
    # Only the projects sync wrote a package for.
    synced = {p["name"] for p in __import__("json").loads(sync.read("projects.json"))["projects"]}
    projects = [p for p in projects if p["name"] in synced]
    names = select_projects(projects, args.command, args.projects, args.known_failing)
    if not names:
        sys.exit("no projects to run")
    shards = shard(names, args.shards)
    out_dir = os.path.join(ROOT, "bb-out", "run")
    os.makedirs(out_dir, exist_ok=True)
    print("%s: %d projects in %d shards; logs in %s" % (args.command, len(names), len(shards),
                                                        os.path.relpath(out_dir)), flush=True)
    start = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(len(shards)) as pool:
        futures = [pool.submit(run_shard, i, args.command, s, extra, out_dir)
                   for i, s in enumerate(shards)]
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            results.append(r)
            failed = sum(s not in PASSING for s in r["status"].values())
            print("shard %d: exit %s, %d/%d passed, %dm%02ds  %s  outer %s" % (
                r["shard"], r["code"] if r["code"] is not None else "?(bb %d)" % r["bb_exit"],
                len(r["status"]) - failed, len(r["status"]), r["wall"] // 60, r["wall"] % 60,
                r["remote"] or "(no remote id)", r["outer"] or "(none)"), flush=True)
    results.sort(key=lambda r: r["shard"])
    rows = sorted((n, s, r["shard"]) for r in results for n, s in r["status"].items())
    width = max(len(n) for n, _, _ in rows)
    print()
    for n, s, i in rows:
        print("%-*s  %-15s shard %d" % (width, n, s, i))
    totals = {}
    for _, s, _ in rows:
        totals[s] = totals.get(s, 0) + 1
    wall = time.time() - start
    print("\n%s: %s; wall %dm%02ds" % (args.command, ", ".join(
        "%s %d" % kv for kv in sorted(totals.items())), wall // 60, wall % 60))
    # The runner's exit code too: a shard can fail after its targets passed.
    ok = set(totals) <= PASSING and all(r["code"] == 0 for r in results)
    if not ok and set(totals) <= PASSING:
        print("a shard failed although every project passed; see its log")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
