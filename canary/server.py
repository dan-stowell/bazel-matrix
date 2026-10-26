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

# Popular rulesets, each with projects from projects.txt that build with
# it: the ruleset module itself (when it isn't known-failing) and small
# dependents (by the bazel_dep lines of their BCR MODULE.bazel). One column
# per group on the page.
GROUPS = {
    "rules_go": ["rules_go", "gazelle", "rpmpack", "circl", "jsonnet_go", "brotli_go"],
    "rules_python": ["rules_python", "abseil-py", "fire"],
    "rules_java": ["javaparser", "javacc", "bazel_jar_jar", "stardoc"],
    "rules_kotlin": ["rules_kotlin"],
    "rules_rust": ["rules_rust", "rules_rust_mdbook", "gazelle_rust"],
    "rules_js": ["aspect_rules_js", "aspect_rules_terser", "aspect_rules_esbuild", "rules_nodejs",
                 "aspect_rules_rollup"],
    "protobuf/grpc": ["protobuf", "zipkin-api", "bazel_worker_api", "rules_proto", "toolchains_protoc", "rules_buf",
                      "openconfig_gnpsi", "p4runtime"],
    "rules_cc": ["rules_cc", "zlib", "abseil-cpp", "googletest", "re2", "argparse", "cli11"],
    "rules_oci": ["rules_docker_compose_test", "masorange_rules_helm"],
    "rules_pkg": ["rules_pkg", "rules_shar", "gotopt2"],
    "rules_shell": ["rules_shell", "buildozer", "helly25_bashtest"],
    "bazel_skylib": ["bazel_skylib", "bazel_features", "sha256.bzl"],
}
# Every GROUPS project, on every release and arch. Each :test runs on RBE in
# the image (--config=inner-remote[-arm64]); a project that fails on the
# baseline isn't counted for the candidate. Keys: "<release>" for amd64,
# "<release>/<arch>" otherwise.
ALL_PROJECTS = [p for g in GROUPS.values() for p in g]
SUBSETS = {k: list(ALL_PROJECTS) for k in ("22.04", "22.04/arm64", "24.04", "24.04/arm64")}

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
        "repo_branch": "canary-server",
        "salt_inner": True,
        "step_timeout_s": DEFAULT_TIMEOUT,
        "cycle_pause_s": 60,
        # The Bazel binary; "" picks the one bazelisk downloaded for the
        # clone's .bazelversion. Not `bazel`/`bb` on this VM: the bb CLI adds
        # --remote_header=x-buildbuddy-api-key=<key> to Bazel's argv.
        "bazel": "",
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
    """[(column, step)] for a cycle: candidates first, probes (fast) then
    subsets, then baselines likewise. Until a baseline run pairs with it, a
    candidate is compared with the subset, which is chosen from baseline
    passers."""
    cols = columns(cfg["images"])
    cands = [c for c in cols if c.get("role") == "candidate"]
    bases = [c for c in cols if c.get("role") != "candidate"]
    return ([(c, "probe") for c in cands] + [(c, "subset") for c in cands if subset_of(cfg, c)]
            + [(c, "probe") for c in bases] + [(c, "subset") for c in bases if subset_of(cfg, c)])


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
_PROBE_SUMMARY = re.compile(r"^=== tls_probe summary \(CANARY_EXPECT=(\w+)([^)]*)\): (\d+) checks\b")


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
            total = int(m.group(3))
            # A simulated distrust (CANARY_SIMULATE_DISTRUST) says nothing
            # about the image, and a probe cut short by its deadline (a
            # "deadline" check) didn't run every check.
            done = len(checks) == total and "simulated" not in m.group(2) and "deadline" not in checks
            res = {"expect": m.group(1), "total": total, "checks": checks} if done else None
            target = None
            continue
        m = _CHECK.match(l)
        if m:
            checks[m.group(2)] = [m.group(1), m.group(3)]
    return res


