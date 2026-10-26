#!/usr/bin/env python3
"""RBE image canary: answers, for each candidate image and arch, "is it
protected from the eMudhra compromise?" and "do popular rulesets still build
on it?", by running the TLS probe and a ruleset subset on BuildBuddy prod RBE
against it and its baseline, one step at a time, forever. Serves the answers
on http://0.0.0.0:8000. Python 3 stdlib only.

    python3 canary/server.py [--port 8000] [--data-dir ~/canary-data] [--work-dir ~/canary-work]

Data dir: config.json (hand-edited, re-read each cycle; seeded if missing),
runs.jsonl (a JSON line per step start and end; the last line per run id
wins; compacted to the newest MAX_RUNS runs) and logs/ (each step's output,
kept LOG_DAYS days). Work dir: a clone of the repo, reset to
origin/<repo_branch> each cycle; per image only the container-image line of
tools/remote.bazelrc is rewritten (uncommitted), and Bazel runs here (one
output base per arch under ~/canary-out) with its actions on RBE. The API key
($BUILDBUDDY_API_KEY) reaches Bazel through tools/buildbuddy_credential_helper.py
and a 0600 key file, never argv, the runs, the logs or the page. See
canary/README.md.
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

# Today's images, pinned by digest (multi-arch indexes). The 22.04 one is
# tools/remote.bazelrc's (server_test checks); 24.04 is rbe-ubuntu24-04:latest
# as of 2026-10-26.
BASELINE_2204 = ("docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:"
                 "0d84a80bb0fc36ba5381942adcf6493249594dcc9044845c617b78c9b621cae3")
BASELINE_2404 = ("docker://gcr.io/flame-public/rbe-ubuntu24-04@sha256:"
                 "f7db0d4791247f032fdb4451b7c3ba90e567923a341cc6dc43abfc283436791a")
# The 2026-10-26.1 images that distrust the eMudhra roots.
CANDIDATE_2204 = ("docker://gcr.io/flame-public/rbe-ubuntu22-04@sha256:"
                  "c3ea6288672add20a50fafbbeba27752731b24fe6cd4d20bac6c755a0619cc80")
CANDIDATE_2404 = ("docker://gcr.io/flame-public/rbe-ubuntu24-04@sha256:"
                  "be9853fc45092d2cf2bda3abed30d22182881659a50bf35c7125161d7cfc8a75")

# Popular rulesets, as projects of projects.txt, that pass on the baseline of
# that release and arch with Bazel on this machine (see README.md, "The
# subset"). Keys: "<release>" for amd64, "<release>/<arch>" otherwise; a
# column without one is "not covered".
SUBSETS = {}
# Rulesets left out, and why (shown on the page).
SUBSET_NOTES = []

PROBE = "//canary:tls_probe_test"
ARCHS = ["amd64", "arm64"]
DEFAULT_TIMEOUT = 3 * 3600
PASSING = {"PASSED", "FLAKY"}
MAX_RUNS = 200
LOG_DAYS = 3
WORK_ROOT = "/var/tmp/bazel-matrix/work"  # tools/inner_bazel.py's
COMPLETE = ("passed", "failed")  # statuses of a run that ran to the end


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
        "subset": {k: list(v) for k, v in SUBSETS.items()},
    }


def load_config(data_dir):
    """The config (seeded first if missing), with defaults for missing keys
    and for missing subset entries."""
    path = os.path.join(data_dir, "config.json")
    if not os.path.exists(path):
        os.makedirs(data_dir, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(seed_config(), f, indent=2)
            f.write("\n")
        os.replace(path + ".tmp", path)
    with open(path) as f:
        cfg = json.load(f)
    seed = seed_config()
    for k, v in seed.items():
        if k not in ("images", "subset"):
            cfg.setdefault(k, v)
    cfg.setdefault("images", [])
    cfg["subset"] = dict(seed["subset"], **cfg.get("subset", {}))
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
    """The column's subset (a list, maybe empty), None when not configured."""
    rel, arch = image.get("release"), arch_of(image)
    return cfg["subset"].get(rel if arch == "amd64" else "%s/%s" % (rel, arch))


