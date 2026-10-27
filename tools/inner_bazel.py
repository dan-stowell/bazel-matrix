#!/usr/bin/env python3
"""Runs one project's inner `bazel build` or `bazel test`.

Called by the targets tools/project.bzl declares. It extracts the project's
source.tar into a fresh work dir, runs the pinned inner Bazel there in
--batch mode with its own output user root and a minimal, explicit
environment, and deletes the work dir afterwards (also on SIGTERM, and stale
ones left by killed runs), so a runner's disk doesn't grow per run. Fetches
go through BuildBuddy's remote downloader and remote repo contents cache;
nothing is cached on the runner between runs but one install base per inner
Bazel binary (INSTALL_ROOT).

build mode writes --summary (invocation link and counts) and --log (the
inner output). test mode streams the inner output to the test log and writes
$XML_OUTPUT_FILE with one testcase per inner test target (per configuration),
one per non-test target that failed to build, and an `invocation` failure
when the inner Bazel failed for a reason no target explains.

Exit status: 0 when the inner Bazel succeeded (for test, also when it found
no tests), else 1.
"""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

# Not under /tmp: Bazel 9's hermetic /tmp (no longer optional) mounts a
# tmpfs there in locally sandboxed actions, which then can't run below an
# output base in /tmp.
WORK_ROOT = "/var/tmp/bazel-matrix/work"
# Install bases (Bazel's extracted binaries and embedded JDK, ~120 MB), one
# per inner Bazel binary, shared by every run of it on this machine instead
# of extracted afresh into each work dir. The client extracts into a temp
# dir and renames it into place, so concurrent first runs are safe. Bounded:
# one per pinned binary, never written to after extraction.
INSTALL_ROOT = "/var/tmp/bazel-matrix/install"
# Where tools/credentials.bzl writes the API key, relative to the outer
# output base.
KEY_FILE = "bazel-matrix/api-key"
RESULTS_URL = "https://buildbuddy.buildbuddy.io/invocation/"
# Keep the inner JVM within the resources:memory reservation in project.bzl.
JVM_HEAP = "-Xmx2g"
# Seconds between SIGTERM and SIGKILL for the inner Bazel; well below
# Bazel's default --local_termination_grace_seconds (15).
KILL_GRACE = 5

# Inner exit codes that count as success: 4 is "no test targets found".
_OK = {"build": {0}, "test": {0, 4}}
# Inner `bazel test` exit code when //... (minus exclusions) has no tests:
# reported as NO_TESTS, but not a failure.
NO_TESTS = 4
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


