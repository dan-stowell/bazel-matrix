import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

import server

ROOT = os.path.join(os.environ.get("TEST_SRCDIR", ""), os.environ.get("TEST_WORKSPACE", ""))
ESC = "\x1b"

# Abridged `bazel test` output with ANSI colors; //re2:test's log embeds its
# inner Bazel's summary.
LOG = """
{e}[32mINFO: {e}[mStreaming build results to: {e}[36mhttps://buildbuddy.buildbuddy.io/invocation/4e88c7fc-6514-4c26-9796-a1fdc3bc4b48
==================== Test output for //re2:test:
//re2:inner_test                                          PASSED in 1.0s
//zlib:test                                               PASSED in 1.0s
Executed 1 out of 1 test: 1 test passes.
================================================================================
{e}[32mINFO: {e}[mFound 3 test targets...
{e}[32mINFO: {e}[mElapsed time: 23.067s, Critical Path: 4.47s
{e}[32mINFO: {e}[m146 processes: 23 remote cache hit, 123 internal.
{e}[32mINFO: {e}[mBuild completed, 1 test FAILED, 146 total actions
//abseil-cpp:test                                     {e}[32m(cached) PASSED{e}[0m in 48.1s
//re2:test                                            {e}[31m{e}[1mFAILED{e}[0m in 67.9s
  /home/x/.cache/bazel/execroot/re2/test/test.log
//rules_go:test                                       {e}[31m{e}[1mFAILED TO BUILD{e}[0m

Executed 1 out of 3 tests: 1 test passes, 1 fails locally and 1 was skipped.
{e}[32mINFO: {e}[mStreaming build results to: {e}[36mhttps://buildbuddy.buildbuddy.io/invocation/4e88c7fc-6514-4c26-9796-a1fdc3bc4b48
""".format(e=ESC)

WANTED = {"//abseil-cpp:test", "//re2:test", "//rules_go:test"}


class ParseTest(unittest.TestCase):
    def test_invocation_links(self):
        self.assertEqual(server.invocation_links(LOG),
                         ["https://buildbuddy.buildbuddy.io/invocation/4e88c7fc-6514-4c26-9796-a1fdc3bc4b48"])
        self.assertEqual(server.invocation_links(
            "Streaming build results to: javascript:alert(1)//invocation/abcd\n"), [])

    def test_target_results_only_outer_summary(self):
        self.assertEqual(server.target_results(LOG, WANTED), {
            "//abseil-cpp:test": "PASSED", "//re2:test": "FAILED", "//rules_go:test": "FAILED TO BUILD"})
        # A killed run ends with a project's inner summary: unrequested labels are dropped.
        cut = LOG[:LOG.index("================================================================================")]
        self.assertEqual(server.target_results(cut, WANTED), {})
        self.assertEqual(server.target_results("ERROR: no such package\n", WANTED), {})

    def test_classify(self):
        self.assertEqual(server.classify(0), "passed")
        self.assertEqual(server.classify(3), "failed")
        self.assertEqual(server.classify(1), "failed")
        for code in (2, 4, 8, 34, 37):
            self.assertEqual(server.classify(code), "error")

    def test_redact(self):
        self.assertEqual(server.redact("key=s3cr3t", "s3cr3t"), "key=<REDACTED>")
        self.assertEqual(server.redact("text", ""), "text")
        out = io.StringIO()
        server.copy_redacted(io.BytesIO(b"a KEY b\nc\n"), out, "KEY")
        self.assertEqual(out.getvalue(), "a <REDACTED> b\nc\n")


PROBE_LOG = """
==================== Test output for //canary:tls_probe_test:
tls_probe: Ubuntu 22.04, CANARY_EXPECT=distrusted, host abc
PASS    tools: found /bin/curl
PASS    trust_store/bundle: removed 4 (emSign Root CA - G1, ...), added 0
PASS    emudhra/fixture: rejected
FAIL    emudhra/online/www.internet2.edu/curl: still verifies
NETERR  host/pypi.org/curl: timeout

=== tls_probe summary (CANARY_EXPECT=distrusted): 5 checks, 3 PASS, 1 FAIL, 1 NETERR, 1s
  FAIL    emudhra/online/www.internet2.edu/curl: still verifies
================================================================================
"""


