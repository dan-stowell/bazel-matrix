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

# Priority tiers for the broad run (every projects.txt project that isn't
# known-failing; see tiers()). Tier 1: C/C++ projects on the image's own,
# autodetected cc toolchain; tier 2: popular rulesets and their dependents;
# tier 3: the rest.
HERMETIC_CC = {"toolchains_llvm", "hermetic_cc_toolchain", "toolchains_llvm_bootstrapped", "gcc_toolchain",
               "toolchains_musl", "hermetic_clang_toolchain", "portable_cc_toolchain", "toolchains_buildbuddy"}
CC_RULES = {"rules_cc", "rules_foreign_cc"}
POPULAR = ["rules_go", "gazelle", "rules_python", "rules_java", "rules_jvm_external", "rules_kotlin", "rules_rust",
           "aspect_rules_js", "rules_nodejs", "protobuf", "grpc", "rules_proto", "rules_oci", "rules_pkg",
           "rules_shell", "rules_cc"]
TIER_NAMES = {1: "tier 1: image toolchains (C/C++)", 2: "tier 2: popular rulesets", 3: "tier 3: the rest"}
TIER_HEURISTIC = (
    "Tiers come from each project's bazel_dep lines (its BCR MODULE.bazel at the projects.json version, "
    "in canary/deps.json). Tier 1, the image's own toolchains: not a ruleset (no rules_/aspect_rules_/"
    "toolchains_/gazelle prefix, no .bzl suffix), no hermetic C++ toolchain dep (%s), and a direct dep on "
    "rules_cc or rules_foreign_cc, or on another tier-1 project (a C/C++ library), so its inner Bazel "
    "autodetects the image's gcc. Tier 2: one of %s or a direct dep on one. Tier 3: the rest (including "
    "C/C++ projects that use native cc rules without any such dep, which MODULE.bazel can't show). "
    "System python3/perl/shell use isn't visible in MODULE.bazel, so it doesn't promote a project."
) % (", ".join(sorted(HERMETIC_CC)), ", ".join(POPULAR))
MATRIX = "MATRIX"  # reference: the matrix's own record (not known-failing in projects.txt) says it passes

PROBE = "//canary:tls_probe_test"
ARCHS = ["amd64", "arm64"]
DEFAULT_TIMEOUT = 3 * 3600
PASSING = {"PASSED", "FLAKY"}
MAX_RUNS = 600
LOG_DAYS = 3
WORK_ROOT = "/var/tmp/bazel-matrix/work"  # tools/inner_bazel.py's
COMPLETE = ("passed", "failed")
# The server's own files: changing them doesn't change any build result.
SERVER_FILES = ("server.py", "server_test.py", "README.md", "restart.sh", "BUILD.bazel")  # statuses of a run that ran to the end


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
        "min_free_gb": 20,
        # The broad run: projects per batch invocation, its --jobs, and
        # whether an image's amd64 and arm64 batches run at once.
        "batch_size": 200,
        "jobs": 100,
        "parallel_archs": True,
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


def schedule(cfg, projects, tier_of):
    """[group] for a cycle, each group [(column, step, batch)] of one image
    (its archs run at once, in their own output bases; cfg["parallel_archs"]
    false runs them one by one). batch is None for a probe, else (tier,
    index, [projects]). Order: candidate probes, then each tier's batches on
    every candidate column (batch k of every image before batch k+1), then
    the baselines likewise."""
    cols = columns(cfg["images"])
    size = int(cfg.get("batch_size", 150))
    plans = {id(c): batches(projects, tier_of, arch_of(c), size) for c in cols}
    groups = []

    def add(items):
        if not items:
            return
        if cfg.get("parallel_archs", True):
            groups.append(items)
        else:
            groups.extend([i] for i in items)

    for role in ("candidate", "baseline"):
        mine = [c for c in cols if (c.get("role") == "candidate") == (role == "candidate")]
        images = []
        for c in mine:
            if (c["name"], c["ref"]) not in images:
                images.append((c["name"], c["ref"]))
        by_image = [[c for c in mine if (c["name"], c["ref"]) == im] for im in images]
        for cs in by_image:
            add([(c, "probe", None) for c in cs])
        for tier in (1, 2, 3):
            n = max([sum(1 for b in plans[id(c)] if b[0] == tier) for c in mine] or [0])
            for k in range(n):
                for cs in by_image:
                    add([(c, "batch", b) for c in cs for b in plans[id(c)] if b[0] == tier and b[1] == k])
    return groups


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


# --- projects, tiers and batches --------------------------------------------

def parse_projects(text):
    """projects.txt -> [{"name", "known_failing": bool, "bazel": pinned version or None}] in file order."""
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            out.append({"name": line.split()[0].split("@")[0], "known_failing": False, "bazel": None})
        elif out:
            words = line.split()
            if words[0] == "known-failing":
                out[-1]["known_failing"] = True
            elif words[0] == "bazel" and len(words) > 1:
                out[-1]["bazel"] = words[1]
    return out


