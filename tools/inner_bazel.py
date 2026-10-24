#!/usr/bin/env python3
"""Runs one project's inner `bazel build` or `bazel test`.

Called by the targets tools/project.bzl declares. It extracts the project's
source.tar into a fresh work dir, runs the pinned inner Bazel there in
--batch mode with its own output user root, and deletes the work dir
afterwards, so a runner's disk doesn't grow per run. Downloads go through a
repository cache shared by every inner Bazel on the machine.

build mode writes --summary (invocation link and counts) and --log (the
inner output). test mode streams the inner output to the test log and writes
$XML_OUTPUT_FILE with one testcase per inner test target, plus one per
non-test target that failed to build.

Exit status: 0 when the inner Bazel succeeded (for test, also when it found
no tests), else 1.
"""

import argparse
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

WORK_ROOT = "/tmp/bazel-matrix/work"
REPOSITORY_CACHE = "/tmp/bazel-matrix/repository_cache"
REPOSITORY_CACHE_LIMIT = 4e9

# Inner exit codes that count as success: 4 is "no test targets found".
_OK = {"build": {0}, "test": {0, 4}}
_PASSING = {"PASSED", "FLAKY"}


def parse_args(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["build", "test"], required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--bazel", required=True)
    p.add_argument("--bazel_version", required=True)
    p.add_argument("--rc", action="append", default=[])
    p.add_argument("--credential_helper", required=True)
    p.add_argument("--startup_flag", action="append", default=[])
    p.add_argument("--flag", action="append", default=[])
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--summary")
    p.add_argument("--log")
    p.add_argument("--timeout", type=int, default=3 * 3600)
    return p.parse_args(argv)


def inner_command(args, out_root, bep):
    """The inner Bazel command line."""
    startup = [
        "--batch",
        "--nosystem_rc",
        "--nohome_rc",
        "--output_user_root=" + out_root,
    ] + ["--bazelrc=" + rc for rc in args.rc] + args.startup_flag
    flags = [
        "--repository_cache=" + REPOSITORY_CACHE,
        "--credential_helper=*.buildbuddy.io=" + args.credential_helper,
        "--build_event_json_file=" + bep,
        "--build_metadata=PROJECT=" + args.project,
    ]
    if args.mode == "test":
        flags.append("--test_output=errors")
    return [args.bazel] + startup + [args.mode] + flags + args.flag + ["--"] + args.target


def load_bep(lines):
    """Per-target results from inner BEP JSON lines.

    Returns (invocation_id, tests, failed_builds): tests maps each configured
    test target to (status, millis); failed_builds lists the non-test targets
    that failed.
    """
    invocation = ""
    test_targets, summaries, completed, aborted = set(), {}, {}, {}
    for line in lines:
        if not line.strip():
            continue
        event = json.loads(line)
        eid = event.get("id", {})
        if "started" in eid:
            invocation = event.get("started", {}).get("uuid", "")
        if "targetConfigured" in eid and "testSize" in event.get("configured", {}):
            test_targets.add(eid["targetConfigured"]["label"])
        if "testSummary" in eid:
            s = event.get("testSummary", {})
            label = eid["testSummary"]["label"]
            # A label can be tested in several configurations; keep a failure.
            if summaries.get(label, ("PASSED",))[0] in _PASSING:
                summaries[label] = (
                    s.get("overallStatus", "NO_STATUS"), int(s.get("totalRunDurationMillis", 0)))
        if "targetCompleted" in eid:
            label = eid["targetCompleted"]["label"]
            if "aborted" in event:
                aborted[label] = event["aborted"].get("reason", "UNKNOWN")
            else:
                completed[label] = completed.get(label, True) and event.get("completed", {}).get("success", False)
        elif "targetConfigured" in eid and "aborted" in event:
            aborted[eid["targetConfigured"]["label"]] = event["aborted"].get("reason", "UNKNOWN")
    tests = {}
    for label in test_targets | set(summaries):
        if label in summaries:
            tests[label] = summaries[label]
        elif aborted.get(label) == "SKIPPED":
            tests[label] = ("SKIPPED", 0)
        elif completed.get(label):
            # Built, not run: `bazel build`.
            tests[label] = ("BUILT", 0)
        else:
            tests[label] = ("FAILED_TO_BUILD", 0)
    failed_builds = sorted(
        ({l for l, ok in completed.items() if not ok} |
         {l for l, r in aborted.items() if r != "SKIPPED"})
        - set(tests))
    return invocation, tests, failed_builds


def test_xml(project, tests, failed_builds, link, ok=True):
    """A JUnit XML document: one testcase per inner test target.

    A failed inner invocation that no target failure explains (a bad flag,
    a target pattern error, a timeout) gets an `invocation` testcase.
    """
    suite = ET.Element("testsuite", name=project)
    failures = skipped = 0
    for label in sorted(tests):
        status, millis = tests[label]
        case = ET.SubElement(suite, "testcase", name=label, classname=project,
                             time="%.3f" % (millis / 1000.0))
        if status in ("SKIPPED", "BUILT"):
            # BUILT: built but not run, e.g. a test_suite member under an
            # excluded pattern.
            skipped += 1
            ET.SubElement(case, "skipped", message=status)
        elif status not in _PASSING:
            failures += 1
            ET.SubElement(case, "failure", message=status).text = "%s %s; see %s" % (label, status, link)
    for label in failed_builds:
        failures += 1
        case = ET.SubElement(suite, "testcase", name=label, classname=project + ".build")
        ET.SubElement(case, "failure", message="FAILED_TO_BUILD").text = "see " + link
    count = len(tests) + len(failed_builds)
    if not ok and not failures:
        failures += 1
        count += 1
        case = ET.SubElement(suite, "testcase", name="invocation", classname=project)
        ET.SubElement(case, "failure", message="INNER_BAZEL_FAILED").text = "see " + link
    suite.set("tests", str(count))
    suite.set("failures", str(failures))
    suite.set("skipped", str(skipped))
    ET.SubElement(suite, "system-out").text = "inner invocation: " + link
    root = ET.Element("testsuites")
    root.append(suite)
    return ET.tostring(root, encoding="unicode") + "\n"


def results_url(rc_texts):
    """The --bes_results_url the rc files set, or BuildBuddy's default."""
    url = "https://app.buildbuddy.io/invocation/"
    for text in rc_texts:
        for m in re.finditer(r"--bes_results_url=(\S+)", text):
            url = m.group(1)
    return url.rstrip("/") + "/"


def summary_text(project, mode, version, code, link, tests, failed_builds, stats):
    counts = {}
    for status, _ in tests.values():
        counts[status] = counts.get(status, 0) + 1
    lines = [
        "project: " + project,
        "command: " + mode,
        "inner bazel: " + version,
        "exit code: %d" % code,
        "inner invocation: " + link,
        "tests: " + (", ".join("%s %d" % kv for kv in sorted(counts.items())) or "none"),
        "failed to build: %d" % len(failed_builds),
    ] + ["  " + l for l in failed_builds] + ["%s: %s" % kv for kv in stats]
    return "\n".join(lines) + "\n"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def bazel_path_dir(args):
    """A dir holding only a `bazel` symlink to the inner Bazel."""
    d = os.path.join(os.path.dirname(args.source_dir), "bin")
    os.makedirs(d, exist_ok=True)
    os.symlink(args.bazel, os.path.join(d, "bazel"))
    return d


def remove_tree(path):
    # Bazel makes parts of its output and install bases read-only.
    subprocess.run(["chmod", "-R", "u+rwx", path], stderr=subprocess.DEVNULL)
    shutil.rmtree(path, ignore_errors=True)


def remove_stale(root):
    """Removes work dirs left by killed runs (their pid file names a dead pid)."""
    for d in os.listdir(root):
        path = os.path.join(root, d)
        try:
            with open(os.path.join(path, "pid")) as f:
                pid = int(f.read())
        except (OSError, ValueError):
            try:
                if time.time() - os.path.getmtime(path) < 600:
                    continue
            except OSError:
                continue  # removed meanwhile
            pid = 0
        if not pid or not _alive(pid):
            remove_tree(path)


def _du(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_blocks * 512
            except OSError:
                pass
    return total


def _big_dirs(work):
    """The output base's subdirectories, to show where a work dir's space goes."""
    out = []
    root = os.path.join(work, "out")
    for d in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        base = os.path.join(root, d)
        if os.path.isdir(base):
            out += [os.path.join("out", d, e) for e in sorted(os.listdir(base))
                    if os.path.isdir(os.path.join(base, e)) and not os.path.islink(os.path.join(base, e))]
    return out


def _gb(n):
    return "%.2f GB" % (n / 1e9)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    for name in ("source", "bazel", "credential_helper"):
        setattr(args, name, os.path.abspath(getattr(args, name)))
    args.rc = [os.path.abspath(rc) for rc in args.rc]

    os.makedirs(WORK_ROOT, exist_ok=True)
    os.makedirs(REPOSITORY_CACHE, exist_ok=True)
    remove_stale(WORK_ROOT)
    if _du(REPOSITORY_CACHE) > REPOSITORY_CACHE_LIMIT:
        # Nothing evicts from a repository cache; start over when it's big.
        remove_tree(REPOSITORY_CACHE)
        os.makedirs(REPOSITORY_CACHE, exist_ok=True)
    work = tempfile.mkdtemp(prefix=args.project + "-", dir=WORK_ROOT)
    with open(os.path.join(work, "pid"), "w") as f:
        f.write(str(os.getpid()))
    proc = None

    def on_signal(signum, _frame):
        if proc and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(20)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
        remove_tree(work)
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    log = open(args.log, "w") if args.log else sys.stdout
    free_before = shutil.disk_usage(WORK_ROOT).free
    start = time.time()
    try:
        src = args.source_dir = os.path.join(work, "src")
        os.makedirs(src)
        subprocess.run(["tar", "-xf", args.source, "-C", src], check=True)
        version_file = os.path.join(src, ".bazelversion")
        if os.path.exists(version_file):
            with open(version_file) as f:
                upstream = f.read().strip()
            if upstream != args.bazel_version:
                print("note: upstream .bazelversion is %s; using %s" % (upstream, args.bazel_version),
                      file=log, flush=True)
        bep = os.path.join(work, "bep.json")
        env = dict(os.environ)
        # Build actions get an empty environment; cc autoconfiguration
        # needs a PATH to find the compiler.
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        # Integration tests (rules_go's go_bazel_test, ...) run `bazel` from
        # PATH: make that the inner Bazel itself.
        env["PATH"] = bazel_path_dir(args) + os.pathsep + env["PATH"]
        env.setdefault("HOME", work)
        env["TMPDIR"] = os.path.join(work, "tmp")
        os.makedirs(env["TMPDIR"])
        cmd = inner_command(args, os.path.join(work, "out"), bep)
        print("+ " + " ".join(cmd), file=log, flush=True)
        proc = subprocess.Popen(cmd, cwd=src, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            code = proc.wait(args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
            print("inner bazel timed out after %ds" % args.timeout, file=log, flush=True)
        try:
            with open(bep) as f:
                invocation, tests, failed_builds = load_bep(f)
        except OSError:
            invocation, tests, failed_builds = "", {}, []
        stats = [
            ("wall time", "%ds" % (time.time() - start)),
            ("peak RSS of one inner process", _gb(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024)),
            ("work dir size before cleanup", _gb(_du(work))),
        ] + [("  " + rel, _gb(_du(os.path.join(work, rel)))) for rel in _big_dirs(work)]
    finally:
        if args.log:
            log.close()
        remove_tree(work)
    stats.append(("shared repository cache", _gb(_du(REPOSITORY_CACHE))))
    stats.append(("disk free before/after", "%s / %s" % (
        _gb(free_before), _gb(shutil.disk_usage(WORK_ROOT).free))))
    rc_texts = []
    for rc in args.rc:
        with open(rc) as f:
            rc_texts.append(f.read())
    link = results_url(rc_texts) + invocation if invocation else "(none)"
    ok = code in _OK[args.mode]
    summary = summary_text(args.project, args.mode, args.bazel_version, code, link, tests,
                           failed_builds, stats)
    if args.summary:
        with open(args.summary, "w") as f:
            f.write(summary)
    sys.stderr.write(summary)
    if args.mode == "test" and os.environ.get("XML_OUTPUT_FILE"):
        with open(os.environ["XML_OUTPUT_FILE"], "w") as f:
            f.write(test_xml(args.project, tests, failed_builds, link, ok))
    if not ok and args.log:
        with open(args.log) as f:
            sys.stderr.write("".join(f.readlines()[-80:]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