class ProbeTest(unittest.TestCase):
    def test_complete(self):
        got = server.probe_result(PROBE_LOG)
        self.assertEqual(got["expect"], "distrusted")
        self.assertEqual(got["total"], 5)
        self.assertEqual(got["checks"]["emudhra/online/www.internet2.edu/curl"], ["FAIL", "still verifies"])
        self.assertEqual(got["checks"]["host/pypi.org/curl"][0], "NETERR")
        self.assertTrue(server.is_emudhra("emudhra/fixture") and not server.is_emudhra("trust_store/bundle"))

    def test_partial_is_none(self):
        # Crashed before the summary.
        self.assertIsNone(server.probe_result(PROBE_LOG[:PROBE_LOG.index("=== tls_probe")]))
        # Summary counts a check that wasn't printed.
        self.assertIsNone(server.probe_result(PROBE_LOG.replace("PASS    tools: found /bin/curl\n", "")))
        # A simulated distrust, or a probe cut short by its deadline.
        self.assertIsNone(server.probe_result(PROBE_LOG.replace("distrusted):", "distrusted, simulated):")))
        self.assertIsNone(server.probe_result(PROBE_LOG.replace("PASS    tools: found /bin/curl", "FAIL    deadline: hit")))
        # Another target's output doesn't count.
        self.assertIsNone(server.probe_result(PROBE_LOG.replace("//canary:tls_probe_test", "//x:y")))


class RewriteTest(unittest.TestCase):
    REF = "docker://gcr.io/flame-public/rbe-ubuntu24-04@sha256:" + "a" * 64

    def setUp(self):
        with open(os.path.join(ROOT, "tools", "remote.bazelrc")) as f:
            self.rc = f.read()

    def test_rewrites_only_the_image(self):
        new = server.rewrite_image(self.rc, self.REF)
        diff = [(a, b) for a, b in zip(self.rc.splitlines(), new.splitlines()) if a != b]
        self.assertEqual(len(diff), 1)
        self.assertTrue(diff[0][1].endswith("container-image=" + self.REF))
        self.assertEqual(re.findall(r"container-image=[^ \n]*", new), ["container-image=" + self.REF])

    def test_rejects(self):
        with self.assertRaises(ValueError):
            server.rewrite_image(self.rc, "docker://gcr.io/flame-public/rbe-ubuntu24-04:latest")
        with self.assertRaises(ValueError):
            server.rewrite_image("common --jobs=1\n", self.REF)