def bep_results(lines, wanted):
    """{label: status} from Build Event Protocol JSON lines (testResult and
    testSummary events) for the labels in `wanted`."""
    out = {}
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        ident = ev.get("id", {})
        for kind, field in (("testResult", "status"), ("testSummary", "overallStatus")):
            label = ident.get(kind, {}).get("label")
            if label in wanted and field in ev.get(kind, {}):
                out[label] = ev[kind][field]
    return out


def no_tests(output_base, targets):
    """The //p:test targets whose test.xml (tools/inner_bazel.py's) says the
    inner `bazel test` found no tests (NO_TESTS): they built, but tested nothing."""
    return sorted(t for t in targets if 'message="NO_TESTS"' in test_xml(output_base, t))


INFRA = "INFRA"


def test_xml(output_base, target):
    """The text of a //p:test target's test.xml, "" if missing."""
    pkg, _, name = target[2:].partition(":")
    out_dir = os.path.join(output_base, "execroot", "_main", "bazel-out")
    try:
        configs = os.listdir(out_dir)
    except OSError:
        return ""
    for c in configs:
        try:
            with open(os.path.join(out_dir, c, "testlogs", pkg, name, "test.xml"), errors="replace") as f:
                return f.read()
        except OSError:
            pass
    return ""


def infra_killed(output_base, targets):
    """The targets whose wrapper was killed by infrastructure (or raised):
    their test.xml has an infra_killed or wrapper_error testcase
    (tools/remote_inner_bazel.py)."""
    return sorted(t for t in targets if re.search(r'name="(infra_killed|wrapper_error)"', test_xml(output_base, t)))


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


def newest(runs, image, step, subset=None):
    """The newest finished (not running) run of the column's exact image
    (name, ref, role, arch) and step (for a subset, of exactly that subset)."""
    for r in reversed(runs):
        im = r["image"]
        if (r["step"] != step or r["status"] == "running" or im["name"] != image["name"]
                or im["ref"] != image["ref"] or im.get("role") != image.get("role")
                or arch_of(im) != arch_of(image)):
            continue
        if step == "subset" and r.get("subset") != subset:
            continue
        return r
    return None


def complete(r):
    return r is not None and r["status"] in COMPLETE and (r["step"] != "probe" or bool(r.get("probe")))


def latest_complete(runs, image, step, subset=None, rev=None):
    """newest() if it ran to the end (and, with rev, at that repo revision);
    None otherwise: an older success never stands in for a newer run that
    didn't finish."""
    r = newest(runs, image, step, subset)
    if not complete(r) or (rev is not None and r.get("rev") != rev):
        return None
    return r


def current_rev(runs):
    """The repo revision of the newest run (the one the current cycle uses)."""
    return next((r["rev"] for r in reversed(runs) if r.get("rev")), None)


def last_note(runs, image, step, subset=None):
    """"last: <status>, <age>" for pending cells; "" when there's no run."""
    r = newest(runs, image, step, subset)
    if r is None:
        return ""
    try:
        age = datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(r.get("end") or r["start"])
        ago = "%dh%02dm ago" % (age.total_seconds() // 3600, age.total_seconds() % 3600 // 60)
    except (TypeError, ValueError):
        ago = "?"
    return "last: %s%s, %s" % (r["status"], "" if complete(r) else " (incomplete)", ago)


def protected(runs, col):
    """("yes"|"no"|"pending", [reasons], probe run): every emudhra* check
    passes in distrusted mode."""
    r = latest_complete(runs, col, "probe", rev=current_rev(runs))
    if r is None:
        return "pending", [last_note(runs, col, "probe") or "not run yet"], None
    p = r["probe"]
    em = {c: v for c, v in p["checks"].items() if is_emudhra(c)}
    if p["expect"] != "distrusted" or not em:
        return "pending", ["probe ran without eMudhra checks in distrusted mode"], r
    bad = ["%s: %s" % (c, m) for c, (st, m) in sorted(em.items()) if st == "FAIL"]
    if bad:
        return "no", bad, r
    unsure = ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(em.items()) if st not in ("PASS", "INFO")]
    return ("pending", unsure, r) if unsure else ("yes", [], r)