def schedule(cfg):
    """[(column, step)] for a cycle: candidates' probes first (fast), then
    baselines' probes, then the subsets (baselines first) of columns with one."""
    cols = columns(cfg["images"])
    cands = [c for c in cols if c.get("role") == "candidate"]
    bases = [c for c in cols if c.get("role") != "candidate"]
    return [(c, "probe") for c in cands + bases] + [(c, "subset") for c in bases + cands if subset_of(cfg, c)]


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
_TEST_OUTPUT = re.compile(r"^=+ Test output for (\S+):")
_CHECK = re.compile(r"^(PASS|FAIL|NETERR|INFO|SKIP)\s+(\S+): (.*)$")
_PROBE_SUMMARY = re.compile(r"^=== tls_probe summary \(CANARY_EXPECT=(\w+)[^)]*\): (\d+) checks\b")


def clean_lines(text):
    return [l.rstrip() for l in _ANSI.sub("", text).splitlines()]


def invocation_links(text):
    """Every distinct BuildBuddy invocation link printed, in order."""
    out = []
    for l in clean_lines(text):
        m = _STREAM.search(l)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def target_results(text, wanted):
    """{label: status} for the labels in `wanted`, from the final test
    summary only (a failing project's log embeds its inner summary)."""
    lines = clean_lines(text)
    ends = [i for i, l in enumerate(lines) if _END.match(l)]
    if not ends:
        return {}
    start = end = ends[-1]
    while start > 0 and _SUMMARY.match(lines[start - 1]):
        start -= 1
    out = {}
    for l in lines[start:end]:
        m = _RESULT.match(l)
        if m and m.group(1) in wanted:
            out[m.group(1)] = m.group(2)
    return out


def probe_result(text):
    """The probe's last complete output: {"expect", "total", "checks":
    {check: [status, message]}}, None unless its summary line was printed
    and every check it counts was seen."""
    res, target, checks = None, None, {}
    for l in clean_lines(text):
        m = _TEST_OUTPUT.match(l)
        if m:
            target, checks = m.group(1), {}
            continue
        if target != PROBE:
            continue
        m = _PROBE_SUMMARY.match(l)
        if m:
            total = int(m.group(2))
            res = {"expect": m.group(1), "total": total, "checks": checks} if len(checks) == total else None
            target = None
            continue
        m = _CHECK.match(l)
        if m:
            checks[m.group(2)] = [m.group(1), m.group(3)]
    return res


def is_emudhra(check):
    return check.split("/")[0].startswith("emudhra")


def classify(code):
    """passed | failed | error from Bazel's exit code: 1 is a build failure,
    3 failed tests; anything else (2 bad flags, 4 no tests, 8 interrupted,
    3x infrastructure, ...) means the run itself went wrong."""
    if code == 0:
        return "passed"
    return "failed" if code in (1, 3) else "error"


def redact(text, secret):
    return text.replace(secret, "<REDACTED>") if secret else text


# --- verdicts ---------------------------------------------------------------

def is_pass(status):
    return status in PASSING


def latest_complete(runs, image, step, subset=None, rev=None):
    """The newest run of the column's exact image (name, ref, role, arch)
    that ran to the end (and for a subset, of exactly that subset; with rev,
    at that repo revision)."""
    for r in reversed(runs):
        im = r["image"]
        if (r["step"] != step or r["status"] not in COMPLETE or im["name"] != image["name"]
                or im["ref"] != image["ref"] or im.get("role") != image.get("role")
                or arch_of(im) != arch_of(image)):
            continue
        if step == "probe" and not r.get("probe"):
            continue
        if step == "subset" and r.get("subset") != subset:
            continue
        if rev is not None and r.get("rev") != rev:
            continue
        return r
    return None


def protected(runs, col):
    """("yes"|"no"|"pending", [reasons], probe run): every emudhra* check
    passes in distrusted mode."""
    r = latest_complete(runs, col, "probe")
    if r is None:
        return "pending", ["no complete probe result for this image yet"], None
    p = r["probe"]
    em = {c: v for c, v in p["checks"].items() if is_emudhra(c)}
    if p["expect"] != "distrusted" or not em:
        return "pending", ["probe ran without eMudhra checks in distrusted mode"], r
    bad = ["%s: %s" % (c, m) for c, (st, m) in sorted(em.items()) if st == "FAIL"]
    if bad:
        return "no", bad, r
    unsure = ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(em.items()) if st not in ("PASS", "INFO")]
    return ("pending", unsure, r) if unsure else ("yes", [], r)


