#!/usr/bin/env python3
"""Runs every project's build or test as K concurrent `bb remote` invocations.

    tools/run.py test                  # all projects, 4 shards
    tools/run.py build --shards 8
    tools/run.py test zlib re2         # only these projects
    tools/run.py test --known-failing  # also the known-failing ones
    tools/run.py test -- --test_output=all   # extra outer Bazel flags

Each shard is one `tools/bb.sh <command> <targets>` on its own runner
(concurrent remote runs get separate runners). Projects are dealt to shards
round-robin in name order. It prints each shard's invocation links as it
finishes, then one row per project and the totals; the logs are in
bb-out/run/<command>-<time>-<pid>/. Exit status 0 when every project passed
and every shard's runner Bazel exited 0.

Without project names it leaves out what `//...` leaves out: a
`known-failing build` project entirely; for a `known-failing test` project,
`test` runs its :build instead of its :test (row BUILT), so a regression of
its inner build still shows.

A shard's result is its runner's Bazel exit code, not `bb remote`'s: after
the run, `bb remote` downloads the top-level outputs, which can fail
(`download blob ... NotFound`) and make it exit 1 although Bazel passed. It
has no flag to skip that download, so a disagreement is printed as a
warning.
"""

import argparse
import collections
import concurrent.futures
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync  # noqa: E402

RESULTS_URL = "https://buildbuddy.buildbuddy.io/invocation/"
# FLAKY: passed on a retry. BUILT: the :build of a known-failing test project.
PASSING = {"PASSED", "FLAKY", "BUILT"}
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d+(?:;\d+)*m")
_EXIT = re.compile(r"\(command exited with code (\d+)\)")
_STREAM = re.compile(r"Streaming build results to: (\S+/invocation/[0-9a-f-]+)")
_TEST = re.compile(r"^//([^:\s/]+):test\s+(?:\(cached\)\s+)?"
                   r"(PASSED|FAILED TO BUILD|FAILED|TIMEOUT|FLAKY|NO STATUS|INCOMPLETE|"
                   r"REMOTE FAILURE|SKIPPED)\b")
# With --show_result (see run_shard), Bazel reports every top-level target.
_BUILD = re.compile(r"^Target //([^:\s/]+):build (up-to-date|failed to build)")
# The line ending the outer summary, a few lines before the outer Bazel's
# last "Streaming build results to" line.
_END = {"build": re.compile(r"^INFO: Elapsed time: "),
        "test": re.compile(r"^Executed \d+ out of \d+ tests?\b")}
# What the outer summary is made of, read backwards from its end.
_SUMMARY = re.compile(r"^(\s|$|//|@|Target //|INFO: (Elapsed time|\d+ processes|Build completed)|"
                      r"ERROR: Build did NOT|FAILED: Build did NOT|Use --verbose_failures )")

_procs, _lock = [], threading.Lock()


def select_projects(projects, command, names, known_failing):
    """{project: "build" or "test"}: the target of each project to run.

    `names` (and `known_failing`) runs the named (all) projects' command;
    otherwise known-failing ones are left out as in the docstring.
    """
    known = {p["name"] for p in projects}
    unknown = [n for n in names if n not in known]
    if unknown:
        raise ValueError("not in projects.txt: " + ", ".join(unknown))
    out = {}
    for p in projects:
        if names and p["name"] not in names:
            continue
        kf = (p.get("known_failing") or ("",))[0]
        if names or known_failing or not kf:
            out[p["name"]] = command
        elif kf == "test":
            out[p["name"]] = "build"
    return out


def shard(names, k):
    """Round-robin over names in sorted order; no empty shards."""
    names = sorted(names)
    k = max(1, min(k, len(names)))
    return [names[i::k] for i in range(k)]


def summary_lines(lines, command):
    """The outer Bazel's final summary lines, [] if it never printed one.

    Only those: a project's inner output (in a failing outer test's log)
    has result lines of its own, maybe even `//<project>:test PASSED`.
    """
    links = [i for i, l in enumerate(lines) if _STREAM.search(l)]
    if not links:
        return []
    outer = _STREAM.search(lines[links[0]]).group(1)
    last = max(i for i in links if _STREAM.search(lines[i]).group(1) == outer)
    end = next((i for i in range(last - 1, max(last - 10, -1), -1)
                if _END[command].match(lines[i])), None)
    if end is None:
        return []
    start = end
    while start > 0 and _SUMMARY.match(lines[start - 1]):
        start -= 1
    return lines[start:end]


def parse_log(text, command, targets):
    """(runner exit code or None, outer link or "", {project: status}).

    targets maps each project of the shard to the target that ran
    ("build" or "test"); a project without a result line is UNKNOWN.
    """
    lines = [l.rstrip() for l in _ANSI.sub("", text).splitlines()]
    codes = _EXIT.findall(text)
    code = int(codes[-1]) if codes else None
    links = [m.group(1) for m in map(_STREAM.search, lines) if m]
    status = {}
    for line in summary_lines(lines, command):
        m = _TEST.match(line)
        if m and targets.get(m.group(1)) == "test":
            status[m.group(1)] = m.group(2)
        m = _BUILD.match(line)
        if m and targets.get(m.group(1)) == "build":
            ok = m.group(2) == "up-to-date"
            status[m.group(1)] = ("PASSED" if command == "build" else "BUILT") if ok else "FAILED"
    return code, links[0] if links else "", {n: status.get(n, "UNKNOWN") for n in targets}