_BAZEL_DEP = re.compile(r'bazel_dep\(\s*name\s*=\s*"([^"]+)"')


def module_deps(text):
    """The sorted bazel_dep names of a MODULE.bazel (dev deps included: the project is the root)."""
    return sorted(set(_BAZEL_DEP.findall(text)))


def write_deps(bcr_dir, projects_json, out):
    """Writes {module: [bazel_dep names]} for every projects.json project, from
    a BCR checkout at projects.json's bcr_commit (tools/sync.py's cache)."""
    with open(projects_json) as f:
        projects = json.load(f)["projects"]
    deps = {}
    for p in projects:
        with open(os.path.join(bcr_dir, "modules", p["name"], p["version"], "MODULE.bazel")) as f:
            deps[p["name"]] = module_deps(f.read())
    with open(out, "w") as f:
        json.dump(deps, f, indent=0, sort_keys=True)
        f.write("\n")


def is_ruleset(name):
    return name.startswith(("rules_", "aspect_rules_", "toolchains_", "gazelle")) or name.endswith(".bzl")


def tiers(names, deps):
    """{name: (tier, reason)} for names, by TIER_HEURISTIC; deps: {module: [bazel_dep names]}."""
    cc = set()  # C/C++ projects, among every module deps has (known-failing ones too)
    changed = True
    while changed:
        changed = False
        for n in sorted(set(names) | set(deps)):
            d = set(deps.get(n, []))
            if n in cc or is_ruleset(n) or d & HERMETIC_CC:
                continue
            if d & CC_RULES or d & cc:
                cc.add(n)
                changed = True
    out = {}
    pop = set(POPULAR)
    for n in names:
        d = set(deps.get(n, []))
        if n in cc:
            why = sorted(d & CC_RULES) or sorted(d & cc)[:3]
            out[n] = (1, "C/C++ via " + ", ".join(why))
        elif n in pop or d & pop:
            out[n] = (2, "is a popular ruleset" if n in pop else "uses " + ", ".join(sorted(d & pop)))
        else:
            out[n] = (3, "hermetic C++ toolchain: " + ", ".join(sorted(d & HERMETIC_CC)) if d & HERMETIC_CC else
                      "no popular ruleset or C/C++ dep")
    return out


NO_ARM64_BAZELS = ("8.4.2",)  # tools/versions.bzl versions without an arm64_sha256


def arm64_ok(project):
    """False for a project whose pinned inner Bazel has no linux-arm64 binary."""
    return project["bazel"] not in NO_ARM64_BAZELS