def builds(cfg, runs, images, col):
    """("yes"|"no"|"pending"|"not covered", [reasons], "N/M" or "", details):
    the probe's non-eMudhra checks pass, and every subset project that
    passed on the same release+arch baseline (same subset, same repo
    revision) also passes on the candidate."""
    reasons, state = [], "yes"
    pr = latest_complete(runs, col, "probe")
    if pr is None:
        state, reasons = "pending", ["no complete probe result yet"]
    else:
        other = {c: v for c, v in pr["probe"]["checks"].items() if not is_emudhra(c)}
        bad = ["%s: %s" % (c, m) for c, (st, m) in sorted(other.items()) if st == "FAIL"]
        unsure = ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(other.items()) if st not in ("PASS", "INFO", "FAIL")]
        if bad:
            state, reasons = "no", bad
        elif unsure:
            state, reasons = "pending", unsure
    subset = subset_of(cfg, col)
    if not subset:
        return ("no" if state == "no" else "not covered"), reasons + ["no ruleset subset for this release and arch"], "", {}
    targets = ["//%s:test" % p for p in subset]
    sub = latest_complete(runs, col, "subset", subset)
    if sub is None:
        return ("no" if state == "no" else "pending"), reasons + ["ruleset builds not run yet"], "", {}
    if any(t not in sub.get("targets", {}) for t in targets):
        missing = [t for t in targets if t not in sub.get("targets", {})]
        return ("no" if state == "no" else "pending"), reasons + ["no result for %s" % ", ".join(missing)], "", {}
    bases = [b for b in columns(images) if b.get("role") == "baseline" and b.get("release") == col.get("release")
             and arch_of(b) == arch_of(col)]
    base = next((x for x in (latest_complete(runs, b, "subset", subset, rev=sub.get("rev")) for b in bases) if x), None)
    if base is None or any(t not in base.get("targets", {}) for t in targets):
        return ("no" if state == "no" else "pending"), reasons + ["no complete baseline result at the same revision"], "", {}
    reference = [t for t in targets if is_pass(base["targets"][t])]
    ok = [t for t in reference if is_pass(sub["targets"][t])]
    details = {t: (base["targets"][t], sub["targets"][t]) for t in targets}
    if len(ok) < len(reference):
        state = "no"
        reasons = reasons + ["fails on the candidate but passes on the baseline: %s" % ", ".join(
            t for t in reference if t not in ok)]
    elif not reference:
        state = "no" if state == "no" else "pending"
        reasons = reasons + ["nothing passed on the baseline"]
    return state, reasons, "%d/%d" % (len(ok), len(reference)), details


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

    def compact(self, keep=MAX_RUNS, log_days=LOG_DAYS):
        """Keeps the newest `keep` runs (one line each) and deletes logs older
        than log_days that no kept run names."""
        with self.lock:
            runs = []
            try:
                by_id = {}
                with open(self.path) as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        by_id[rec["id"]] = rec
                runs = sorted(by_id.values(), key=lambda r: (r["start"], r["id"]))[-keep:]
            except FileNotFoundError:
                pass
            with open(self.path + ".tmp", "w") as f:
                for r in runs:
                    f.write(json.dumps(r, sort_keys=True) + "\n")
            os.replace(self.path + ".tmp", self.path)
        named = {r["log"] for r in runs}
        cutoff = time.time() - log_days * 86400
        for name in os.listdir(self.logs):
            path = os.path.join(self.logs, name)
            try:
                if name not in named and os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except OSError:
                pass

    def next_cycle(self):
        return max([r["cycle"] for r in self.runs()] or [0]) + 1


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def prune_work(root=WORK_ROOT):
    """Removes inner work dirs whose pid file names a dead process."""
    try:
        entries = os.listdir(root)
    except OSError:
        return
    for d in entries:
        path = os.path.join(root, d)
        try:
            with open(os.path.join(path, "pid")) as f:
                pid = int(f.read())
        except (OSError, ValueError):
            continue
        if not pid_alive(pid):
            subprocess.run(["chmod", "-R", "u+rwx", path], stderr=subprocess.DEVNULL)
            shutil.rmtree(path, ignore_errors=True)


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
        return subprocess.run(["git", "-C", self.work] + list(args), check=True, timeout=600,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL).stdout.decode().strip()

    def prepare(self, branch):
        if not os.path.isdir(os.path.join(self.work, ".git")):
            subprocess.run(["git", "clone", "--quiet", REPO_URL, self.work], check=True, timeout=600,
                           stdin=subprocess.DEVNULL)
        self.git("fetch", "--quiet", "origin", branch)
        self.git("reset", "--quiet", "--hard", "FETCH_HEAD")
        self.git("clean", "-fdq")
        return self.git("rev-parse", "HEAD")

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
        self.store.compact()
        # Two servers must not share a work dir: hold its lock for the cycle.
        with open(self.work.rstrip("/") + ".lock", "w") as lk:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("another server holds %s.lock" % self.work.rstrip("/"))
            with self.lock:
                rev = self.prepare(cfg["repo_branch"])
            for image, step in schedule(cfg):
                if self.stopping.is_set():
                    return
                self.housekeeping(cfg)
                self.step(cfg, cycle, rev, image, step)
        # Not a hot loop when every step is skipped or fails at once.
        self.stopping.wait(cfg.get("cycle_pause_s", 60))

    def output_base(self, cfg, image):
        # One per arch: the Arch flag would otherwise discard the analysis
        # cache at every switch. Steps run one at a time, so never two
        # Bazels on one output base.
        return os.path.join(cfg["output_root"], arch_of(image))

    def housekeeping(self, cfg):
        """Prunes dead inner work dirs; when disk runs low, `bazel clean
        --expunge`s this server's own output bases (no step is running).
        Never fails the cycle."""
        try:
            prune_work()
            root = cfg["output_root"]
            os.makedirs(root, exist_ok=True)
            if shutil.disk_usage(root).free >= cfg.get("min_free_gb", 15) * 2**30:
                return
            for arch in ARCHS:
                base = os.path.join(root, arch)
                if os.path.isdir(base):
                    print("low disk: cleaning %s" % base, file=sys.stderr)
                    subprocess.run([cfg["bazel"], "--output_base=" + base, "clean", "--expunge"],
                                   cwd=self.work, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=1800)
        except Exception as e:
            print("housekeeping: %s: %s" % (type(e).__name__, e), file=sys.stderr)

    def key_file(self, cfg, key):
        """A 0600 file with the key, for tools/buildbuddy_credential_helper.py."""
        path = os.path.join(cfg["output_root"], ".api-key")
        os.makedirs(cfg["output_root"], exist_ok=True)
        fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        os.replace(path + ".tmp", path)
        return path

    def new_record(self, cycle, image, step):
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        rid = "%s-c%d-%s-%s-%s" % (stamp, cycle, re.sub(r"[^A-Za-z0-9._-]", "_", image["name"]),
                                   re.sub(r"[^A-Za-z0-9._-]", "_", arch_of(image)), step)
        return {"id": rid, "cycle": cycle, "image": dict(image), "step": step, "start": now(),
                "end": None, "exit_code": None, "status": "running", "invocations": [],
                "targets": {}, "log": rid + ".log", "command": []}

    def command(self, cfg, cycle, image, step):
        """The Bazel command line for a step (no secrets), None if it has
        nothing to run.

        Bazel runs here, its actions on RBE in the image of the rewritten
        tools/remote.bazelrc. The projects' :test actions are no-remote-exec,
        so their inner Bazels run here too, with their actions on RBE.
        """
        arch = arch_of(image)
        arch_flags = [] if arch == "amd64" else ["--remote_default_exec_properties=Arch=" + arch]
        helper = os.path.join(self.work, "tools", "buildbuddy_credential_helper.py")
        head = [cfg["bazel"], "--output_base=" + self.output_base(cfg, image), "test"]
        tail = ["--config=remote-minimal", "--credential_helper=*.buildbuddy.io=" + helper,
                "--nocache_test_results"] + arch_flags
        if step == "probe":
            expect = "trusted" if image.get("role") == "baseline" else "distrusted"
            return head + [PROBE] + tail + ["--test_output=all", "--test_env=CANARY_EXPECT=" + expect]
        subset = subset_of(cfg, image)
        if not subset:
            return None
        args = head + ["//%s:test" % p for p in subset] + tail
        args += ["--//:inner_flags=" + f for f in arch_flags]
        if cfg.get("salt_inner", True):
            args.append("--//:inner_flags=--remote_instance_name=canary-%d" % cycle)
        return args

    def step(self, cfg, cycle, rev, image, step):
        rec = self.new_record(cycle, image, step)
        rec["rev"] = rev
        if step == "subset":
            rec["subset"] = subset_of(cfg, image)
        key = os.environ.get("BUILDBUDDY_API_KEY", "")
        if not key:
            rec.update(status="error", end=now(), error="BUILDBUDDY_API_KEY is not set")
            self.store.append(rec)
            return
        args = self.command(cfg, cycle, image, step)
        with self.lock:
            rc = os.path.join(self.work, "tools", "remote.bazelrc")
            try:
                env = dict(os.environ, BAZEL_MATRIX_KEY_FILE=self.key_file(cfg, key))
                self.git("checkout", "--", "tools/remote.bazelrc")
                with open(rc) as f:
                    text = rewrite_image(f.read(), image["ref"])
                with open(rc, "w") as f:
                    f.write(text)
            except Exception as e:
                rec.update(status="error", end=now(), error="%s: %s" % (type(e).__name__, e))
                self.store.append(rec)
                return
            rec["command"] = args
            self.current = rec
            self.store.append(rec)
            self.execute(rec, cfg, args, env, key)
            self.current = None
            self.store.append(rec)

    def execute(self, rec, cfg, args, env, key):
        log_path = os.path.join(self.store.logs, rec["log"])
        timeout = cfg.get("step_timeout_s", DEFAULT_TIMEOUT)
        timed_out = False
        try:
            with open(log_path, "w") as log:
                self.proc = subprocess.Popen(args, cwd=self.work, env=env, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             start_new_session=True)
                # Redacted on the way in, in case anything echoes the key.
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
            if timed_out:
                # The server may still run the build; stop it.
                subprocess.run([cfg["bazel"], "--output_base=" + args[1].split("=", 1)[1], "shutdown"],
                               cwd=self.work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300)
            with open(log_path, errors="replace") as f:
                text = f.read()
            wanted = {x for x in args if x.startswith("//") and ":" in x}
            rec.update(exit_code=code, invocations=invocation_links(text), targets=target_results(text, wanted))
            if rec["step"] == "probe":
                rec["probe"] = probe_result(text)
            if self.stopping.is_set():
                rec["status"] = "interrupted"
            elif timed_out:
                rec["status"] = "timeout"
            else:
                rec["status"] = classify(code)
                if rec["step"] == "probe" and rec["probe"] is None:
                    rec["status"] = "error"
                    rec["error"] = "no complete tls_probe summary in the output"
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
    """SIGINT the process group (the Bazel client cancels the build), then
    SIGKILL the group if it outlives the grace period."""
    try:
        os.killpg(proc.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        proc.wait(grace)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # stragglers in the group too
    except ProcessLookupError:
        pass


# --- UI ---------------------------------------------------------------------

CSS = """
:root { color-scheme: light dark; --bg:#fff; --fg:#1b1b1b; --mut:#666; --line:#ddd; --card:#fafafa;
  --yes:#1a7f37; --no:#cf222e; --pend:#9a6700; --yesbg:#dafbe1; --nobg:#ffebe9; --pendbg:#fff8c5; }
@media (prefers-color-scheme: dark) { :root { --bg:#16181b; --fg:#e6e6e6; --mut:#9a9a9a; --line:#333; --card:#1e2125;
  --yes:#3fb950; --no:#f85149; --pend:#d29922; --yesbg:#12261a; --nobg:#2d1416; --pendbg:#2b2411; } }
body { background:var(--bg); color:var(--fg); font:15px/1.45 system-ui,sans-serif; margin:16px auto; max-width:1100px; padding:0 16px; }
h1 { font-size:22px; margin:0 0 4px; } a { color:inherit; } .mut { color:var(--mut); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; margin:16px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }
.card h2 { font-size:16px; margin:0 0 10px; }
.q { margin:10px 0; padding:10px; border-radius:8px; }
.q .a { font-size:26px; font-weight:700; } .q .t { font-size:13px; }
.yes { background:var(--yesbg); } .yes .a { color:var(--yes); }
.no { background:var(--nobg); } .no .a { color:var(--no); }
.pending, .not_covered { background:var(--pendbg); } .pending .a, .not_covered .a { color:var(--pend); }
details { margin:6px 0; font-size:13px; } summary { cursor:pointer; }
table { border-collapse:collapse; font-size:13px; } td, th { border:1px solid var(--line); padding:2px 6px; text-align:left; }
ul { margin:4px 0; padding-left:18px; } code { font-size:12px; }
"""

PROTECT_TEXT = {
    "yes": "This image rejects certificates that chain to the eMudhra roots.",
    "no": "This image still trusts eMudhra: see details.",
    "pending": "No complete probe result for this image yet.",
}
BUILD_TEXT = {
    "yes": "Every ruleset build that works on today's image also works on this one.",
    "no": "Something that works on today's image breaks on this one: see details.",
    "pending": "Waiting for complete results on this image and its baseline.",
    "not covered": "No ruleset builds are checked for this release and arch.",
}


def esc(s):
    return html.escape(str(s), quote=True)


def elapsed(start, end=None):
    try:
        t0 = datetime.datetime.fromisoformat(start)
        t1 = datetime.datetime.fromisoformat(end) if end else datetime.datetime.now(datetime.timezone.utc)
        s = int((t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return ""
    return "%dh%02dm%02ds" % (s // 3600, s % 3600 // 60, s % 60)


def links(r):
    if not r:
        return ""
    return " ".join('<a href="%s">invocation</a>' % esc(u) for u in r.get("invocations") or []) + \
        ' <a href="/logs/%s">log</a>' % esc(r["log"])


def lis(items):
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % esc(x) for x in items) if items else ""


def answer(question, state, text, extra=""):
    return '<div class="q %s"><div class="t">%s</div><div class="a">%s%s</div><div class="t">%s</div></div>' % (
        esc(state.replace(" ", "_")), esc(question), esc(state.upper()), extra, esc(text))


def card(cfg, runs, images, col):
    p_state, p_why, p_run = protected(runs, col)
    b_state, b_why, ratio, table = builds(cfg, runs, images, col)
    out = ['<div class="card"><h2>Ubuntu %s candidate &middot; %s</h2>' % (esc(col.get("release")), esc(arch_of(col))),
           answer("Protected from the eMudhra compromise?", p_state, PROTECT_TEXT[p_state]),
           answer("Do popular rulesets still build?", b_state, BUILD_TEXT[b_state],
                  " &nbsp;<span style=\"font-size:16px\">%s</span>" % esc(ratio) if ratio else "")]
    det = []
    det.append('<p class="mut">%s<br>%s</p>' % (esc(col["name"]), esc(col["ref"])))
    if p_why:
        det.append("<b>eMudhra</b>%s" % lis(p_why))
    if b_why:
        det.append("<b>Builds</b>%s" % lis(b_why))
    if p_run:
        checks = p_run["probe"]["checks"]
        store = ["%s: %s" % (c, m) for c, (st, m) in sorted(checks.items()) if c.startswith("trust_store")]
        if store:
            det.append("<b>CA store vs baseline</b> (informational)%s" % lis(store))
        bad = ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(checks.items()) if st != "PASS"]
        det.append("<b>Probe</b>: %d checks%s %s" % (len(checks), ", not passing:" if bad else ", all pass", links(p_run)))
        det.append(lis(bad))
    if table:
        det.append("<b>Rulesets</b> (baseline &rarr; candidate)<table>%s</table>" % "".join(
            "<tr><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (esc(t), esc(b), esc(c))
            for t, (b, c) in sorted(table.items())))
    out.append("<details><summary>details</summary>%s</details></div>" % "".join(det))
    return "".join(out)


def render(cfg, runs, current):
    images = cfg["images"]
    cols = columns(images)
    out = ['<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>RBE image canary</title><style>%s</style></head><body>" % CSS,
           "<h1>RBE image canary</h1>",
           '<p class="mut">The new RBE images, checked on BuildBuddy against today\'s images. '
           "Refreshes every 30 s.</p>",
           '<div class="cards">']
    out += [card(cfg, runs, images, c) for c in cols if c.get("role") == "candidate"]
    out.append("</div>")
    det = []
    if current:
        det.append("<p>Running: %s %s %s, %s elapsed. <a href=\"/logs/%s?tail=200\">log tail</a></p>" % (
            esc(current["image"]["name"]), esc(arch_of(current["image"])), esc(current["step"]),
            elapsed(current["start"]), esc(current["log"])))
    else:
        det.append("<p>Idle between steps.</p>")
    base_rows = []
    for b in cols:
        if b.get("role") != "baseline":
            continue
        pr = latest_complete(runs, b, "probe")
        sr = latest_complete(runs, b, "subset", subset_of(cfg, b)) if subset_of(cfg, b) else None
        base_rows.append("<tr><td>%s %s</td><td>probe %s %s</td><td>%s</td></tr>" % (
            esc(b["name"]), esc(arch_of(b)), esc(pr["status"]) if pr else "none", links(pr),
            ("rulesets %d/%d passed %s" % (sum(1 for s in sr["targets"].values() if is_pass(s)), len(sr["targets"]),
                                          links(sr))) if sr else "rulesets: none"))
    det.append("<b>Baselines</b> (the reference)<table>%s</table>" % "".join(base_rows))
    det.append("<p><b>Rulesets checked</b>: %s</p>" % "; ".join(
        "%s: %s" % (esc(k), esc(", ".join(v) or "none")) for k, v in sorted(cfg["subset"].items())))
    if SUBSET_NOTES:
        det.append("<p><b>Not included</b>%s</p>" % lis(SUBSET_NOTES))
    hist = []
    for r in list(reversed(runs))[:30]:
        hist.append("<tr><td>%s</td><td>%s %s</td><td>%s</td><td>%s</td><td>%s%s</td><td>%s</td></tr>" % (
            esc(r["cycle"]), esc(r["image"]["name"]), esc(arch_of(r["image"])), esc(r["step"]), esc(r["start"]),
            esc(r["status"]), (" (%s)" % esc(r["error"])) if r.get("error") else "", links(r)))
    det.append("<b>Recent runs</b><table>%s</table>" % "".join(hist))
    out.append("<details><summary>details</summary>%s</details></body></html>" % "".join(det))
    return "".join(out)


_LOG_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def read_tail(path, n, max_bytes=1 << 20):
    """The last n lines of a file, reading at most max_bytes from its end."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - max_bytes))
        data = f.read().decode("utf-8", "replace")
    return "\n".join(data.splitlines()[-n:]) + "\n"


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
            key = os.environ.get("BUILDBUDDY_API_KEY", "")
            try:
                if path == "/":
                    cfg = load_config(data_dir)
                    self.send(200, render(cfg, store.runs(), runner.current if runner else None), "text/html")
                elif path == "/api/runs":
                    self.send(200, redact(json.dumps(store.runs(), indent=1), key), "application/json")
                elif path.startswith("/logs/"):
                    name = path[len("/logs/"):]
                    full = os.path.join(store.logs, name)
                    if not _LOG_NAME.match(name) or not os.path.isfile(full):
                        return self.send(404, "not found\n", "text/plain")
                    if "tail" in q:
                        text = read_tail(full, max(1, min(int(q["tail"][0]), 10000)))
                    else:
                        with open(full, errors="replace") as f:
                            text = f.read()
                    self.send(200, redact(text, key), "text/plain")
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