def probe_others(runs, col):
    """The probe's non-eMudhra checks that don't pass (FAIL or NETERR)."""
    r = latest_complete(runs, col, "probe", rev=current_rev(runs))
    if r is None:
        return None
    return ["%s %s: %s" % (st, c, m) for c, (st, m) in sorted(r["probe"]["checks"].items())
            if not is_emudhra(c) and st not in ("PASS", "INFO")]


NO_BASELINE = "no baseline result yet"


def compare_subset(cfg, runs, images, col, live=None):
    """(pending reason or None, {target: (baseline status, candidate status
    or None while running)}, candidate run, baseline run).

    The candidate side is `live` (the running subset step of this column,
    with the results so far) or the newest complete subset run with a result
    for every configured target. The baseline side is a complete baseline
    run (same release and arch, same subset, same repo revision); without
    one, NO_BASELINE (the candidate's results show, but no verdict).
    """
    subset = subset_of(cfg, col)
    if not subset:
        return "no ruleset projects for this release and arch", {}, None, None
    targets = ["//%s:test" % p for p in subset]
    sub = live or latest_complete(runs, col, "subset", subset, rev=current_rev(runs))
    if sub is None:
        return last_note(runs, col, "subset", subset) or "not run yet", {}, None, None
    missing = [t for t in targets if t not in sub.get("targets", {})]
    if missing and not live:
        return "no result for %s" % ", ".join(missing), {}, sub, None
    bases = [b for b in columns(images) if b.get("role") == "baseline" and b.get("release") == col.get("release")
             and arch_of(b) == arch_of(col)]
    base = next((x for x in (latest_complete(runs, b, "subset", subset, rev=sub.get("rev")) for b in bases) if x), None)
    if base is not None and any(t not in base.get("targets", {}) for t in targets):
        base = None
    ref = (lambda t: base["targets"][t]) if base else (lambda t: NO_BASELINE)
    return None, {t: (ref(t), sub.get("targets", {}).get(t)) for t in targets}, sub, base


def group_cell(cfg, pair, group):
    """("yes"|"no"|"running"|"pending"|"n/a", ok, reference, [notes], done)
    for a ruleset group: its projects that passed on the baseline must pass
    on the candidate."""
    pending, table = pair[0], pair[1]
    live = pair[2] is not None and pair[2].get("status") == "running"
    projects = ["//%s:test" % p for p in group]
    if pending is not None:
        return ("n/a" if pending.startswith("no ruleset") else "pending"), 0, 0, [pending], 0
    mine = [t for t in projects if t in table]
    if not mine:
        return "n/a", 0, 0, [], 0
    if any(table[t][0] == NO_BASELINE for t in mine):
        ok = [t for t in mine if is_pass(table[t][1])]
        done = sum(1 for t in mine if table[t][1] is not None)
        return ("running" if live else "pending"), len(ok), len(mine), [NO_BASELINE], done
    # Infra-killed projects count neither way: not as a candidate failure,
    # nor (on the baseline) as a failure that excuses the candidate.
    infra = [t for t in mine if is_pass(table[t][0]) and table[t][1] == INFRA]
    reference = [t for t in mine if is_pass(table[t][0]) and t not in infra]
    ok = [t for t in reference if is_pass(table[t][1])]
    running = [t for t in reference if table[t][1] is None]
    failing = [t for t in reference if t not in ok and t not in running]
    done = len(reference) - len(running)
    notes = ["infra (not counted): " + ", ".join(infra)] if infra else []
    if not reference:
        return ("pending", 0, 0, notes, 0) if infra else ("n/a", 0, 0, ["none passed on the baseline"], 0)
    if running or live:
        # Not green until the run's final summary is in.
        return ("no" if failing else "running"), len(ok), len(reference), failing + (
            ["running: " + ", ".join(running)] if running else ["finishing"]) + notes, done
    return ("no" if failing else "yes"), len(ok), len(reference), failing + notes, done


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


