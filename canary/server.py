#!/usr/bin/env python3
"""RBE image canary: runs the probe and a project subset on BuildBuddy prod
RBE against each configured executor image and arch, one step at a time,
forever, and serves the results on http://0.0.0.0:8000. Python 3 stdlib only.

    python3 canary/server.py [--port 8000] [--data-dir ~/canary-data] [--work-dir ~/canary-work]

Data dir: config.json (hand-edited, re-read each cycle; seeded if missing),
runs.jsonl (one JSON line per step start and end; the last line for a run id
wins) and logs/ (each step's full output). Work dir: a clone of the repo,
reset to origin/<repo_branch> each cycle; per image only the container-image
line of tools/remote.bazelrc is rewritten (uncommitted), and Bazel runs here
(one output base per arch under ~/canary-out) with its actions on RBE, using
$BUILDBUDDY_API_KEY (never written to the runs, logs or UI). See canary/README.md.
"""

import argparse
import datetime
import fcntl
import html
import http.server
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse

REPO_URL = "https://github.com/dan-stowell/bazel-matrix.git"

# Today's images, pinned by digest. The 22.04 one is tools/remote.bazelrc's
# (server_test checks); 24.04 is rbe-ubuntu24-04:latest as of 2026-10-26.
BASELINE_2204 = ("docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:"
                 "0d84a80bb0fc36ba5381942adcf6493249594dcc9044845c617b78c9b621cae3")
BASELINE_2404 = ("docker://gcr.io/flame-public/rbe-ubuntu24-04@sha256:"
                 "f7db0d4791247f032fdb4451b7c3ba90e567923a341cc6dc43abfc283436791a")

# The new images that distrust the eMudhra roots (multi-arch indexes).
CANDIDATE_2204 = ("docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:"
                  "37fb0e3f1af1d95b8f41c2204e2de405e883f484b5e2c6a124e45058431206e7")
CANDIDATE_2404 = ("docker://gcr.io/flame-public/rbe-ubuntu24-04@sha256:"
                  "9b3f4dbfd576b9e80f9915d4377b3435054011c5ac4c0516ffc9749129c5a63c")

# Projects (not known-failing) covering C++, Go/gazelle, Python, Rust, JVM,
# JS and shell/pkg that passed `tools/bb.sh test` on that baseline.
SUBSET_2204 = [
    "zlib", "abseil-cpp", "googletest", "protobuf", "re2", "rules_cc",  # C++
    "gazelle", "rules_go", "buildozer",  # Go, gazelle go_deps
    "rules_python", "aspect_rules_py",  # Python, pip
    "rules_rust",  # Rust, crates
    "rules_kotlin", "rules_scala",  # JVM
    "aspect_rules_js", "rules_nodejs",  # JS, npm
    "rules_shell", "rules_pkg", "bazel_skylib", "rules_img",  # shell, packaging, OCI
]
SUBSET_2404 = []

PROBE = "//canary:tls_probe_test"
PROBE_TARGETS = [PROBE]
ARCHS = ["amd64", "arm64"]
DEFAULT_TIMEOUT = 3 * 3600
PASSING = {"PASSED", "FLAKY"}


def seed_config():
    return {
        "repo_branch": "rbe-image-canary",
        "salt_inner": True,
        "step_timeout_s": DEFAULT_TIMEOUT,
        "cycle_pause_s": 60,
        "bazel": "bazel",
        "output_root": os.path.expanduser("~/canary-out"),
        "min_free_gb": 15,
        "images": [
            {"name": "ubuntu22-04", "ref": BASELINE_2204, "role": "baseline", "release": "22.04"},
            {"name": "ubuntu22-04-candidate", "ref": CANDIDATE_2204, "role": "candidate", "release": "22.04"},
            {"name": "ubuntu24-04", "ref": BASELINE_2404, "role": "baseline", "release": "24.04"},
            {"name": "ubuntu24-04-candidate", "ref": CANDIDATE_2404, "role": "candidate", "release": "24.04"},
        ],
        "subset": {"22.04": list(SUBSET_2204), "24.04": list(SUBSET_2404)},
    }