def install_base(bazel):
    """The shared install base of the Bazel binary at path bazel: keyed by
    its content, so a changed binary never reuses another's."""
    h = hashlib.sha256()
    with open(bazel, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return os.path.join(INSTALL_ROOT, h.hexdigest()[:32])


def inner_command(args, out_root, bep, install):
    """The inner Bazel command line."""
    startup = [
        "--batch",
        "--nosystem_rc",
        "--nohome_rc",
        "--output_user_root=" + out_root,
        "--install_base=" + install,
        "--host_jvm_args=" + JVM_HEAP,
    ] + ["--bazelrc=" + rc for rc in args.rc] + args.startup_flag
    flags = [
        "--credential_helper=*.buildbuddy.io=" + args.credential_helper,
        "--build_event_json_file=" + bep,
        "--build_metadata=PROJECT=" + args.project,
        # BuildBuddy's tag filter finds every inner run, or one project's.
        "--build_metadata=TAGS=bazel-matrix," + args.project,
    ]
    if args.mode == "test":
        flags.append("--test_output=errors")
    return [args.bazel] + startup + [args.mode] + flags + args.flag + ["--"] + args.target


def inner_env(work, bin_dir, key_file):
    """The inner Bazel's whole environment, the same in build and test mode."""
    return {
        # Integration tests (rules_go's go_bazel_test, ...) run `bazel` from
        # PATH: bin_dir makes that the inner Bazel itself.
        "PATH": bin_dir + ":/usr/local/bin:/usr/bin:/bin",
        "HOME": os.path.join(work, "home"),
        "TMPDIR": os.path.join(work, "tmp"),
        "LANG": "C.UTF-8",
        "BAZEL_MATRIX_KEY_FILE": key_file,
    }


def _config(eid_part):
    return eid_part.get("configuration", {}).get("id", "")


def load_bep(lines):
    """Per-target results from inner BEP JSON lines; bad lines are skipped.

    Returns (invocation_id, tests, failed_builds): tests maps each
    (test label, configuration) to (status, millis); failed_builds lists the
    non-test targets that failed.
    """
    invocation = ""
    test_labels, summaries, completed, aborted = set(), {}, {}, {}
    for line in lines:
        try:
            event = json.loads(line)
            eid = event["id"]
        except (ValueError, KeyError, TypeError):
            continue  # blank, or truncated by a killed Bazel
        if "started" in eid:
            invocation = event.get("started", {}).get("uuid", "")
        if "targetConfigured" in eid:
            label = eid["targetConfigured"].get("label", "")
            if "aborted" in event:
                aborted[label] = event["aborted"].get("reason", "UNKNOWN")
            elif "testSize" in event.get("configured", {}):
                test_labels.add(label)
        if "testSummary" in eid:
            s = event.get("testSummary", {})
            key = (eid["testSummary"].get("label", ""), _config(eid["testSummary"]))
            summaries[key] = (s.get("overallStatus", "NO_STATUS"),
                              int(s.get("totalRunDurationMillis", 0)))
        if "targetCompleted" in eid:
            key = (eid["targetCompleted"].get("label", ""), _config(eid["targetCompleted"]))
            if "aborted" in event:
                aborted[key[0]] = event["aborted"].get("reason", "UNKNOWN")
            else:
                completed[key] = event.get("completed", {}).get("success", False)
    tests = dict(summaries)
    for key, ok in completed.items():
        if key[0] in test_labels and key not in tests:
            # Built (or not), never run.
            tests[key] = ("BUILT" if ok else "FAILED_TO_BUILD", 0)
    seen = {label for label, _ in tests}
    for label in test_labels - seen:
        tests[(label, "")] = ("SKIPPED" if aborted.get(label) == "SKIPPED" else "FAILED_TO_BUILD", 0)
    failed_builds = sorted(
        ({l for (l, _), ok in completed.items() if not ok} |
         {l for l, r in aborted.items() if r != "SKIPPED"})
        - test_labels)
    return invocation, tests, failed_builds


def _case_names(tests):
    """Testcase names: the label, plus the configuration if it has several."""
    count = {}
    for label, _ in tests:
        count[label] = count.get(label, 0) + 1
    return {(l, c): l if count[l] == 1 else "%s [%s]" % (l, c[:12]) for l, c in tests}


def test_xml(project, tests, failed_builds, link, ok=True, no_tests=False):
    """A JUnit XML document: one testcase per inner test target.

    no_tests (the inner Bazel found no test targets) adds a skipped
    `no tests` testcase with message NO_TESTS.
    """
    suite = ET.Element("testsuite", name=project)
    failures = skipped = 0
    names = _case_names(tests)
    for key in sorted(tests):
        status, millis = tests[key]
        case = ET.SubElement(suite, "testcase", name=names[key], classname=project,
                             time="%.3f" % (millis / 1000.0))
        if status in ("SKIPPED", "BUILT"):
            # BUILT: built but not run, e.g. a test_suite member under an
            # excluded pattern.
            skipped += 1
            ET.SubElement(case, "skipped", message=status)
        elif status not in _PASSING:
            failures += 1
            ET.SubElement(case, "failure", message=status).text = "%s %s; see %s" % (
                names[key], status, link)
    for label in failed_builds:
        failures += 1
        case = ET.SubElement(suite, "testcase", name=label, classname=project + ".build")
        ET.SubElement(case, "failure", message="FAILED_TO_BUILD").text = "see " + link
    count = len(tests) + len(failed_builds)
    if no_tests and not tests:
        skipped += 1
        count += 1
        case = ET.SubElement(suite, "testcase", name="no tests", classname=project)
        ET.SubElement(case, "skipped", message="NO_TESTS")
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


def summary_text(project, mode, version, code, link, tests, failed_builds, wall):
    counts = {}
    for status, _ in tests.values():
        counts[status] = counts.get(status, 0) + 1
    lines = [
        "project: " + project,
        "command: " + mode,
        "inner bazel: " + version,
        "exit code: %d" % code,
        "inner invocation: " + link,
        "tests: " + (", ".join("%s %d" % kv for kv in sorted(counts.items())) or
                     ("NO_TESTS (no test targets)" if mode == "test" and code == NO_TESTS else "none")),
        "failed to build: %d" % len(failed_builds),
    ] + ["  " + l for l in failed_builds] + ["wall time: %ds" % wall]
    return "\n".join(lines) + "\n"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def remove_tree(path):
    # Bazel makes parts of its output and install bases read-only.
    subprocess.run(["chmod", "-R", "u+rwx", path], stderr=subprocess.DEVNULL)
    shutil.rmtree(path, ignore_errors=True)


def remove_stale(root):
    """Removes work dirs left by killed runs: their pid file names a dead pid.

    A dir with no pid file yet is only removed once it's 10 minutes old, and
    a dir that disappears meanwhile (another run cleaning up) is fine.
    """
    try:
        entries = os.listdir(root)
    except FileNotFoundError:
        return
    for d in entries:
        path = os.path.join(root, d)
        try:
            with open(os.path.join(path, "pid")) as f:
                pid = int(f.read())
        except (OSError, ValueError):
            try:
                if time.time() - os.path.getmtime(path) < 600:
                    continue
            except OSError:
                continue
            pid = 0
        if not pid or not _alive(pid):
            remove_tree(path)


def read_bazelversion(path):
    """The version in a .bazelversion file, read as bazelisk does: its first
    line that is neither empty nor a `#` comment, or None."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    return None


def output_base(cwd):
    """The outer output base: the parent of the `execroot` above cwd.

    Build actions run in <output base>/execroot/_main, tests in a runfiles
    tree below it (both unsandboxed).
    """
    path = os.path.realpath(cwd)
    while path != "/":
        if os.path.basename(path) == "execroot":
            return os.path.dirname(path)
        path = os.path.dirname(path)
    raise RuntimeError("not under an outer execroot: " + cwd)


def _killpg(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def wait_exit(proc, timeout):
    """Waits up to timeout seconds for proc to exit, without reaping it.

    An unreaped leader keeps its process group ID from being reused, so
    signalling the group stays safe until kill() reaps it.
    """
    deadline = time.time() + timeout
    while True:
        if proc.returncode is not None or os.waitid(
                os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.2)


def kill(proc):
    """Stops the inner Bazel's whole process group, then reaps the leader.

    SIGTERM first; after KILL_GRACE seconds (or as soon as the leader is
    gone), SIGKILL whatever is left in the group. A leader already reaped is
    never signalled: its group ID may belong to someone else by now.
    """
    if proc is None or proc.returncode is not None:
        return
    _killpg(proc.pid, signal.SIGTERM)
    wait_exit(proc, KILL_GRACE)
    _killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    for name in ("source", "bazel", "credential_helper"):
        setattr(args, name, os.path.abspath(getattr(args, name)))
    args.rc = [os.path.abspath(rc) for rc in args.rc]
    if args.mode == "test" and os.environ.get("TEST_TIMEOUT"):
        # Finish (and clean up) before the outer test times out.
        args.timeout = min(args.timeout, int(os.environ["TEST_TIMEOUT"]) - 60)
    key_file = os.path.join(output_base(os.getcwd()), KEY_FILE)

    os.makedirs(WORK_ROOT, exist_ok=True)
    remove_stale(WORK_ROOT)
    work = tempfile.mkdtemp(prefix=args.project + "-", dir=WORK_ROOT)
    with open(os.path.join(work, "pid"), "w") as f:
        f.write(str(os.getpid()))
    state = {"proc": None}

    def on_signal(signum, _frame):
        kill(state["proc"])
        remove_tree(work)
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    log = open(args.log, "w") if args.log else sys.stdout
    start = time.time()
    code, invocation, tests, failed_builds = 1, "", {}, []
    try:
        src = os.path.join(work, "src")
        bin_dir = os.path.join(work, "bin")
        env = inner_env(work, bin_dir, key_file)
        for d in (src, bin_dir, env["HOME"], env["TMPDIR"]):
            os.makedirs(d)
        os.symlink(args.bazel, os.path.join(bin_dir, "bazel"))
        subprocess.run(["tar", "-xf", args.source, "-C", src], check=True)
        version_file = os.path.join(src, ".bazelversion")
        if os.path.exists(version_file):
            upstream = read_bazelversion(version_file)
            if upstream and upstream != args.bazel_version:
                print("note: upstream .bazelversion is %s; using %s" % (upstream, args.bazel_version),
                      file=log, flush=True)
        bep = os.path.join(work, "bep.json")
        cmd = inner_command(args, os.path.join(work, "out"), bep, install_base(args.bazel))
        print("+ " + " ".join(cmd), file=log, flush=True)
        state["proc"] = subprocess.Popen(cmd, cwd=src, env=env, stdout=log,
                                         stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = not wait_exit(state["proc"], args.timeout)
        # Also on success: nothing of the inner Bazel may outlive it.
        kill(state["proc"])
        code = 1 if timed_out else state["proc"].returncode
        state["proc"] = None
        if timed_out:
            print("inner bazel timed out after %ds" % args.timeout, file=log, flush=True)
        try:
            with open(bep, errors="replace") as f:
                invocation, tests, failed_builds = load_bep(f)
        except OSError:
            pass
    finally:
        if args.log:
            log.close()
        remove_tree(work)
    ok = code in _OK[args.mode]
    link = RESULTS_URL + invocation if invocation else "(none)"
    summary = summary_text(args.project, args.mode, args.bazel_version, code, link, tests,
                           failed_builds, time.time() - start)
    if args.summary:
        with open(args.summary, "w") as f:
            f.write(summary)
    sys.stderr.write(summary)
    if args.mode == "test" and os.environ.get("XML_OUTPUT_FILE"):
        with open(os.environ["XML_OUTPUT_FILE"], "w") as f:
            f.write(test_xml(args.project, tests, failed_builds, link, ok, code == NO_TESTS))
    if not ok and args.log:
        with open(args.log) as f:
            sys.stderr.write("".join(f.readlines()[-80:]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