def batches(projects, tier_of, arch, size):
    """[(tier, index, [names])]: the column's projects (not known-failing; on
    arm64, not pinned to a Bazel without an arm64 binary), by tier then name,
    in chunks of `size`."""
    out = []
    for tier in (1, 2, 3):
        names = sorted(p["name"] for p in projects if not p["known_failing"] and tier_of.get(p["name"], (3,))[0] == tier
                       and (arch == "amd64" or arm64_ok(p)))
        for i in range(0, len(names), size):
            out.append((tier, i // size, names[i:i + size]))
    return out


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


def test_xml(output_base, target, since=0):
    """The text of a //p:test target's test.xml, "" if missing or older than
    `since` (a time)."""
    pkg, _, name = target[2:].partition(":")
    out_dir = os.path.join(output_base, "execroot", "_main", "bazel-out")
    try:
        configs = os.listdir(out_dir)
    except OSError:
        return ""
    for c in configs:
        path = os.path.join(out_dir, c, "testlogs", pkg, name, "test.xml")
        try:
            if os.path.getmtime(path) < since:
                continue
            with open(path, errors="replace") as f:
                return f.read()
        except OSError:
            pass
    return ""


def retry_outcome(targets, infra, again, code, aborted, xml):
    """Updates targets with an infra retry's results; returns the targets
    still to count as INFRA.

    again: the retry's own summary results; code: its exit code; xml(t): the
    target's test.xml written by the retry ("" if not). A pass only on the
    retry is FLAKY; a fresh, non-infra failure is a failure; anything else
    (no fresh result, the retry failing before running tests, interrupted)
    stays INFRA, never a pass.
    """
    left = []
    for t in infra:
        st = again.get(t)
        fresh = xml(t)
        if st is not None and is_pass(st) and not aborted:
            targets[t] = "FLAKY"
        elif (st is not None and fresh and not aborted and code in (1, 3)
              and not re.search(r'name="(infra_killed|wrapper_error)"', fresh)):
            targets[t] = st
        else:
            left.append(t)
    return left


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
RUNNING = "RUNNING"
# Results of a project that ran (NO STATUS, INCOMPLETE, SKIPPED, REMOTE
# FAILURE: it didn't, and a resume runs it again).
RAN = {"PASSED", "FLAKY", "FAILED", "FAILED TO BUILD", "TIMEOUT", INFRA}
DONE = COMPLETE + ("timeout",)  # a batch that needn't run again this cycle


def same_column(im, col):
    return (im["name"] == col["name"] and im["ref"] == col["ref"] and im.get("role") == col.get("role")
            and arch_of(im) == arch_of(col))


def batch_done(runs, col, rev, cycle, step, names):
    """A run of this step (and batch) for the column finished this cycle at rev."""
    return any(r["step"] == step and r.get("cycle") == cycle and r.get("rev") == rev and r["status"] in DONE
               and same_column(r["image"], col) and (step != "batch" or r.get("subset") == names)
               and (step != "probe" or bool(r.get("probe"))) for r in runs)


def done_projects(runs, col, rev, cycle):
    """The projects with a result from a finished batch of this cycle at rev."""
    out = set()
    for r in runs:
        if (r["step"] == "batch" and r.get("cycle") == cycle and r.get("rev") == rev and r["status"] in DONE
                and same_column(r["image"], col)):
            out.update(t[2:-5] for t, st in (r.get("targets") or {}).items() if st in RAN)
    return out


def remaining(runs, group, rev, cycle):
    """The group's items still to run this cycle: a probe without a finished
    run; a batch less its projects that already have a result (a restart, or
    a new batch_size, resumes where it was)."""
    todo = []
    done = {}
    for im, st, b in group:
        if st == "probe":
            if not batch_done(runs, im, rev, cycle, st, None):
                todo.append((im, st, b))
            continue
        key = (im["name"], im["ref"], arch_of(im))
        if key not in done:
            done[key] = done_projects(runs, im, rev, cycle)
        names = [n for n in b[2] if n not in done[key]]
        if names:
            todo.append((im, st, (b[0], b[1], names)))
    return todo


def project_results(runs, col, rev, lives=()):
    """{target: (status, run)}: per project, a running batch's result, else
    the newest finished batch's at rev, else RUNNING while a batch runs it."""
    out = {}
    running = {}
    for r in lives:
        if r.get("step") == "batch" and same_column(r["image"], col):
            for p in r.get("subset") or []:
                t = "//%s:test" % p
                st = r["targets"].get(t)
                if st is None:
                    running[t] = (RUNNING, r)
                else:
                    out[t] = (st, r)
    for r in reversed(runs):
        if r["step"] != "batch" or r.get("rev") != rev or r["status"] not in DONE or not same_column(r["image"], col):
            continue
        for t, st in (r.get("targets") or {}).items():
            out.setdefault(t, (st, r))
    for t, v in running.items():
        out.setdefault(t, v)
    return out


def baseline_of(images, col):
    return [b for b in columns(images) if b.get("role") == "baseline" and b.get("release") == col.get("release")
            and arch_of(b) == arch_of(col)]


def project_table(cfg, runs, col, targets, lives=()):
    """{target: (reference status, candidate status or None, candidate run)}.
    The reference: the baseline's result at the same rev; else, for 22.04
    amd64, MATRIX (the matrix's bb remote record on that same image: projects
    not known-failing pass); else NO_BASELINE."""
    rev = current_rev(runs)
    cand = project_results(runs, col, rev, lives)
    base = {}
    for b in baseline_of(cfg["images"], col):
        for t, v in project_results(runs, b, rev, lives).items():
            base.setdefault(t, v)
    matrix = col.get("release") == "22.04" and arch_of(col) == "amd64"
    out = {}
    for t in targets:
        ref = base.get(t, (None,))[0]
        if ref is None or ref == RUNNING:
            ref = MATRIX if matrix else NO_BASELINE
        c = cand.get(t)
        out[t] = (ref, c[0] if c else None, c[1] if c else None)
    return out


def ref_passes(ref):
    return is_pass(ref) or ref == MATRIX


def kind(ref, st):
    """pass | flaky | regression | fail | infra | running | pending, for a candidate result."""
    if st is None:
        return "pending"
    if st == RUNNING:
        return "running"
    if st == INFRA:
        return "infra"
    if st == "FLAKY":
        return "flaky"
    if is_pass(st):
        return "pass"
    return "regression" if ref_passes(ref) else "fail"


def tally(table, targets):
    """Counts of kind() over the targets in table, plus "total" and "ok" (pass + flaky)."""
    c = {k: 0 for k in ("pass", "flaky", "regression", "fail", "infra", "running", "pending")}
    for t in targets:
        if t in table:
            c[kind(table[t][0], table[t][1])] += 1
    c["total"] = sum(c.values())
    c["ok"] = c["pass"] + c["flaky"]
    return c


def ref_label(table):
    refs = {v[0] for v in table.values()}
    if refs and refs <= {MATRIX}:
        return "vs matrix record"
    if NO_BASELINE in refs:
        return "baseline pending" if not (refs - {NO_BASELINE}) else "baseline partly pending"
    return "vs baseline" if MATRIX not in refs else "vs baseline / matrix record"


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

    def resume_cycle(self):
        """The newest cycle if it hasn't finished (a restart resumes it, its
        finished batches skipped), else a new one."""
        last = max([r["cycle"] for r in self.runs()] or [0])
        try:
            with open(os.path.join(os.path.dirname(self.path), "cycle-done")) as f:
                done = int(f.read().strip() or 0)
        except (OSError, ValueError):
            done = 0
        return last if last > done else last + 1

    def mark_cycle_done(self, cycle):
        path = os.path.join(os.path.dirname(self.path), "cycle-done")
        with open(path + ".tmp", "w") as f:
            f.write("%d\n" % cycle)
        os.replace(path + ".tmp", path)


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


def live_bazel(output_root, proc="/proc"):
    """This server's output bases with a Bazel client still running (a
    command in progress: an old server's step, or its shutdown)."""
    bases = {os.path.join(output_root, a + sfx) for a in ARCHS for sfx in ("", "-inner")}
    busy = set()
    for pid in os.listdir(proc):
        if not pid.isdigit():
            continue
        try:
            with open(os.path.join(proc, pid, "cmdline"), "rb") as f:
                argv = f.read().decode("utf-8", "replace").split("\0")
        except OSError:
            continue
        if argv and argv[0].startswith("bazel("):
            continue  # a Bazel server (idle ones stay up), not a client
        for a in argv:
            if a.startswith("--output_base=") and a.split("=", 1)[1] in bases:
                busy.add(a.split("=", 1)[1])
    return sorted(busy)


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
        self.currents = {}  # id -> the running steps' records
        self.procs = set()
        self.info = None  # (projects, {name: (tier, reason)}) of the current cycle
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
        # The newest commit that can change a project's result: one touching
        # more than the server's own files. Pushing server changes then
        # keeps this cycle's results (and the finished batches) current.
        return self.git("log", "-1", "--format=%H", "--", ".", *(":(exclude)canary/" + f for f in SERVER_FILES))

    def load_info(self):
        with open(os.path.join(self.work, "projects.txt")) as f:
            projects = parse_projects(f.read())
        with open(os.path.join(self.work, "canary", "deps.json")) as f:
            deps = json.load(f)
        names = [p["name"] for p in projects if not p["known_failing"]]
        return projects, tiers(names, deps)

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
        cycle = self.store.resume_cycle()
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
            busy = live_bazel(cfg["output_root"])
            if busy:
                # An old server's Bazel is still shutting down: don't reset
                # the workspace under it.
                print("waiting for Bazel servers on %s" % ", ".join(busy), file=sys.stderr)
                self.stopping.wait(10)
                return
            with self.lock:
                rev = self.prepare(cfg["repo_branch"])
                cfg["bazel"] = resolve_bazel(cfg, self.work)
                self.info = self.load_info()
            for group in schedule(cfg, *self.info):
                if self.stopping.is_set():
                    return
                todo = remaining(self.store.runs(), group, rev, cycle)
                if todo:
                    self.housekeeping(cfg)
                    self.group(cfg, cycle, rev, todo)
            if not self.stopping.is_set():
                self.store.mark_cycle_done(cycle)
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
            if shutil.disk_usage(root).free >= cfg.get("min_free_gb", 20) * 2**30:
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

    def command(self, cfg, cycle, image, step, names=None):
        """The Bazel command line for a step (no secrets), None if it has
        nothing to run.

        Bazel runs here, its actions on RBE in the image of the rewritten
        tools/remote.bazelrc. A batch's //<p>:test actions run on RBE in the
        image too (--config=inner-remote): each inner Bazel's host is the
        image and arch under test.
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
        if not names:
            return None
        # Its own output base: the credential helper differs, and Bazel
        # caches helper results.
        remote_helper = os.path.join(self.work, "tools", "remote_exec_credential_helper.py")
        bep = os.path.join(cfg["output_root"], "bep-%s.json" % arch)
        args = [cfg["bazel"], "--output_base=" + self.output_base(cfg, image) + "-inner", "test"]
        args += ["//%s:test" % p for p in names]
        args += ["--config=remote-minimal", "--config=inner-remote" + ("" if arch == "amd64" else "-" + arch),
                 "--jobs=%d" % int(cfg.get("jobs", 100)),
                 "--credential_helper=*.buildbuddy.io=" + remote_helper, "--nocache_test_results",
                 # Once more after a failure: a wrapper killed by infra
                 # passes the second time (FLAKY, which counts as a pass).
                 "--flaky_test_attempts=2",
                 "--remote_download_regex=.*/testlogs/.*/test\\.xml$", "--build_event_json_file=" + bep]
        if cfg.get("salt_inner", True):
            args.append("--//:inner_flags=--remote_instance_name=canary-%d" % cycle)
        return args

    def group(self, cfg, cycle, rev, items):
        """Runs a group's steps (one image, its archs) at once."""
        image = items[0][0]
        recs = []
        for im, step, batch in items:
            rec = self.new_record(cycle, im, step if batch is None else "%s-t%d-%d" % (step, batch[0], batch[1]))
            rec.update(rev=rev, step=step)
            if batch is not None:
                rec.update(tier=batch[0], batch=batch[1], subset=list(batch[2]))
            recs.append((rec, self.command(cfg, cycle, im, step, batch[2] if batch else None)))
        key = os.environ.get("BUILDBUDDY_API_KEY", "")
        if not key:
            for rec, _ in recs:
                rec.update(status="error", end=now(), error="BUILDBUDDY_API_KEY is not set")
                self.store.append(rec)
            return
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
                for rec, _ in recs:
                    rec.update(status="error", end=now(), error="%s: %s" % (type(e).__name__, e))
                    self.store.append(rec)
                return
            threads = []
            for rec, args in recs:
                if args is None:
                    rec.update(status="error", end=now(), error="nothing to run")
                    self.store.append(rec)
                    continue
                # A BEP file of this run's own, so live results never come from another run.
                bep = os.path.join(cfg["output_root"], "bep-%s.json" % rec["id"])
                args = [("--build_event_json_file=" + bep) if a.startswith("--build_event_json_file=") else a
                        for a in args]
                if os.path.exists(bep):
                    os.remove(bep)
                rec["command"] = args
                self.currents[rec["id"]] = rec
                self.store.append(rec)
                t = threading.Thread(target=self.execute_and_record, args=(rec, cfg, args, env, key), daemon=True)
                t.start()
                threads.append(t)
            for t in threads:
                t.join()

    def execute_and_record(self, rec, cfg, args, env, key):
        try:
            self.execute(rec, cfg, args, env, key)
        finally:
            # Recorded as soon as it ends, not when the group's slowest does.
            self.store.append(rec)
            self.currents.pop(rec["id"], None)

    def step(self, cfg, cycle, rev, image, step, batch=None):
        self.group(cfg, cycle, rev, [(image, step, batch)])

    def invoke(self, rec, args, env, key, log, log_path, deadline, holder):
        """Runs one Bazel invocation, its output appended (redacted) to log
        and its test results streamed into rec["targets"] from its BEP file.
        Returns (exit code, timed out). holder[0] is set to its process."""
        timed_out = False
        proc = subprocess.Popen(args, cwd=self.work, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        holder[:] = [proc]
        self.procs.add(proc)
        if self.stopping.is_set():
            kill_group(proc)
        # Redacted on the way in, in case anything echoes the key.
        copier = threading.Thread(target=copy_redacted, args=(proc.stdout, log, key), daemon=True)
        copier.start()
        wanted = {x for x in args if x.startswith("//") and ":" in x}
        bep = next((x.split("=", 1)[1] for x in args if x.startswith("--build_event_json_file=")), None)
        bep_pos, bep_buf = 0, ""
        while proc.poll() is None:
            if self.stopping.is_set() or time.time() > deadline:
                timed_out = not self.stopping.is_set()
                kill_group(proc)
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
        code = proc.wait()
        self.procs.discard(proc)
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
        holder = []
        try:
            wanted = [x for x in args if x.startswith("//") and ":" in x]
            with open(log_path, "w") as log:
                code, timed_out = self.invoke(rec, args, env, key, log, log_path, deadline, holder)
            with open(log_path, errors="replace") as f:
                text = f.read()
            targets = target_results(text, set(wanted))
            infra = []
            if rec["step"] in ("subset", "batch") and not self.stopping.is_set() and not timed_out:
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
                        start, began = log.tell(), time.time()
                        code2, timed_out = self.invoke(rec, retry, env, key, log, log_path, deadline, holder)
                    with open(log_path, errors="replace") as f:
                        f.seek(start)
                        again = target_results(f.read(), set(infra))
                    infra = retry_outcome(targets, infra, again, code2, timed_out or self.stopping.is_set(),
                                          lambda t: test_xml(output_base, t, since=began))
                    # The step's exit: failed if any real failure is left.
                    real = [t for t in wanted if not is_pass(targets.get(t)) and targets.get(t) != INFRA]
                    code = 0 if not real else (code if code in (1, 3) else 3)
                for t in infra:
                    targets[t] = INFRA
                targets = {t: st for t, st in targets.items() if st is not None}
            if timed_out or self.stopping.is_set():
                # The Bazel server may still run the build; stop it.
                subprocess.run([cfg["bazel"], "--output_base=" + output_base, "shutdown"],
                               cwd=self.work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300)
            with open(log_path, errors="replace") as f:
                text = f.read()
            rec.update(exit_code=code, invocations=invocation_links(text), targets=targets, infra=infra)
            if rec["step"] in ("subset", "batch"):
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
            p = holder[0] if holder else None
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
            rec["end"] = now()

    def stop(self):
        self.stopping.set()
        for p in list(self.procs):
            if p.poll() is None:
                threading.Thread(target=kill_group, args=(p,), daemon=True).start()


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

CSS = "body{font-family:sans-serif;margin:16px;background:#fff;color:#000} table{border-collapse:collapse;margin-bottom:16px} " \
      "td,th{border:1px solid #ccc;padding:3px 6px;text-align:left;vertical-align:top} " \
      ".yes,.pass{color:#1a7f37} .no,.regression{color:#cf222e;font-weight:bold} .fail{color:#9a3412} " \
      ".pending,.na,.running,.infra,.flaky,.small{color:#777} .small{font-size:85%}"
MARK = {"yes": "&#10003;", "no": "&#10007;", "pending": "pending", "n/a": "n/a", "running": "running"}
PMARK = {"pass": "&#10003;", "flaky": "flaky", "regression": "&#10007;", "fail": "&#10007;", "infra": "infra",
         "running": "running", "pending": "pending"}


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


def column_targets(projects, tier_of, col):
    """{tier: [targets]} the column runs."""
    out = {1: [], 2: [], 3: []}
    for tier, _, names in batches(projects, tier_of, arch_of(col), 10 ** 6):
        out[tier] += ["//%s:test" % n for n in names]
    return out


def tally_html(c, label=True):
    """ "N/M ok" with the non-zero other counts; regressions red."""
    if not c["total"]:
        return '<span class="na">none</span>'
    parts = ["%d/%d ok" % (c["ok"], c["total"])]
    if c["regression"]:
        parts.append('<span class="regression">%d regression%s</span>' % (c["regression"], "s" if c["regression"] > 1 else ""))
    for k, name in (("fail", "failing"), ("flaky", "flaky"), ("infra", "infra"), ("running", "running"),
                    ("pending", "pending")):
        if c[k]:
            parts.append('<span class="%s">%d %s</span>' % (k if k != "fail" else "fail", c[k], name))
    return ", ".join(parts)


def batch_minutes(runs, rev):
    """Median minutes of this rev's finished batches, None without any."""
    mins = []
    for r in runs:
        if r["step"] == "batch" and r.get("rev") == rev and r["status"] in DONE and r.get("end"):
            try:
                mins.append((datetime.datetime.fromisoformat(r["end"]) -
                             datetime.datetime.fromisoformat(r["start"])).total_seconds() / 60)
            except (TypeError, ValueError):
                pass
    return sorted(mins)[len(mins) // 2] if mins else None


def etas(cfg, runs, info, lives):
    """{(column name, ref, arch, tier): "~HH:MM UTC"}: when the tier's last
    batch on the column should end, at the median batch time (45 min until
    one has finished) per remaining group, groups one after another."""
    rev = current_rev(runs)
    cycle = max([r["cycle"] for r in runs] or [0])
    per = batch_minutes(runs, rev) or 45.0
    t = datetime.datetime.now(datetime.timezone.utc)
    out = {}
    running = {(r["image"]["name"], r["image"]["ref"], arch_of(r["image"]), tuple(r.get("subset") or [])) for r in lives}
    for group in schedule(cfg, *info):
        todo = [x for x in remaining(runs, group, rev, cycle) if x[1] == "batch"]
        if not todo:
            continue
        live = any((c["name"], c["ref"], arch_of(c), tuple(b[2])) in running for c, _, b in todo)
        t += datetime.timedelta(minutes=per / 2 if live else per)
        for c, _, b in todo:
            out[(c["name"], c["ref"], arch_of(c), b[0])] = t.strftime("~%H:%M UTC")
    return out


def render(cfg, runs, lives=(), info=None):
    images = cfg["images"]
    cols = columns(images)
    cands = [c for c in cols if c.get("role") == "candidate"]
    lives = list(lives)
    projects, tier_of = info or ([], {})
    targets = {id(c): column_targets(projects, tier_of, c) for c in cands}
    tables = {id(c): project_table(cfg, runs, c, [t for ts in targets[id(c)].values() for t in ts], lives)
              for c in cands}
    eta = etas(cfg, runs, info, lives) if info else {}
    out = ['<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="60">',
           "<title>RBE image canary</title><style>%s</style></head><body>" % CSS,
           "<h1>RBE image canary</h1>",
           "<p>Candidate images vs. today's images on BuildBuddy RBE. Every project in projects.txt that "
           "isn't known-failing runs as //&lt;p&gt;:test with its inner Bazel on an RBE executor in the image "
           "under test (--config=inner-remote). A regression is a candidate failure of a project that passes "
           "on the reference: the baseline image's run, or (22.04 amd64, until its baseline runs) the "
           "matrix's own record. Tiers: see details.</p>",
           "<h2>Summary</h2><table><tr><th>Image</th><th>eMudhra protected</th>%s<th>reference</th></tr>" % "".join(
               "<th>%s</th>" % esc(TIER_NAMES[t]) for t in (1, 2, 3))]
    for c in cands:
        digest = c["ref"].rsplit("@sha256:", 1)[-1][:12]
        others = probe_others(runs, c)
        note = ("<br><span class=\"no\" title=\"%s\">probe: %d other checks fail</span>" % (
            esc("; ".join(others)), len(others))) if others else ""
        out.append('<tr><td>%s &middot; %s<br><code title="%s">%s</code>%s</td>' % (
            esc(c.get("release")), esc(arch_of(c)), esc(c["ref"]), esc(digest), note))
        state, why, pr = protected(runs, c)
        out.append(cell(state, "", first_link(pr), "; ".join(why)))
        table = tables[id(c)]
        for tier in (1, 2, 3):
            ts = targets[id(c)][tier]
            n = tally(table, ts)
            regs = [t[2:-5] for t in ts if t in table and kind(table[t][0], table[t][1]) == "regression"]
            e = eta.get((c["name"], c["ref"], arch_of(c), tier))
            out.append('<td title="%s">%s%s</td>' % (
                esc(("regressions: " + ", ".join(regs)) if regs else ""), tally_html(n),
                ('<br><span class="small">ETA %s</span>' % esc(e)) if e and (n["pending"] or n["running"]) else ""))
        out.append("<td>%s</td></tr>" % esc(ref_label(table) if table else ""))
    out.append("</table>")
    # Per ruleset.
    out.append("<h2>Popular rulesets</h2><p class=\"small\">Each ruleset and a few small dependents "
               "(GROUPS in server.py); same counts as above.</p><table><tr><th>Image</th>%s</tr>" % "".join(
                   "<th>%s</th>" % esc(g) for g in GROUPS))
    for c in cands:
        table = tables[id(c)]
        out.append("<tr><td>%s &middot; %s</td>" % (esc(c.get("release")), esc(arch_of(c))))
        for g, members in GROUPS.items():
            ts = ["//%s:test" % p for p in members if "//%s:test" % p in table]
            if not ts:
                out.append('<td><span class="na">n/a</span></td>')
                continue
            n = tally(table, ts)
            st = "no" if n["regression"] else ("yes" if n["ok"] == n["total"] else "pending")
            bad = [t[2:-5] for t in ts if kind(table[t][0], table[t][1]) not in ("pass", "flaky")]
            out.append('<td title="%s"><span class="%s">%s</span> %s</td>' % (
                esc(", ".join("%s: %s" % (t, kind(table["//%s:test" % t][0], table["//%s:test" % t][1])) for t in bad)),
                st, MARK[st], tally_html(n)))
        out.append("</tr>")
    out.append("</table>")
    # Per project.
    if cands and projects:
        rows = sorted({t for c in cands for t in tables[id(c)]})

        def rank(t):
            ks = [kind(tables[id(c)][t][0], tables[id(c)][t][1]) for c in cands if t in tables[id(c)]]
            return (0 if "regression" in ks else 1 if "fail" in ks else 2 if "infra" in ks else 3,
                    tier_of.get(t[2:-5], (3,))[0], t)

        rows.sort(key=rank)
        out.append("<h2>Projects</h2><p class=\"small\">Regressions first, then failures, then infra, then the rest "
                   "(by tier). Each cell: the candidate's result (linked to its invocation), then the "
                   "reference's.</p><table><tr><th>Project</th><th>tier</th>%s</tr>" % "".join(
                       "<th>%s &middot; %s</th>" % (esc(c.get("release")), esc(arch_of(c))) for c in cands))
        for t in rows:
            name = t[2:-5]
            tier, why = tier_of.get(name, (3, ""))
            out.append('<tr><td>%s</td><td title="%s">%d</td>' % (esc(name), esc(why), tier))
            for c in cands:
                v = tables[id(c)].get(t)
                if v is None:
                    out.append('<td class="na">-</td>')
                    continue
                ref, st, r = v
                k = kind(ref, st)
                body = '<span class="%s">%s</span>' % (k, PMARK[k])
                if r is not None and k not in ("pending",):
                    body = '<a href="%s">%s</a>' % (esc(first_link(r)), body)
                refs = ("matrix &#10003;" if ref == MATRIX else "base pending" if ref == NO_BASELINE
                        else "base " + ("&#10003;" if ref == "PASSED" else esc(ref.lower())))
                out.append('<td title="%s">%s <span class="small">%s</span></td>' % (esc(st or ""), body, refs))
            out.append("</tr>")
        out.append("</table>")
    det = ["<p>%s</p>" % esc(TIER_HEURISTIC)]
    if info:
        sizes = {}
        for n, (tier, _) in tier_of.items():
            sizes[tier] = sizes.get(tier, 0) + 1
        det.append("<p>Tier sizes: %s; batches of %d projects, --jobs=%d, amd64 and arm64 of an image at once.</p>" % (
            esc(", ".join("tier %d: %d" % (t, sizes.get(t, 0)) for t in (1, 2, 3))), int(cfg.get("batch_size", 150)),
            int(cfg.get("jobs", 100))))
    for cur in lives:
        det.append('<p>Running: %s %s %s%s, %s, %d/%d done. <a href="/logs/%s?tail=200">log</a></p>' % (
            esc(cur["image"]["name"]), esc(arch_of(cur["image"])), esc(cur["step"]),
            (" tier %s batch %s" % (cur.get("tier"), cur.get("batch"))) if cur.get("tier") else "",
            elapsed(cur["start"]), len(cur.get("targets") or {}), len(cur.get("subset") or [1]), esc(cur["log"])))
    det.append("<p>Baselines:</p><ul>")
    rev = current_rev(runs)
    for b in cols:
        if b.get("role") == "baseline":
            pr = latest_complete(runs, b, "probe")
            res = project_results(runs, b, rev, lives)
            det.append('<li>%s %s <code>%s</code>: probe %s%s, projects %d/%d passed</li>' % (
                esc(b["name"]), esc(arch_of(b)), esc(b["ref"].rsplit("@sha256:", 1)[-1][:12]),
                esc(pr["status"]) if pr else "none", (' <a href="%s">link</a>' % esc(first_link(pr))) if pr else "",
                sum(1 for st, _ in res.values() if is_pass(st)), len(res)))
    det.append("</ul><p>Recent runs:</p><table>")
    for r in list(reversed(runs))[:60]:
        det.append('<tr><td>%s</td><td>%s %s</td><td>%s%s</td><td>%s</td><td>%s%s</td><td><a href="/logs/%s">log</a>'
                   '%s</td></tr>' % (
                       esc(r["cycle"]), esc(r["image"]["name"]), esc(arch_of(r["image"])), esc(r["step"]),
                       (" t%s/%s" % (r.get("tier"), r.get("batch"))) if r.get("tier") else "",
                       esc(r["start"]), esc(r["status"]), (" (%s)" % esc(r["error"])) if r.get("error") else "",
                       esc(r["log"]), "".join(' <a href="%s">invocation</a>' % esc(u) for u in r.get("invocations") or [])))
    det.append("</table>")
    out.append("<details><summary>details</summary>%s</details></body></html>" % "".join(det))
    return "".join(out)


def repo_info(root):
    """(projects, tiers) from a checkout (the page's fallback before the runner has read its clone)."""
    try:
        with open(os.path.join(root, "projects.txt")) as f:
            projects = parse_projects(f.read())
        with open(os.path.join(root, "canary", "deps.json")) as f:
            deps = json.load(f)
    except OSError:
        return None
    return projects, tiers([p["name"] for p in projects if not p["known_failing"]], deps)


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
                    lives = list(runner.currents.values()) if runner else []
                    info = (runner.info if runner else None) or repo_info(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    self.send(200, render(cfg, store.runs(), lives, info), "text/html")
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
    ap.add_argument("--write-deps", metavar="BCR_DIR",
                    help="write canary/deps.json from a BCR checkout at projects.json's bcr_commit, then exit")
    args = ap.parse_args(argv)
    if args.write_deps:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        write_deps(args.write_deps, os.path.join(root, "projects.json"), os.path.join(root, "canary", "deps.json"))
        return
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
    pidfile = os.path.join(args.data_dir, "server.pid")
    with open(pidfile, "w") as f:
        f.write("%d\n" % os.getpid())  # for canary/restart.sh
    print("serving on http://%s:%d" % (args.host, args.port), file=sys.stderr)
    server.serve_forever()
    server.server_close()
    try:
        with open(pidfile) as f:
            if f.read().strip() == str(os.getpid()):
                os.remove(pidfile)
    except OSError:
        pass
    # Hold the work dir's lock (this process) until the running step and its
    # Bazel shutdown are done: a 30 s kill grace plus a 300 s shutdown.
    runner.join(900)


if __name__ == "__main__":
    main()