def load_config(data_dir):
    """The config, written from seed_config() first if missing."""
    path = os.path.join(data_dir, "config.json")
    if not os.path.exists(path):
        os.makedirs(data_dir, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(seed_config(), f, indent=2)
            f.write("\n")
        os.replace(path + ".tmp", path)
    with open(path) as f:
        cfg = json.load(f)
    for k, v in seed_config().items():
        if k not in ("images", "subset"):
            cfg.setdefault(k, v)
    cfg.setdefault("images", [])
    cfg.setdefault("subset", {})
    return cfg


def ordered_images(images):
    """By release, baseline first, then config order."""
    idx = {id(im): i for i, im in enumerate(images)}
    return sorted(images, key=lambda im: (im.get("release", ""), im.get("role") != "baseline", idx[id(im)]))


def columns(images):
    """One image dict per (image, arch), its `archs` (default both), with `arch` set."""
    return [dict(im, arch=a) for im in ordered_images(images) for a in im.get("archs", ARCHS)]


def arch_of(image):
    return image.get("arch", "amd64")


def subset_of(cfg, image):
    """The image's subset: cfg["subset"]["<release>"] on amd64,
    ["<release>/<arch>"] on another arch; None when there is none."""
    rel, arch = image.get("release"), arch_of(image)
    return cfg["subset"].get(rel if arch == "amd64" else "%s/%s" % (rel, arch)) or None


def schedule(cfg):
    """[(column, step)] for a cycle: candidates' probes first (fast), then
    baselines' probes, then the subsets of the columns that have one."""
    cols = columns(cfg["images"])
    probes = [c for c in cols if c.get("role") == "candidate"] + [c for c in cols if c.get("role") != "candidate"]
    return [(c, "probe") for c in probes] + [(c, "subset") for c in cols if subset_of(cfg, c)]


# --- tools/remote.bazelrc ---------------------------------------------------

_IMAGE = re.compile(r"(--remote_default_exec_properties=container-image=)(\S+)")


def rewrite_image(text, ref):
    """remote.bazelrc text with its one container-image value set to ref."""
    if not re.fullmatch(r"docker://\S+@sha256:[0-9a-f]{64}", ref):
        raise ValueError("image ref must be docker://...@sha256:<digest>: %r" % ref)
    new, n = _IMAGE.subn(lambda m: m.group(1) + ref, text)
    if n != 1:
        raise ValueError("expected one container-image line in remote.bazelrc, found %d" % n)
    return new


# --- output parsing -----------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[\d+(?:;\d+)*m")
_STREAM = re.compile(r"Streaming (?:remote runner logs|build results) to: "
                     r"(https://(?:app|buildbuddy)\.buildbuddy\.io/invocation/[0-9a-f-]+)")
_RESULT = re.compile(r"^((?://|@)\S*:\S+)\s+(?:\(cached\)\s+)?"
                     r"(PASSED|FAILED TO BUILD|FAILED|TIMEOUT|FLAKY|NO STATUS|INCOMPLETE|"
                     r"REMOTE FAILURE|SKIPPED)\b")
_END = re.compile(r"^Executed \d+ out of \d+ tests?\b")
_SUMMARY = re.compile(r"^(\s|$|//|@|Target //|INFO: (Elapsed time|\d+ processes|Build completed)|"
                      r"ERROR: Build did NOT|FAILED: Build did NOT|Use --verbose_failures )")


def clean_lines(text):
    return [l.rstrip() for l in _ANSI.sub("", text).splitlines()]


def invocation_links(text):
    """Every distinct invocation link printed, in order."""
    out = []
    for l in clean_lines(text):
        m = _STREAM.search(l)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def target_results(text):
    """{label: status} from the outer Bazel's final test summary only (a
    failing test's log may contain inner result lines of its own)."""
    lines = clean_lines(text)
    ends = [i for i, l in enumerate(lines) if _END.match(l)]
    if not ends:
        return {}
    end = ends[-1]
    start = end
    while start > 0 and _SUMMARY.match(lines[start - 1]):
        start -= 1
    out = {}
    for l in lines[start:end]:
        m = _RESULT.match(l)
        if m:
            out[m.group(1)] = m.group(2)
    return out


_TEST_OUTPUT = re.compile(r"^=+ Test output for (\S+):")
_PROBE_SUMMARY = re.compile(r"^=== tls_probe summary\b")
_PROBE_FAIL = re.compile(r"^\s+(FAIL|NETERR)\s+(\S+): (.*)$")


def probe_failures(text):
    """{probe target: [(status, check, message)]} from each tls_probe
    summary block (needs --test_output=all for passing targets' output)."""
    out, target, in_summary = {}, None, False
    for l in clean_lines(text):
        m = _TEST_OUTPUT.match(l)
        if m:
            target, in_summary = m.group(1), False
            out.setdefault(target, [])
            continue
        if _PROBE_SUMMARY.match(l):
            in_summary = target is not None
            if in_summary:
                out[target] = []  # a retried test prints it again
            continue
        if in_summary:
            m = _PROBE_FAIL.match(l)
            if m:
                out[target].append((m.group(1), m.group(2), m.group(3)))
            elif not l.startswith(" "):
                in_summary = False
    return {t: f for t, f in out.items() if t in PROBE_TARGETS}


_CHECK = re.compile(r"^(PASS|FAIL|NETERR|INFO|SKIP)\s+(\S+): (.*)$")


def probe_checks(text):
    """{check: [status, message]} from the probe's output (its check lines,
    not the indented summary), for the last run of PROBE in the log."""
    out, target = {}, None
    for l in clean_lines(text):
        m = _TEST_OUTPUT.match(l)
        if m:
            target = m.group(1)
            if target == PROBE:
                out = {}
            continue
        m = _CHECK.match(l)
        if m and target == PROBE:
            out[m.group(2)] = [m.group(1), m.group(3)]
    return out


def is_emudhra(check):
    return check.split("/")[0].startswith("emudhra")


def summarize_failures(failures, width=70):
    """Short lines for a cell: checks grouped by their first path part, e.g.
    "emudhra_online x3: verified, TLSv1.3"; the message is its last part."""
    groups = {}
    for status, check, msg in failures:
        groups.setdefault(check.split("/")[0], []).append((status, check, msg))
    lines = []
    for top, items in groups.items():
        status, check, msg = items[0]
        short = msg.rsplit(": ", 1)[-1]
        if len(short) > width:
            short = short[:width - 3] + "..."
        name = check if len(items) == 1 else "%s x%d" % (top, len(items))
        lines.append("%s%s: %s" % ("" if status == "FAIL" else status + " ", name, short))
    return lines


def classify(code):
    """passed | failed | error from Bazel's exit code: 1 is a build failure,
    3 failed tests; anything else (2 bad flags, 4 no tests, 8 interrupted,
    3x infrastructure, ...) means the run itself went wrong."""
    if code == 0:
        return "passed"
    return "failed" if code in (1, 3) else "error"


def redact(text, secret):
    return text.replace(secret, "<REDACTED>") if secret else text


# --- regressions ------------------------------------------------------------

def latest(runs):
    """{(image name, ref, arch, step): the newest finished run}."""
    out = {}
    for r in runs:
        if r.get("status") in ("running", "interrupted", "skipped"):
            continue
        key = (r["image"]["name"], r["image"]["ref"], arch_of(r["image"]), r["step"])
        if key not in out or r["start"] >= out[key]["start"]:
            out[key] = r
    return out


def cell_status(lat, image, step, target=None):
    r = lat.get((image["name"], image["ref"], arch_of(image), step))
    if r is None:
        return None, None
    if target is None:
        return r["status"], r
    return r.get("targets", {}).get(target), r


def is_pass(status):
    return status in PASSING or status == "passed"


def regressions(images, lat, rows):
    """{(candidate name, arch, row)}: subset rows (step, target or None) a
    candidate column fails while a baseline of its release and arch passes them.
    images are columns (see columns())."""
    out = set()
    for c in images:
        if c.get("role") != "candidate":
            continue
        bases = [b for b in images if b.get("role") == "baseline" and b.get("release") == c.get("release")
                 and arch_of(b) == arch_of(c)]
        for row in rows:
            if row[0] == "probe":
                continue  # probe checks count in verdicts(), eMudhra ones under Rejects only
            st, _ = cell_status(lat, c, *row)
            if st is None or is_pass(st):
                continue
            if any(is_pass(cell_status(lat, b, *row)[0]) for b in bases):
                out.add((c["name"], arch_of(c), row))
    return out


def verdicts(cfg, images, lat, col):
    """(rejects, works) for a column, each (state, [reasons]) with state
    yes | no | pending | baseline.

    rejects: the probe's emudhra* checks all pass (a candidate runs them with
    CANARY_EXPECT=distrusted, so passing means it rejects eMudhra). works: the
    probe's other checks pass and the subset has no target that fails while
    a baseline of the same release and arch passes it.
    """
    _, probe = cell_status(lat, col, "probe")
    checks = (probe or {}).get("probe_checks") or {}
    if probe is not None and probe["status"] not in ("passed", "failed"):
        checks = {}  # an interrupted or broken probe proves nothing
    fails = lambda keep: ["%s: %s" % (c, m) for c, (st, m) in sorted(checks.items()) if keep(c) and st == "FAIL"]
    unsure = lambda keep: ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(checks.items())
                           if keep(c) and st not in ("PASS", "FAIL", "INFO")]
    em_checks = [c for c in checks if is_emudhra(c)]
    if probe is None or not em_checks:
        rejects = ("pending", ["no probe result yet"] if probe is None else
                   ["probe %s, no eMudhra checks parsed" % probe["status"]])
    else:
        em = fails(is_emudhra)
        if col.get("role") == "baseline":
            rejects = ("baseline", em or ["trusts eMudhra (expected)"])
        elif em:
            rejects = ("no", em)
        else:
            rejects = ("pending", unsure(is_emudhra)) if unsure(is_emudhra) else ("yes", [])
    other = lambda c: not is_emudhra(c)
    reasons = fails(other) if checks else []
    if not checks:
        state = "pending"
        reasons = ["no probe result yet"] if probe is None else ["probe %s, no checks parsed" % probe["status"]]
    elif reasons:
        state = "no"
    elif unsure(other):
        state, reasons = "pending", unsure(other)
    else:
        state = "yes"
    if subset_of(cfg, col):
        _, sub = cell_status(lat, col, "subset")
        if sub is None:
            state = "no" if state == "no" else "pending"
            reasons = reasons + ["subset not run yet"]
        elif col.get("role") == "baseline":
            bad = sorted(t for t, st in sub.get("targets", {}).items() if not is_pass(st))
            if sub["status"] != "passed":
                state = "no"
                reasons = reasons + (["fails %s" % ", ".join(bad)] if bad else ["subset %s" % sub["status"]])
        else:
            bases = [b for b in images if b.get("role") == "baseline" and b.get("release") == col.get("release")
                     and arch_of(b) == arch_of(col)]
            regs, unknown = [], []
            for t, st in sorted(sub.get("targets", {}).items()):
                if is_pass(st):
                    continue
                base = [cell_status(lat, b, "subset", t)[0] for b in bases]
                if any(is_pass(x) for x in base):
                    regs.append(t)
                elif not any(base):
                    unknown.append(t)
            if regs:
                state = "no"
                reasons = reasons + ["regresses %s" % ", ".join(regs)]
            elif sub["status"] != "passed" and not sub.get("targets"):
                # No per-target results (e.g. the build failed first): a
                # regression if a baseline's subset passed.
                if any(cell_status(lat, b, "subset")[0] == "passed" for b in bases):
                    state = "no"
                    reasons = reasons + ["subset %s (baseline passed)" % sub["status"]]
                elif state == "yes":
                    state = "pending"
                    reasons = reasons + ["subset %s" % sub["status"]]
            elif unknown and state == "yes":
                state = "pending"
                reasons = reasons + ["no baseline result for %s" % ", ".join(unknown)]
            elif sub["status"] in ("error", "timeout") and state == "yes":
                state = "pending"
                reasons = reasons + ["subset %s" % sub["status"]]
    return rejects, (state, reasons)