IMAGES = [
    {"name": "b", "ref": "rb", "role": "baseline", "release": "22.04", "archs": ["amd64"]},
    {"name": "c", "ref": "rc", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
]
COLS = server.columns(IMAGES)
CFG = {"subset": {"22.04": ["a", "b"]}, "images": IMAGES}

_n = [0]


def run(col, step, status, targets=None, checks=None, expect="distrusted", rev="r1", subset=("a", "b")):
    _n[0] += 1
    r = {"id": "%d" % _n[0], "cycle": 1, "image": dict(col), "step": step, "start": "%05d" % _n[0],
         "end": "x", "status": status, "targets": targets or {}, "invocations": [], "log": "x.log", "rev": rev}
    if step == "probe":
        r["probe"] = {"expect": expect, "total": len(checks or {}), "checks": checks or {}} if checks is not None else None
    else:
        r["subset"] = list(subset)
    return r


GOOD = {"emudhra/fixture": ["PASS", "rejected"], "host/x": ["PASS", "ok"],
        "trust_store/bundle": ["PASS", "removed 4"]}
BASE_SUB = {"//a:test": "PASSED", "//b:test": "FAILED"}


def builds(cfg, runs, images, col, group=("a", "b"), live=None):
    return server.group_cell(cfg, server.compare_subset(cfg, runs, images, col, live), list(group))[:4]


class VerdictTest(unittest.TestCase):
    def test_yes(self):
        b, c = COLS
        runs = [run(b, "probe", "passed", checks=GOOD, expect="trusted"), run(c, "probe", "passed", checks=GOOD),
                run(b, "subset", "failed", BASE_SUB), run(c, "subset", "failed", BASE_SUB)]
        self.assertEqual(server.protected(runs, c)[:2], ("yes", []))
        # //b:test fails on the baseline too: not counted.
        self.assertEqual(builds(CFG, runs, IMAGES, c), ("yes", 1, 1, []))
        self.assertEqual(server.probe_others(runs, c), [])

    def test_no(self):
        b, c = COLS
        bad = dict(GOOD, **{"emudhra/fixture": ["FAIL", "still verifies"], "host/x": ["FAIL", "curl 60"]})
        runs = [run(c, "probe", "passed", checks=bad), run(b, "subset", "passed", {"//a:test": "PASSED", "//b:test": "PASSED"}),
                run(c, "subset", "failed", {"//a:test": "FAILED", "//b:test": "PASSED"})]
        self.assertEqual(server.protected(runs, c)[:2], ("no", ["emudhra/fixture: still verifies"]))
        self.assertEqual(builds(CFG, runs, IMAGES, c), ("no", 1, 2, ["//a:test"]))
        self.assertEqual(builds(CFG, runs, IMAGES, c, group=["b"]), ("yes", 1, 1, []))
        self.assertEqual(builds(CFG, runs, IMAGES, c, group=["zzz"])[0], "n/a")
        self.assertEqual(server.probe_others(runs, c), ["FAIL host/x: curl 60"])

    def test_pending(self):
        b, c = COLS
        # Nothing yet.
        self.assertEqual(server.protected([], c)[0], "pending")
        self.assertEqual(builds(CFG, [], IMAGES, c)[0], "pending")
        self.assertIsNone(server.probe_others([], c))
        # An interrupted probe, or one without a complete summary, proves nothing.
        runs = [run(c, "probe", "interrupted", checks=GOOD), run(c, "probe", "error", checks=None)]
        self.assertEqual(server.protected(runs, c)[0], "pending")
        # A NETERR eMudhra check is pending, not yes.
        runs = [run(c, "probe", "failed", checks=dict(GOOD, **{"emudhra/x": ["NETERR", "timeout"]}))]
        self.assertEqual(server.protected(runs, c)[0], "pending")
        # A missing target result, a baseline at another revision, an older
        # subset config, or another digest: pending.
        probes = [run(c, "probe", "passed", checks=GOOD)]
        for runs in (
            [run(b, "subset", "passed", BASE_SUB), run(c, "subset", "failed", {"//a:test": "PASSED"})],
            [run(b, "subset", "passed", BASE_SUB), run(c, "subset", "failed", BASE_SUB, subset=("a",))],
            [run(c, "subset", "interrupted", BASE_SUB)],
        ):
            self.assertEqual(builds(CFG, probes + runs, IMAGES, c)[0], "pending", runs)
        # Without a complete baseline run at the same revision and digest:
        # the candidate's counts, but no verdict.
        for runs in (
            [run(b, "subset", "passed", BASE_SUB, rev="r0"), run(c, "subset", "failed", BASE_SUB)],
            [run(dict(b, ref="old"), "subset", "passed", BASE_SUB), run(c, "subset", "failed", BASE_SUB)],
            [run(b, "subset", "interrupted", BASE_SUB), run(c, "subset", "failed", BASE_SUB)],
        ):
            self.assertEqual(builds(CFG, probes + runs, IMAGES, c), ("pending", 1, 2, [server.NO_BASELINE]), runs)
        # A NO STATUS baseline target doesn't excuse a candidate failure and
        # isn't counted: only baseline passes are the reference.
        runs = probes + [run(b, "subset", "failed", {"//a:test": "NO STATUS", "//b:test": "PASSED"}),
                         run(c, "subset", "failed", {"//a:test": "FAILED", "//b:test": "PASSED"})]
        self.assertEqual(builds(CFG, runs, IMAGES, c), ("yes", 1, 1, []))

    def test_live(self):
        b, c = COLS
        base = [run(b, "subset", "passed", {"//a:test": "PASSED", "//b:test": "PASSED"})]
        cur = run(c, "subset", "running", {"//a:test": "PASSED"})
        got = server.group_cell(CFG, server.compare_subset(CFG, base, IMAGES, c, cur), ["a", "b"])
        self.assertEqual(got, ("running", 1, 2, ["running: //b:test"], 1))
        # No baseline yet: running, with the counts so far.
        self.assertEqual(server.group_cell(CFG, server.compare_subset(CFG, [], IMAGES, c, cur), ["a", "b"]),
                         ("running", 1, 2, [server.NO_BASELINE], 1))
        # Every target done, but no final summary yet: still not green.
        cur["targets"]["//b:test"] = "PASSED"
        self.assertEqual(server.group_cell(CFG, server.compare_subset(CFG, base, IMAGES, c, cur), ["a", "b"])[0],
                         "running")
        cur["targets"]["//b:test"] = "FAILED"
        self.assertEqual(server.group_cell(CFG, server.compare_subset(CFG, base, IMAGES, c, cur), ["a", "b"])[0], "no")

    def test_no_tests(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for pkg, xml in (("a", '<testcase name="no tests"><skipped message="NO_TESTS"/></testcase>'),
                         ("b", '<testcase name="//x:y_test"/>')):
            path = os.path.join(d, "execroot/_main/bazel-out/k8-fastbuild/testlogs", pkg, "test")
            os.makedirs(path)
            with open(os.path.join(path, "test.xml"), "w") as f:
                f.write(xml)
        self.assertEqual(server.no_tests(d, ["//a:test", "//b:test", "//c:test"]), ["//a:test"])

    def test_infra(self):
        b, c = COLS
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for pkg, xml in (("a", '<testcase name="infra_killed"/>'), ("b", '<testcase name="wrapper_error"/>'),
                         ("c", '<testcase name="//x:y_test"><failure/></testcase>')):
            path = os.path.join(d, "execroot/_main/bazel-out/aarch64-fastbuild/testlogs", pkg, "test")
            os.makedirs(path)
            with open(os.path.join(path, "test.xml"), "w") as f:
                f.write(xml)
        self.assertEqual(server.infra_killed(d, ["//a:test", "//b:test", "//c:test", "//d:test"]),
                         ["//a:test", "//b:test"])
        # An infra kill on the candidate isn't a failure; on the baseline it
        # doesn't excuse the candidate.
        runs = [run(b, "subset", "failed", {"//a:test": "PASSED", "//b:test": "INFRA"}),
                run(c, "subset", "failed", {"//a:test": "INFRA", "//b:test": "FAILED"})]
        got = server.group_cell(CFG, server.compare_subset(CFG, runs, IMAGES, c), ["a", "b"])
        self.assertEqual(got[0], "pending")
        runs = [run(b, "subset", "passed", {"//a:test": "PASSED", "//b:test": "PASSED"}),
                run(c, "subset", "failed", {"//a:test": "INFRA", "//b:test": "PASSED"})]
        got = server.group_cell(CFG, server.compare_subset(CFG, runs, IMAGES, c), ["a", "b"])
        self.assertEqual(got[:3], ("yes", 1, 1))
        self.assertIn("infra (not counted): //a:test", got[3])

    def test_retry_outcome(self):
        targets = {"//a:test": "FAILED", "//b:test": "FAILED", "//c:test": "FAILED", "//d:test": "FAILED"}
        again = {"//a:test": "PASSED", "//b:test": "FAILED", "//c:test": "FAILED"}
        xml = {"//b:test": '<testcase name="//x:y"><failure/></testcase>', "//c:test": '<testcase name="infra_killed"/>'}
        left = server.retry_outcome(targets, ["//a:test", "//b:test", "//c:test", "//d:test"], again, 3, False,
                                    lambda t: xml.get(t, ""))
        # Passed only on the retry: flaky. A fresh real failure: failed. Killed
        # again, or no fresh result: infra.
        self.assertEqual(targets["//a:test"], "FLAKY")
        self.assertEqual(targets["//b:test"], "FAILED")
        self.assertEqual(left, ["//c:test", "//d:test"])
        # A retry that failed before running tests (exit 2, 37, ...) proves nothing.
        targets = {"//b:test": "FAILED"}
        self.assertEqual(server.retry_outcome(targets, ["//b:test"], {"//b:test": "FAILED"}, 37, False,
                                              lambda t: xml.get(t, "")), ["//b:test"])
        self.assertEqual(server.retry_outcome(targets, ["//a:test"], {"//a:test": "PASSED"}, 0, True,
                                              lambda t: ""), ["//a:test"])

    def test_baseline_infra_is_unknown(self):
        b, c = COLS
        runs = [run(b, "subset", "failed", {"//a:test": "INFRA", "//b:test": "PASSED"}),
                run(c, "subset", "failed", {"//a:test": "FAILED", "//b:test": "PASSED"})]
        got = server.group_cell(CFG, server.compare_subset(CFG, runs, IMAGES, c), ["a", "b"])
        self.assertEqual(got[:3], ("pending", 1, 2))
        self.assertIn("unknown (baseline infra): //a:test", got[3])
        got = server.group_cell(CFG, server.compare_subset(CFG, runs, IMAGES, c), ["a"])
        self.assertEqual(got[:3], ("pending", 0, 1))

    def test_live_bazel(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for pid, argv in (("1", ["bazel", "--output_base=/o/amd64-inner", "test"]),
                          ("2", ["bazel(work)", "--output_base=/o/arm64"]),
                          ("3", ["bazel", "--output_base=/elsewhere", "test"]), ("x", ["junk"])):
            os.makedirs(os.path.join(d, pid))
            with open(os.path.join(d, pid, "cmdline"), "wb") as f:
                f.write("\0".join(argv).encode())
        self.assertEqual(server.live_bazel("/o", proc=d), ["/o/amd64-inner"])

    def test_bep(self):
        lines = [json.dumps({"id": {"testResult": {"label": "//a:test", "run": 1}}, "testResult": {"status": "FAILED"}}),
                 json.dumps({"id": {"testSummary": {"label": "//a:test"}}, "testSummary": {"overallStatus": "FLAKY"}}),
                 json.dumps({"id": {"testResult": {"label": "//x:y"}}, "testResult": {"status": "PASSED"}}),
                 "{truncated"]
        self.assertEqual(server.bep_results(lines, {"//a:test"}), {"//a:test": "FLAKY"})

    def test_newest_run_decides(self):
        b, c = COLS
        # An older success doesn't stand in for a newer run that didn't finish.
        runs = [run(c, "probe", "passed", checks=GOOD), run(c, "probe", "error", checks=None)]
        state, why, _ = server.protected(runs, c)
        self.assertEqual(state, "pending")
        self.assertTrue(why[0].startswith("last: error (incomplete), "), why)
        runs = [run(b, "subset", "passed", BASE_SUB), run(c, "subset", "passed", BASE_SUB),
                run(c, "subset", "timeout", {})]
        self.assertEqual(builds(CFG, runs, IMAGES, c)[0], "pending")
        # Results from an older repo revision than the current cycle's: pending.
        runs = [run(c, "probe", "passed", checks=GOOD, rev="r0"), run(b, "probe", "passed", checks=GOOD, rev="r1")]
        self.assertEqual(server.protected(runs, c)[0], "pending")

    def test_not_covered(self):
        c = COLS[1]
        runs = [run(c, "probe", "passed", checks=GOOD)]
        self.assertEqual(builds({"subset": {}}, runs, IMAGES, c)[0], "n/a")


class ScheduleTest(unittest.TestCase):
    def test_order_and_commands(self):
        images = [
            {"name": "b22", "ref": "r", "role": "baseline", "release": "22.04"},
            {"name": "c22", "ref": "r", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
        ]
        cfg = {"images": images, "subset": {"22.04": ["zlib"], "22.04/arm64": ["rules_go"]},
               "salt_inner": True, "bazel": "bazel", "output_root": "/out"}
        got = [(c["name"], c["arch"], step) for c, step in server.schedule(cfg)]
        self.assertEqual(got, [
            ("c22", "amd64", "probe"), ("c22", "amd64", "subset"), ("b22", "amd64", "probe"),
            ("b22", "arm64", "probe"), ("b22", "amd64", "subset"), ("b22", "arm64", "subset"),
        ])
        runner = server.Runner("/nonexistent", "/w", None)
        rbe = ["--config=remote-minimal", "--credential_helper=*.buildbuddy.io=/w/tools/buildbuddy_credential_helper.py",
               "--nocache_test_results"]
        arm = dict(images[0], arch="arm64")
        self.assertEqual(runner.command(cfg, 7, arm, "probe"), [
            "bazel", "--output_base=/out/arm64", "test", "//canary:tls_probe_test"] + rbe + [
            "--remote_default_exec_properties=Arch=arm64", "--test_output=all", "--test_env=CANARY_EXPECT=trusted"])
        self.assertIn("--test_env=CANARY_EXPECT=distrusted",
                      runner.command(cfg, 7, dict(images[1], arch="amd64"), "probe"))
        inner = ["--credential_helper=*.buildbuddy.io=/w/tools/remote_exec_credential_helper.py",
                 "--nocache_test_results", "--flaky_test_attempts=2", "--remote_download_regex=.*/testlogs/.*/test\\.xml$"]
        self.assertEqual(runner.command(cfg, 7, dict(images[0], arch="amd64"), "subset"), [
            "bazel", "--output_base=/out/amd64-inner", "test", "//zlib:test", "--config=remote-minimal",
            "--config=inner-remote"] + inner + [
            "--build_event_json_file=/out/bep-amd64.json", "--//:inner_flags=--remote_instance_name=canary-7"])
        self.assertEqual(runner.command(cfg, 7, arm, "subset"), [
            "bazel", "--output_base=/out/arm64-inner", "test", "//rules_go:test", "--config=remote-minimal",
            "--config=inner-remote-arm64"] + inner + [
            "--build_event_json_file=/out/bep-arm64.json", "--//:inner_flags=--remote_instance_name=canary-7"])
        self.assertIsNone(runner.command(dict(cfg, subset={}), 7, arm, "subset"))

    def test_kill_group(self):
        import subprocess
        p = subprocess.Popen(["sh", "-c", "trap '' INT; sleep 60 & wait"], start_new_session=True)
        time.sleep(0.5)
        t0 = time.time()
        server.kill_group(p, grace=1)
        self.assertEqual(p.wait(10), -9)
        self.assertLess(time.time() - t0, 10)
        server.kill_group(p)  # already reaped: a no-op

    def test_key_file(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        path = server.Runner("/x", "/w", None).key_file({"output_root": d}, "KEY")
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), "0o600")
        with open(path) as f:
            self.assertEqual(f.read(), "KEY")


class ResolveBazelTest(unittest.TestCase):
    def test_explicit(self):
        self.assertEqual(server.resolve_bazel({"bazel": "/x/bazel"}, "/nonexistent"), "/x/bazel")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_seed(self):
        cfg = server.load_config(self.dir)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "config.json")))
        self.assertEqual(cfg["repo_branch"], "canary-server")
        self.assertEqual(sorted(cfg["subset"]), ["22.04", "22.04/arm64", "24.04", "24.04/arm64"])
        self.assertEqual([(i["release"], i["role"]) for i in cfg["images"]],
                         [("22.04", "baseline"), ("22.04", "candidate"), ("24.04", "baseline"),
                          ("24.04", "candidate")])
        for im in cfg["images"]:
            server.rewrite_image("--remote_default_exec_properties=container-image=x\n", im["ref"])

    def test_seed_22_04_is_remote_bazelrc(self):
        with open(os.path.join(ROOT, "tools", "remote.bazelrc")) as f:
            self.assertIn("container-image=" + server.BASELINE_2204 + "\n", f.read())

    def test_defaults_merge(self):
        path = os.path.join(self.dir, "config.json")
        with open(path, "w") as f:
            json.dump({"images": [], "subset": {"9.9": ["x"]}}, f)
        orig = server.SUBSETS
        server.SUBSETS = {"22.04": ["zlib"]}
        try:
            got = server.load_config(self.dir)
        finally:
            server.SUBSETS = orig
        self.assertEqual(got["subset"], {"22.04": ["zlib"], "9.9": ["x"]})
        self.assertTrue(got["salt_inner"])


class StoreAndUiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.store = server.Store(self.dir)

    def test_interrupted_and_compact(self):
        b = COLS[0]
        for i in range(5):
            r = run(b, "subset", "running")
            r["log"] = "l%d.log" % i
            self.store.append(r)
            if i < 4:
                r["status"] = "passed"
                self.store.append(r)
        self.store.mark_interrupted()
        self.assertEqual([r["status"] for r in self.store.runs()], ["passed"] * 4 + ["interrupted"])
        for name in ("l0.log", "old.log", "new.log"):
            with open(os.path.join(self.dir, "logs", name), "w") as f:
                f.write("x")
        os.utime(os.path.join(self.dir, "logs", "old.log"), (time.time() - 10 * 86400,) * 2)
        os.utime(os.path.join(self.dir, "logs", "l0.log"), (time.time() - 10 * 86400,) * 2)
        self.store.compact(keep=3)
        self.assertEqual([r["log"] for r in self.store.runs()], ["l2.log", "l3.log", "l4.log"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "logs"))), ["new.log"])
        with open(self.store.path) as f:
            self.assertEqual(len(f.readlines()), 3)

    def test_read_tail(self):
        path = os.path.join(self.dir, "big.log")
        with open(path, "w") as f:
            f.write("".join("line%d\n" % i for i in range(1000)))
        self.assertEqual(server.read_tail(path, 2, max_bytes=100), "line998\nline999\n")

    def test_prune_work(self):
        root = os.path.join(self.dir, "work")
        for name, pid in (("dead", 2 ** 22 + 12345), ("live", os.getpid())):
            os.makedirs(os.path.join(root, name))
            with open(os.path.join(root, name, "pid"), "w") as f:
                f.write(str(pid))
        os.makedirs(os.path.join(root, "nopid"))
        server.prune_work(root)
        self.assertEqual(sorted(os.listdir(root)), ["live", "nopid"])

    def test_http(self):
        with open(os.path.join(self.dir, "config.json"), "w") as f:
            json.dump(CFG, f)
        b, c = COLS
        for r in (run(b, "probe", "passed", checks=GOOD, expect="trusted"), run(c, "probe", "passed", checks=GOOD),
                  run(b, "subset", "failed", BASE_SUB), run(c, "subset", "failed", BASE_SUB)):
            self.store.append(r)
        with open(os.path.join(self.dir, "logs", "x.log"), "w") as f:
            f.write("line1\nline2\nline3\n")
        with open(os.path.join(self.dir, "secret"), "w") as f:
            f.write("no")
        srv = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.dir, self.store, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]

        def get(path):
            with urllib.request.urlopen(base + path) as resp:
                return resp.read().decode()

        orig = server.GROUPS
        server.GROUPS = {"ab": ["a", "b"], "none": []}
        try:
            page = get("/")
        finally:
            server.GROUPS = orig
        self.assertIn("<th>eMudhra protected</th><th>ab</th><th>none</th>", page)
        self.assertIn('<span class="yes">&#10003;</span> 1/1', page)
        self.assertIn('<span class="na">n/a</span>', page)
        self.assertIn('http-equiv="refresh" content="30"', page)
        self.assertEqual(len(json.loads(get("/api/runs"))), 4)
        self.assertEqual(get("/logs/x.log?tail=1"), "line3\n")
        for bad in ("/logs/../secret", "/logs/%2e%2e/secret", "/logs/..%2fsecret", "/logs/.x"):
            with self.assertRaises(urllib.error.HTTPError, msg=bad) as e:
                get(bad)
            self.assertEqual(e.exception.code, 404)
            e.exception.close()

        # A project that passed only on the retry is shown as flaky.
        self.store.append(run(c, "subset", "passed", {"//a:test": "FLAKY", "//b:test": "FAILED"}))
        server.GROUPS = {"ab": ["a", "b"]}
        try:
            page = get("/")
        finally:
            server.GROUPS = orig
        self.assertIn("1/1, 1 flaky (candidate only)", page)
        self.assertIn("//a:test (only on the candidate)", page)


if __name__ == "__main__":
    unittest.main()