def resolve_bazel(cfg, work):
    """cfg["bazel"], or the bazelisk-downloaded Bazel matching work/.bazelversion."""
    if cfg.get("bazel"):
        return cfg["bazel"]
    with open(os.path.join(work, ".bazelversion")) as f:
        want = f.read().strip()
    root = os.path.expanduser("~/.cache/bazelisk/downloads")
    for dirpath, _, files in os.walk(root):
        if "bazel" in files and dirpath.endswith("/bin"):
            path = os.path.join(dirpath, "bazel")
            try:
                out = subprocess.run([path, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     timeout=30).stdout.decode()
            except (OSError, subprocess.SubprocessError):
                continue
            if out.split() == ["bazel", want]:
                return path
    raise RuntimeError("no Bazel %s under %s; run bazelisk once in %s" % (want, root, work))


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
        # Two servers must not share a work dir: hold its lock for the cycle.
        with open(self.work.rstrip("/") + ".lock", "w") as lk:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                # A server being replaced (canary/restart.sh) is finishing up.
                print("waiting for %s.lock" % self.work.rstrip("/"), file=sys.stderr)
                self.stopping.wait(10)
                return
            self.store.compact()  # under the lock: no other server is appending
            with self.lock:
                rev = self.prepare(cfg["repo_branch"])
                cfg["bazel"] = resolve_bazel(cfg, self.work)
            for image, step in schedule(cfg):
                if self.stopping.is_set():
                    return
                self.housekeeping(cfg)
                self.step(cfg, cycle, rev, image, step)
        # Not a hot loop when every step is skipped or fails at once.
        if not self.stopping.is_set():
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
            for base in [os.path.join(root, a + sfx) for a in ARCHS for sfx in ("", "-inner")]:
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
        # Each project's :test runs on RBE in the image (its inner Bazel's host
        # is the image and arch under test). Its own output base: the
        # credential helper differs, and Bazel caches helper results.
        remote_helper = os.path.join(self.work, "tools", "remote_exec_credential_helper.py")
        bep = os.path.join(cfg["output_root"], "bep-%s.json" % arch)
        args = [cfg["bazel"], "--output_base=" + self.output_base(cfg, image) + "-inner", "test"]
        args += ["//%s:test" % p for p in subset]
        args += ["--config=remote-minimal", "--config=inner-remote" + ("" if arch == "amd64" else "-" + arch),
                 "--credential_helper=*.buildbuddy.io=" + remote_helper, "--nocache_test_results",
                 # Once more after a failure: a wrapper killed by infra
                 # passes the second time (FLAKY, which counts as a pass).
                 "--flaky_test_attempts=2",
                 "--remote_download_regex=.*/testlogs/.*/test\\.xml$", "--build_event_json_file=" + bep]
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
            # A BEP file of this run's own, so live results never come from another run.
            bep = os.path.join(cfg["output_root"], "bep-%s.json" % rec["id"])
            args = [("--build_event_json_file=" + bep) if a.startswith("--build_event_json_file=") else a for a in args]
            if os.path.exists(bep):
                os.remove(bep)
            rec["command"] = args
            self.current = rec
            self.store.append(rec)
            self.execute(rec, cfg, args, env, key)
            self.current = None
            self.store.append(rec)

    def invoke(self, rec, args, env, key, log, log_path, deadline):
        """Runs one Bazel invocation, its output appended (redacted) to log
        and its test results streamed into rec["targets"] from its BEP file.
        Returns (exit code, timed out)."""
        timed_out = False
        self.proc = subprocess.Popen(args, cwd=self.work, env=env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        # Redacted on the way in, in case anything echoes the key.
        copier = threading.Thread(target=copy_redacted, args=(self.proc.stdout, log, key), daemon=True)
        copier.start()
        wanted = {x for x in args if x.startswith("//") and ":" in x}
        bep = next((x.split("=", 1)[1] for x in args if x.startswith("--build_event_json_file=")), None)
        bep_pos, bep_buf = 0, ""
        while self.proc.poll() is None:
            if self.stopping.is_set() or time.time() > deadline:
                timed_out = not self.stopping.is_set()
                kill_group(self.proc)
                break
            if bep:
                # Results as each target finishes, for the page.
                try:
                    with open(bep) as f:
                        f.seek(bep_pos)
                        bep_buf += f.read()
                        bep_pos = f.tell()
                    *done, bep_buf = bep_buf.split("\n")
                    rec["targets"].update(bep_results(done, wanted))
                except OSError:
                    pass
            if not rec["invocations"]:
                with open(log_path, errors="replace") as f:
                    rec["invocations"] = invocation_links(f.read(1 << 16))
            time.sleep(2)
        code = self.proc.wait()
        copier.join(60)
        if bep:
            try:
                os.remove(bep)
            except OSError:
                pass
        return code, timed_out

    def execute(self, rec, cfg, args, env, key):
        log_path = os.path.join(self.store.logs, rec["log"])
        deadline = time.time() + cfg.get("step_timeout_s", DEFAULT_TIMEOUT)
        output_base = args[1].split("=", 1)[1]
        timed_out = False
        try:
            wanted = [x for x in args if x.startswith("//") and ":" in x]
            with open(log_path, "w") as log:
                code, timed_out = self.invoke(rec, args, env, key, log, log_path, deadline)
            with open(log_path, errors="replace") as f:
                text = f.read()
            targets = target_results(text, set(wanted))
            infra = []
            if rec["step"] == "subset" and not self.stopping.is_set() and not timed_out:
                infra = infra_killed(output_base, [t for t in wanted if not is_pass(targets.get(t))])
                if infra:
                    # Killed by infrastructure, not failed: once more, alone.
                    first = args.index(wanted[0])
                    flags = [a for a in args[first:] if a not in wanted]
                    retry = args[:first] + infra + [
                        (a + "-retry") if a.startswith("--build_event_json_file=") else a for a in flags]
                    with open(log_path, "a") as log:
                        log.write("\n=== canary: retrying infra-killed %s\n" % " ".join(infra))
                        log.flush()
                        start = log.tell()
                        code2, timed_out = self.invoke(rec, retry, env, key, log, log_path, deadline)
                    with open(log_path, errors="replace") as f:
                        f.seek(start)
                        targets.update(target_results(f.read(), set(infra)))
                    infra = infra_killed(output_base, [t for t in infra if not is_pass(targets.get(t))])
                    if all(is_pass(targets.get(t)) or t in infra for t in wanted):
                        code = 0  # only infra kills, if anything, are left
                for t in infra:
                    targets[t] = INFRA
            if timed_out or self.stopping.is_set():
                # The Bazel server may still run the build; stop it.
                subprocess.run([cfg["bazel"], "--output_base=" + output_base, "shutdown"],
                               cwd=self.work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300)
            with open(log_path, errors="replace") as f:
                text = f.read()
            rec.update(exit_code=code, invocations=invocation_links(text), targets=targets, infra=infra)
            if rec["step"] == "subset":
                rec["no_tests"] = no_tests(output_base, [t for t, st in targets.items() if is_pass(st)])
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
            p = self.proc
            if p is not None and p.poll() is None:
                # Failed after launching: don't leave the build running.
                try:
                    kill_group(p)
                    p.wait(60)
                    subprocess.run([cfg["bazel"], "--output_base=" + output_base, "shutdown"],
                                   cwd=self.work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=300)
                except Exception as e2:
                    print("cleanup: %s: %s" % (type(e2).__name__, e2), file=sys.stderr)
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


_kill_lock = threading.Lock()


def kill_group(proc, grace=30):
    """SIGINT the process group (the Bazel client cancels the build), then
    SIGKILL it if the leader outlives the grace period. Only signals while
    the leader is unreaped, so the group id can't have been reused."""
    with _kill_lock:
        try:
            if proc.poll() is not None:
                return
            os.killpg(proc.pid, signal.SIGINT)
            deadline = time.time() + grace
            while time.time() < deadline:
                # Leader still a child (unreaped) means its pgid is still ours.
                if os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                    return
                time.sleep(0.5)
            os.killpg(proc.pid, signal.SIGKILL)
        except (ChildProcessError, ProcessLookupError):
            pass  # reaped meanwhile (by the runner's wait()): nothing left to signal


# --- UI ---------------------------------------------------------------------

CSS = "body{font-family:sans-serif;margin:16px} table{border-collapse:collapse} " \
      "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;vertical-align:top} " \
      ".yes{color:#1a7f37} .no{color:#cf222e;font-weight:bold} .pending,.na,.running{color:#777}"
MARK = {"yes": "&#10003;", "no": "&#10007;", "pending": "pending", "n/a": "n/a", "running": "running"}


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


def first_link(r):
    inv = (r or {}).get("invocations") or []
    return inv[0] if inv else ("/logs/" + r["log"] if r else "")


def cell(state, text, href, title):
    body = '<span class="%s">%s</span>%s' % ("na" if state == "n/a" else state, MARK.get(state, esc(state)),
                                             (" " + esc(text)) if text else "")
    if href:
        body = '<a href="%s">%s</a>' % (esc(href), body)
    return '<td title="%s">%s</td>' % (esc(title), body)


def render(cfg, runs, current):
    images = cfg["images"]
    cols = columns(images)
    out = ['<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">',
           "<title>RBE image canary</title><style>%s</style></head><body>" % CSS,
           "<h1>RBE image canary</h1>",
           "<p>Candidate images vs. today's images on BuildBuddy RBE; ruleset cells count projects that "
           "pass on today's image and also on the candidate.</p>",
           "<table><tr><th>Image</th><th>eMudhra protected</th>%s</tr>" % "".join(
               "<th>%s</th>" % esc(g) for g in GROUPS)]
    for c in cols:
        if c.get("role") != "candidate":
            continue
        digest = c["ref"].rsplit("@sha256:", 1)[-1][:12]
        others = probe_others(runs, c)
        note = ("<br><span class=\"no\" title=\"%s\">probe: %d other checks fail</span>" % (
            esc("; ".join(others)), len(others))) if others else ""
        out.append('<tr><td>%s &middot; %s<br><code title="%s">%s</code>%s</td>' % (
            esc(c.get("release")), esc(arch_of(c)), esc(c["ref"]), esc(digest), note))
        state, why, pr = protected(runs, c)
        out.append(cell(state, "", first_link(pr), "; ".join(why)))
        live = current if (current and current["step"] == "subset" and current["image"].get("name") == c["name"]
                           and current["image"].get("ref") == c["ref"] and arch_of(current["image"]) == arch_of(c)) else None
        pair = compare_subset(cfg, runs, images, c, live)
        href = first_link(pair[2])
        for g, projects in GROUPS.items():
            st, ok, ref, failing, done = group_cell(cfg, pair, projects)
            if not set(projects) & set(subset_of(cfg, c) or []):
                st, failing = "n/a", []
            title = ("fails: " + ", ".join(failing)) if st == "no" else "; ".join(failing) or ", ".join(
                t for t in ("//%s:test" % p for p in projects) if t in pair[1])
            text = "%d/%d" % (ok, ref) if ref else ""
            table = pair[1]
            ok_targets = [t for t in ("//%s:test" % p for p in projects) if t in table and
                          (is_pass(table[t][0]) or table[t][0] == NO_BASELINE) and is_pass(table[t][1])]
            built_only = [t for t in ok_targets if t in ((pair[2] or {}).get("no_tests") or [])]
            # Passed only on the retry: flaky on both is the project's own
            # flakiness, flaky only on the candidate is worth a look.
            flaky = [t for t in ok_targets if table[t][1] == "FLAKY"]
            only_cand = [t for t in flaky if table[t][0] != "FLAKY"]
            if built_only and st in ("yes", "no"):
                text += ", %d tested" % (len(ok_targets) - len(built_only))
                title += "; built, no tests: " + ", ".join(built_only)
            infra_t = [t for t in ("//%s:test" % p for p in projects) if table.get(t, (None, None))[1] == INFRA]
            if infra_t and st in ("yes", "no", "pending"):
                text += ", %d infra" % len(infra_t)
            if flaky and st in ("yes", "no"):
                text += ", %d flaky%s" % (len(flaky), " (candidate only)" if only_cand else "")
                title += "; flaky: %s" % ", ".join(
                    "%s (%s)" % (t, "only on the candidate" if t in only_cand else "also on the baseline")
                    for t in flaky)
            if st == "running" or (st == "no" and live):
                text = "%d/%d done, %d ok" % (done, ref, ok)
            if pair[3] is None and table and ref:
                text = ("%d/%d done, %d ok" % (done, ref, ok) if live else "%d/%d ok" % (ok, ref)) + ", baseline pending"
            out.append(cell(st, text, href if (st in ("yes", "no", "running") or table) else "", title))
        out.append("</tr>")
    out.append("</table>")
    det = []
    if current:
        det.append('<p>Running: %s %s %s, %s. <a href="/logs/%s?tail=200">log</a></p>' % (
            esc(current["image"]["name"]), esc(arch_of(current["image"])), esc(current["step"]),
            elapsed(current["start"]), esc(current["log"])))
    det.append("<p>Baselines:</p><ul>")
    for b in cols:
        if b.get("role") == "baseline":
            pr = latest_complete(runs, b, "probe")
            sr = latest_complete(runs, b, "subset", subset_of(cfg, b)) if subset_of(cfg, b) else None
            det.append('<li>%s %s <code>%s</code>: probe %s%s, projects %s%s</li>' % (
                esc(b["name"]), esc(arch_of(b)), esc(b["ref"].rsplit("@sha256:", 1)[-1][:12]),
                esc(pr["status"]) if pr else "none", (' <a href="%s">link</a>' % esc(first_link(pr))) if pr else "",
                ("%d/%d passed" % (sum(1 for x in sr["targets"].values() if is_pass(x)), len(sr["targets"])))
                if sr else "none", (' <a href="%s">link</a>' % esc(first_link(sr))) if sr else ""))
    det.append("</ul><p>Projects per release/arch: %s</p>" % esc("; ".join(
        "%s: %s" % (k, ", ".join(v) or "none") for k, v in sorted(cfg["subset"].items())) or "none"))
    det.append("<p>Recent runs:</p><table>")
    for r in list(reversed(runs))[:40]:
        det.append('<tr><td>%s</td><td>%s %s</td><td>%s</td><td>%s</td><td>%s%s</td><td><a href="/logs/%s">log</a>'
                   '%s</td></tr>' % (
                       esc(r["cycle"]), esc(r["image"]["name"]), esc(arch_of(r["image"])), esc(r["step"]),
                       esc(r["start"]), esc(r["status"]), (" (%s)" % esc(r["error"])) if r.get("error") else "",
                       esc(r["log"]), "".join(' <a href="%s">invocation</a>' % esc(u) for u in r.get("invocations") or [])))
    det.append("</table>")
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
        # Release the port first (a replacement can bind it at once), then
        # stop the running step in the background.
        threading.Thread(target=server.shutdown, daemon=True).start()
        threading.Thread(target=runner.stop, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    runner.start()
    print("serving on http://%s:%d" % (args.host, args.port), file=sys.stderr)
    server.serve_forever()
    server.server_close()
    runner.join(120)  # lets the running step record its end


if __name__ == "__main__":
    main()