# --- run store --------------------------------------------------------------

class Store:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "runs.jsonl")
        self.logs = os.path.join(data_dir, "logs")
        os.makedirs(self.logs, exist_ok=True)
        self.lock = threading.Lock()

    def append(self, rec):
        with self.lock, open(self.path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    def runs(self):
        """Every run, last record per id, in start order."""
        by_id = {}
        try:
            with open(self.path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    by_id[rec["id"]] = rec
        except FileNotFoundError:
            pass
        return sorted(by_id.values(), key=lambda r: (r["start"], r["id"]))

    def mark_interrupted(self):
        for r in self.runs():
            if r["status"] == "running":
                r.update(status="interrupted", end=r.get("end") or now())
                self.append(r)

    def backfill_checks(self):
        """Adds probe check summaries to finished probe runs recorded without them."""
        for r in self.runs():
            path = os.path.join(self.logs, r["log"])
            if (r["step"] == "probe" and "probe_checks" not in r and r["status"] != "running"
                    and os.path.exists(path)):
                with open(path, errors="replace") as f:
                    text = f.read()
                r["checks"] = {t: summarize_failures(x) for t, x in probe_failures(text).items()}
                r["probe_checks"] = probe_checks(text)
                self.append(r)

    def next_cycle(self):
        return max([r["cycle"] for r in self.runs()] or [0]) + 1


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# --- runner -----------------------------------------------------------------

class Runner(threading.Thread):
    def __init__(self, data_dir, work_dir, store):
        super().__init__(daemon=True)
        self.data_dir, self.work, self.store = data_dir, work_dir, store
        self.current = None  # the running step's record
        self.proc = None
        self.stopping = threading.Event()
        self.lock = threading.Lock()  # one step at a time in the work dir

    def git(self, *args):
        subprocess.run(["git", "-C", self.work] + list(args), check=True, timeout=600,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def prepare(self, branch):
        if not os.path.isdir(os.path.join(self.work, ".git")):
            subprocess.run(["git", "clone", "--quiet", REPO_URL, self.work], check=True, timeout=600,
                           stdin=subprocess.DEVNULL)
        self.git("fetch", "--quiet", "origin", branch)
        self.git("reset", "--quiet", "--hard", "FETCH_HEAD")
        self.git("clean", "-fdq")

    def run(self):
        while not self.stopping.is_set():
            try:
                self.cycle()
            except Exception as e:  # keep looping; record it
                rec = self.new_record(self.store.next_cycle(), {"name": "-", "ref": "-"}, "prepare")
                rec.update(status="error", end=now(), error="%s: %s" % (type(e).__name__, e))
                self.store.append(rec)
                self.stopping.wait(60)

    def cycle(self):
        cfg = load_config(self.data_dir)
        cycle = self.store.next_cycle()
        # Two servers must not share a work dir: hold its lock for the cycle.
        with open(self.work.rstrip("/") + ".lock", "w") as lk:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("another server holds %s.lock" % self.work.rstrip("/"))
            with self.lock:
                self.prepare(cfg["repo_branch"])
            for image, step in schedule(cfg):
                if self.stopping.is_set():
                    return
                self.free_disk(cfg)
                self.step(cfg, cycle, image, step)
        # Not a hot loop when every step is skipped or fails at once.
        self.stopping.wait(cfg.get("cycle_pause_s", 60))

    def new_record(self, cycle, image, step):
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        rid = "%s-c%d-%s-%s-%s" % (stamp, cycle, re.sub(r"[^A-Za-z0-9._-]", "_", image["name"]),
                                   re.sub(r"[^A-Za-z0-9._-]", "_", arch_of(image)), step)
        return {"id": rid, "cycle": cycle, "image": dict(image), "step": step, "start": now(),
                "end": None, "exit_code": None, "status": "running", "invocations": [],
                "targets": {}, "log": rid + ".log", "command": []}

    def output_base(self, cfg, image):
        # One per arch: the Arch flag would otherwise discard the analysis
        # cache at every switch. Steps run one at a time, so never two
        # Bazels on one output base.
        return os.path.join(cfg["output_root"], arch_of(image))

    def free_disk(self, cfg):
        """`bazel clean --expunge` of every output base when disk runs low."""
        root = cfg["output_root"]
        os.makedirs(root, exist_ok=True)
        if shutil.disk_usage(root).free >= cfg.get("min_free_gb", 15) * 2**30:
            return
        for arch in sorted(os.listdir(root)):
            print("low disk: cleaning %s" % os.path.join(root, arch), file=sys.stderr)
            subprocess.run([cfg["bazel"], "--output_base=" + os.path.join(root, arch), "clean", "--expunge"],
                           cwd=self.work, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=1800)

    def command(self, cfg, cycle, image, step, key):
        """The Bazel command line for a step, None if it has nothing to run.

        Bazel runs here, its actions on RBE in the image of the rewritten
        tools/remote.bazelrc. The projects' :test actions are no-remote-exec,
        so their inner Bazels run here too, with their actions on RBE.
        """
        arch = arch_of(image)
        arch_flags = [] if arch == "amd64" else ["--remote_default_exec_properties=Arch=" + arch]
        head = [cfg["bazel"], "--output_base=" + self.output_base(cfg, image), "test"]
        tail = ["--config=remote-minimal", "--remote_header=x-buildbuddy-api-key=" + key,
                "--nocache_test_results"] + arch_flags
        if step == "probe":
            expect = "trusted" if image.get("role") == "baseline" else "distrusted"
            return head + PROBE_TARGETS + tail + ["--test_output=all", "--test_env=CANARY_EXPECT=" + expect]
        subset = subset_of(cfg, image)
        if not subset:
            return None
        args = head + ["//%s:test" % p for p in subset] + tail
        args += ["--//:inner_flags=" + f for f in arch_flags]
        if cfg.get("salt_inner", True):
            args.append("--//:inner_flags=--remote_instance_name=canary-%d" % cycle)
        return args

    def step(self, cfg, cycle, image, step):
        rec = self.new_record(cycle, image, step)
        key = os.environ.get("BUILDBUDDY_API_KEY", "")
        if not key:
            rec.update(status="error", end=now(), error="BUILDBUDDY_API_KEY is not set")
            self.store.append(rec)
            return
        args = self.command(cfg, cycle, image, step, key)
        with self.lock:
            build = os.path.join(self.work, "canary", "BUILD.bazel")
            no_probe = step == "probe" and not (
                os.path.exists(build) and "tls_probe_test" in open(build).read())
            if args is None or no_probe:
                rec.update(status="skipped", end=now(),
                           error="no subset for this release" if args is None else "no //canary probe on this branch")
                self.store.append(rec)
                return
            rc = os.path.join(self.work, "tools", "remote.bazelrc")
            try:
                self.git("checkout", "--", "tools/remote.bazelrc")
                with open(rc) as f:
                    text = rewrite_image(f.read(), image["ref"])
                with open(rc, "w") as f:
                    f.write(text)
            except Exception as e:
                rec.update(status="error", end=now(), error="%s: %s" % (type(e).__name__, e))
                self.store.append(rec)
                return
            rec["command"] = [redact(a, key) for a in args]
            self.current = rec
            self.store.append(rec)
            self.execute(rec, cfg, args, key)
            self.current = None
            self.store.append(rec)

    def execute(self, rec, cfg, args, key):
        log_path = os.path.join(self.store.logs, rec["log"])
        timeout = cfg.get("step_timeout_s", DEFAULT_TIMEOUT)
        timed_out = False
        try:
            with open(log_path, "w") as log:
                self.proc = subprocess.Popen(args, cwd=self.work, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             start_new_session=True)
                # The key never reaches the log file, even mid-run.
                copier = threading.Thread(target=copy_redacted, args=(self.proc.stdout, log, key), daemon=True)
                copier.start()
                deadline = time.time() + timeout
                while self.proc.poll() is None:
                    if self.stopping.is_set() or time.time() > deadline:
                        timed_out = not self.stopping.is_set()
                        kill_group(self.proc)
                        break
                    time.sleep(1)
                code = self.proc.wait()
                copier.join(60)
            with open(log_path, errors="replace") as f:
                text = f.read()
            # Only the requested labels: a failing project's log embeds its
            # inner Bazel's summary, which a killed run may end with.
            wanted = {x for x in args if x.startswith("//")}
            rec.update(exit_code=code, invocations=invocation_links(text),
                       targets={t: st for t, st in target_results(text).items() if t in wanted})
            if rec["step"] == "probe":
                rec["checks"] = {t: summarize_failures(f) for t, f in probe_failures(text).items()}
                rec["probe_checks"] = probe_checks(text)
            if self.stopping.is_set():
                rec["status"] = "interrupted"
            elif timed_out:
                rec["status"] = "timeout"
            else:
                rec["status"] = classify(code)
        except Exception as e:
            rec.update(status="error", error="%s: %s" % (type(e).__name__, e))
        finally:
            self.proc = None
            rec["end"] = now()

    def stop(self):
        self.stopping.set()
        p = self.proc
        if p is not None and p.poll() is None:
            kill_group(p)


def copy_redacted(src, dst, key):
    for line in iter(src.readline, b""):
        dst.write(redact(line.decode("utf-8", "replace"), key))
        dst.flush()
    src.close()


def kill_group(proc, grace=30):
    """SIGINT the process group (the Bazel client cancels the build), then SIGKILL."""
    try:
        os.killpg(proc.pid, signal.SIGINT)
        proc.wait(grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except ProcessLookupError:
        pass


# --- UI ---------------------------------------------------------------------

CSS = """
:root { color-scheme: light dark; --bg:#fff; --fg:#1b1b1b; --mut:#666; --line:#ddd;
  --pass:#d7f5dd; --fail:#fbd5d5; --warn:#fdecc8; --run:#d6e6fb; --none:#f2f2f2; --reg:#c00; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --fg:#e6e6e6; --mut:#999; --line:#333;
  --pass:#1e4d2b; --fail:#5c2020; --warn:#5a4513; --run:#1f3b5e; --none:#24272b; --reg:#ff6b6b; } }
body { background:var(--bg); color:var(--fg); font:14px/1.4 system-ui,sans-serif; margin:16px; }
a { color:inherit; } h1 { font-size:20px; } h2 { font-size:16px; margin-top:24px; }
table { border-collapse:collapse; } td, th { border:1px solid var(--line); padding:3px 6px; text-align:left; vertical-align:top; }
th { font-weight:600; } .mut { color:var(--mut); } .wrap { overflow-x:auto; }
.passed,.PASSED,.FLAKY { background:var(--pass); }
.failed,.FAILED,.TIMEOUT,.timeout,.runner_failed,.error,.FAILED_TO_BUILD,.REMOTE_FAILURE,.INCOMPLETE,.NO_STATUS { background:var(--fail); }
.running { background:var(--run); } .interrupted,.skipped,.UNKNOWN { background:var(--warn); } .none { background:var(--none); }
.emudhra { background:var(--warn); }
.checks { font-size:12px; margin:2px 0 0 0; padding-left:14px; }
.reg { outline:2px solid var(--reg); outline-offset:-2px; font-weight:600; } .reg::after { content:" regression"; color:var(--reg); font-size:11px; }
code { font-size:12px; }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def cls(status):
    return re.sub(r"\W", "_", status or "none")


def elapsed(start, end=None):
    try:
        t0 = datetime.datetime.fromisoformat(start)
        t1 = datetime.datetime.fromisoformat(end) if end else datetime.datetime.now(datetime.timezone.utc)
        s = int((t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return ""
    return "%dh%02dm%02ds" % (s // 3600, s % 3600 // 60, s % 60)


def link(r):
    inv = r.get("invocations") or []
    return " ".join('<a href="%s">%s</a>' % (esc(u), "runner" if "app.buildbuddy" in u else "invocation")
                    for u in inv)


def grid_rows(cfg, runs, images):
    rows = [("probe", None)] + [("probe", t) for t in PROBE_TARGETS] + [("subset", None)]
    targets = []
    for im in images:
        targets += ["//%s:test" % p for p in subset_of(cfg, im) or []]
    for r in runs:
        if r["step"] == "subset":
            targets += list(r.get("targets", {}))
    seen = []
    for t in targets:
        if t not in seen:
            seen.append(t)
    return rows + [("subset", t) for t in sorted(seen)]


def render(cfg, runs, current):
    images = columns(cfg["images"])
    lat = latest(runs)
    rows = grid_rows(cfg, runs, images)
    regs = regressions(images, lat, rows)
    out = ['<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>RBE image canary</title><style>%s</style></head><body>" % CSS,
           "<h1>RBE image canary</h1>"]
    if current:
        out.append('<p class="running">Running: cycle %s, <b>%s</b> (%s, %s, %s) step <b>%s</b>, %s elapsed. '
                   '<a href="/logs/%s?tail=200">log tail</a> &middot; <a href="/logs/%s">full log</a></p>' % (
                       esc(current["cycle"]), esc(current["image"]["name"]), esc(current["image"].get("role")),
                       esc(arch_of(current["image"])),
                       esc(current["image"].get("release")), esc(current["step"]), elapsed(current["start"]),
                       esc(current["log"]), esc(current["log"])))
    else:
        out.append('<p class="mut">Idle (between steps).</p>')
    out.append("<p><b>Rejects eMudhra</b> &ldquo;no&rdquo; on a candidate = the image still trusts eMudhra "
               "(see the emudhra checks). Red <b>Works for customers</b> on a candidate = a regression vs. the "
               "baseline of its release and arch: a non-eMudhra probe check fails, or a project that passes on "
               "the baseline fails. Baselines trust eMudhra by design.</p>")
    cands = [c for c in images if c.get("role") == "candidate"]
    v = [verdicts(cfg, images, lat, c) for c in cands]
    out.append('<p class="mut">Branch %s; inner salt %s. Candidate columns: %d of %d still trust eMudhra, '
               '%d of %d don\'t work for customers.</p>' % (
                   esc(cfg["repo_branch"]), "on" if cfg.get("salt_inner", True) else "off",
                   sum(1 for x in v if x[0][0] == "no"), len(v), sum(1 for x in v if x[1][0] == "no"), len(v)))
    # Grid.
    out.append('<h2>Latest results</h2><div class="wrap"><table><tr><th rowspan="2">step / target</th>')
    releases = []
    for im in images:
        if im.get("release") not in releases:
            releases.append(im.get("release"))
    for rel in releases:
        n = sum(1 for im in images if im.get("release") == rel)
        out.append('<th colspan="%d">Ubuntu %s</th>' % (n, esc(rel)))
    out.append("</tr><tr>")
    for im in images:
        out.append('<th title="%s">%s<br>%s<br><span class="mut">%s &middot; %s</span></th>' % (
            esc(im["ref"]), esc(im["name"]), esc(arch_of(im)), esc(im.get("role")),
            esc(im["ref"].rsplit("@sha256:", 1)[-1][:12])))
    out.append("</tr>")
    for label, idx in (("Rejects eMudhra", 0), ("Works for customers", 1)):
        out.append("<tr><td><b>%s</b></td>" % label)
        for im in images:
            state, reasons = verdicts(cfg, images, lat, im)[idx]
            klass = {"yes": "passed", "no": "failed", "baseline": "none", "pending": "skipped"}[state]
            if idx == 0 and state == "no":
                klass = "emudhra"
            body = "<b>%s</b>" % esc(state)
            if reasons:
                body += '<ul class="checks">%s</ul>' % "".join("<li>%s</li>" % esc(x) for x in reasons)
            if idx == 0:
                _, probe = cell_status(lat, im, "probe")
                diff = ["%s: %s" % (c, m) for c, (st, m) in sorted(((probe or {}).get("probe_checks") or {}).items())
                        if c.startswith("trust_store")]
                if diff:
                    body += "<details><summary>CA store vs baseline</summary><ul class=\"checks\">%s</ul></details>" % (
                        "".join("<li>%s</li>" % esc(d) for d in diff))
            out.append('<td class="%s">%s</td>' % (klass, body))
        out.append("</tr>")
    for row in rows:
        step, target = row
        label = "<b>%s</b>" % step if target is None else "&nbsp;&nbsp;<code>%s</code>" % esc(target)
        out.append("<tr><td>%s</td>" % label)
        for im in images:
            if step == "subset" and not subset_of(cfg, im):
                out.append('<td class="none mut">n/a</td>')
                continue
            st, r = cell_status(lat, im, step, target)
            if r is None or (target is not None and st is None):
                out.append('<td class="none"></td>')
                continue
            reg = " reg" if (im["name"], arch_of(im), row) in regs else ""
            if step == "probe":
                checks = r.get("checks", {})
                fails = checks.get(target, []) if target else [
                    "%s: %d failing check(s)" % (t.split(":")[-1], len(c)) for t, c in sorted(checks.items()) if c]
            else:
                fails = []
            detail = '<ul class="checks">%s</ul>' % "".join("<li>%s</li>" % esc(f) for f in fails) if fails else ""
            klass = cls(st)
            pc = r.get("probe_checks") or {}
            failing = [c for c, (x, _) in pc.items() if x == "FAIL"]
            if step == "probe" and not is_pass(st) and failing and all(is_emudhra(c) for c in failing):
                klass = "emudhra"  # only eMudhra checks fail: see Rejects eMudhra
            out.append('<td class="%s%s" title="cycle %s, %s">%s %s <a href="/logs/%s">log</a>%s</td>' % (
                klass, reg, esc(r["cycle"]), esc(r["end"]), esc(st), link(r), esc(r["log"]), detail))
        out.append("</tr>")
    out.append("</table></div>")
    # History.
    out.append("<h2>Recent runs</h2><div class=\"wrap\"><table><tr><th>cycle</th><th>image</th><th>step</th>"
               "<th>start</th><th>took</th><th>status</th><th>exit</th><th>targets</th><th>links</th></tr>")
    for r in list(reversed(runs))[:100]:
        tg = r.get("targets", {})
        bad = sum(1 for s in tg.values() if not is_pass(s))
        out.append('<tr><td>%s</td><td>%s <span class="mut">%s %s %s</span></td><td>%s</td><td>%s</td><td>%s</td>'
                   '<td class="%s">%s%s</td><td>%s</td><td>%s</td><td>%s <a href="/logs/%s">log</a></td></tr>' % (
                       esc(r["cycle"]), esc(r["image"]["name"]), esc(r["image"].get("role", "")),
                       esc(r["image"].get("release", "")), esc(arch_of(r["image"])), esc(r["step"]), esc(r["start"]),
                       elapsed(r["start"], r.get("end")), cls(r["status"]), esc(r["status"]),
                       (' <span class="mut">%s</span>' % esc(r["error"])) if r.get("error") else "",
                       esc(r.get("exit_code")), "%d/%d failing" % (bad, len(tg)) if tg else "",
                       link(r), esc(r["log"])))
    out.append("</table></div></body></html>")
    return "".join(out)


_LOG_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def make_handler(data_dir, store, runner):
    class Handler(http.server.BaseHTTPRequestHandler):
        def send(self, code, body, ctype):
            data = body.encode("utf-8", "replace")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(url.path)
            q = urllib.parse.parse_qs(url.query)
            try:
                if path == "/":
                    cfg = load_config(data_dir)
                    self.send(200, render(cfg, store.runs(), runner.current if runner else None), "text/html")
                elif path == "/api/runs":
                    self.send(200, json.dumps(store.runs(), indent=1), "application/json")
                elif path.startswith("/logs/"):
                    name = path[len("/logs/"):]
                    full = os.path.join(store.logs, name)
                    if not _LOG_NAME.match(name) or not os.path.isfile(full):
                        return self.send(404, "not found\n", "text/plain")
                    with open(full, errors="replace") as f:
                        text = redact(f.read(), os.environ.get("BUILDBUDDY_API_KEY", ""))
                    if "tail" in q:
                        n = int(q["tail"][0])
                        text = "\n".join(text.splitlines()[-n:]) + "\n"
                    self.send(200, text, "text/plain")
                else:
                    self.send(404, "not found\n", "text/plain")
            except Exception as e:
                self.send(500, "%s: %s\n" % (type(e).__name__, e), "text/plain")

        def log_message(self, *args):
            pass

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--data-dir", default=os.path.expanduser("~/canary-data"))
    ap.add_argument("--work-dir", default=os.path.expanduser("~/canary-work"))
    args = ap.parse_args(argv)
    load_config(args.data_dir)
    store = Store(args.data_dir)
    store.mark_interrupted()
    store.backfill_checks()
    runner = Runner(args.data_dir, args.work_dir, store)
    server = http.server.ThreadingHTTPServer((args.host, args.port), make_handler(args.data_dir, store, runner))

    def shutdown(signum, _frame):
        runner.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    runner.start()
    print("serving on http://%s:%d" % (args.host, args.port), file=sys.stderr)
    server.serve_forever()
    runner.join(60)  # lets the running step record its end
    server.server_close()


if __name__ == "__main__":
    main()