def run_shard(i, command, targets, extra, out_dir):
    labels = ["//%s:%s" % kv for kv in sorted(targets.items())]
    if not labels:
        raise ValueError("shard %d is empty" % i)
    log_path = os.path.join(out_dir, "%d.log" % i)
    id_path = os.path.join(out_dir, "%d.id" % i)
    # A shard of only :build targets (known-failing test projects) builds:
    # `bazel test` without tests would exit 4.
    bazel_command = "build" if set(targets.values()) == {"build"} else command
    # A result line per non-test target, so passes are reported, not inferred.
    flags = ["--show_result=1000000"]
    if bazel_command == "test" and "build" in targets.values():
        flags.append("--nobuild_tests_only")  # .bazelrc sets it for test
    start = time.time()
    with open(log_path, "w") as log:
        with _lock:
            if None in _procs:
                raise RuntimeError("stopping")
            proc = subprocess.Popen(
                [os.path.join(ROOT, "tools", "bb.sh"), "--invocation_id_file=" + id_path,
                 bazel_command]
                + labels + flags + extra,
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            _procs.append(proc)
        proc.wait()
    wall = time.time() - start
    with open(log_path, errors="replace") as f:
        code, outer, status = parse_log(f.read(), bazel_command, targets)
    if bazel_command != command:
        status = {n: "BUILT" if s == "PASSED" else s for n, s in status.items()}
    remote = ""
    if os.path.exists(id_path):
        with open(id_path) as f:
            remote = RESULTS_URL + f.read().strip()
    return {"shard": i, "bb_exit": proc.returncode, "code": code, "remote": remote,
            "outer": outer, "status": status, "wall": wall, "log": log_path, "error": ""}


_stopping = []


def stop_all(signum, _frame):
    """Stops every bb remote child (SIGINT makes it cancel its remote run)."""
    if _stopping:
        return  # a second signal while stopping
    _stopping.append(signum)
    with _lock:
        procs = [p for p in _procs if p is not None]
        _procs.append(None)  # no new children after this
    for p in procs:
        if p.poll() is None:
            p.send_signal(signal.SIGINT)
    deadline = time.time() + 20
    for p in procs:
        try:
            p.wait(max(0, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    os._exit(128 + signum)


def shard_result(i, future, targets):
    try:
        return future.result()
    except Exception as e:  # a failed shard, not a failed run
        return {"shard": i, "bb_exit": None, "code": None, "remote": "", "outer": "",
                "status": {n: "ERROR" for n in targets}, "wall": 0, "log": "",
                "error": "%s: %s" % (type(e).__name__, e)}


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
    skipped = {s["name"]: s["reason"] for s in json.loads(sync.read("projects.json"))["skipped"]}
    for n in args.projects:
        if n in skipped:
            sys.exit("%s: skipped by sync: %s" % (n, skipped[n]))
    # Only the projects sync wrote a package for.
    projects = [p for p in projects if os.path.exists(os.path.join(ROOT, p["name"], "BUILD.bazel"))]
    targets = select_projects(projects, args.command, args.projects, args.known_failing)
    if not targets:
        sys.exit("no projects to run")
    shards = [{n: targets[n] for n in s} for s in shard(targets, args.shards)]
    # Its own dir, so concurrent runs don't share logs.
    out_dir = os.path.join(ROOT, "bb-out", "run", "%s-%s-%d" % (
        args.command, time.strftime("%Y%m%d-%H%M%S"), os.getpid()))
    os.makedirs(out_dir)
    print("%s: %d projects in %d shards; logs in %s" % (args.command, len(targets), len(shards),
                                                        os.path.relpath(out_dir)), flush=True)
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)
    start = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(len(shards)) as pool:
        futures = {pool.submit(run_shard, i, args.command, s, extra, out_dir): i
                   for i, s in enumerate(shards)}
        for f in concurrent.futures.as_completed(futures):
            i = futures[f]
            r = shard_result(i, f, shards[i])
            results.append(r)
            passed = sum(s in PASSING for s in r["status"].values())
            if r["error"]:
                print("shard %d: ERROR %s" % (i, r["error"]), flush=True)
                continue
            print("shard %d: exit %s, %d/%d passed, %dm%02ds  %s  outer %s" % (
                i, "?" if r["code"] is None else r["code"], passed, len(r["status"]),
                r["wall"] // 60, r["wall"] % 60, r["remote"] or "(no remote id)",
                r["outer"] or "(none)"), flush=True)
            if (r["bb_exit"] == 0) != (r["code"] == 0):
                print("shard %d: WARNING: bb remote exited %s but the runner's Bazel exited %s; "
                      "see %s" % (i, r["bb_exit"], r["code"], os.path.relpath(r["log"])), flush=True)
    rows = sorted((n, s, r["shard"]) for r in results for n, s in r["status"].items())
    width = max(len(n) for n, _, _ in rows)
    print()
    for n, s, i in rows:
        print("%-*s  %-15s shard %d" % (width, n, s, i))
    totals = collections.Counter(s for _, s, _ in rows)
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
