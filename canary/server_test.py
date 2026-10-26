import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import server

ROOT = os.path.join(os.environ.get("TEST_SRCDIR", ""), os.environ.get("TEST_WORKSPACE", ""))
ESC = "\x1b"

# Abridged `tools/bb.sh test` output, with bb remote's ANSI colors.
LOG = """
Waiting for available remote runner...
Streaming remote runner logs to: https://app.buildbuddy.io/invocation/5cd3a676-3e5f-4dea-8cd8-a6589f63e29d
{e}[90m2026-10-26 16:49:00.391 UTC {e}[32m$ {e}[mgit init --quiet
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
  /home/buildbuddy/.cache/bazel/execroot/re2/test/test.log
//rules_go:test                                       {e}[31m{e}[1mFAILED TO BUILD{e}[0m

Executed 1 out of 3 tests: 1 test passes, 1 fails locally and 1 was skipped.
{e}[32mINFO: {e}[mStreaming build results to: {e}[36mhttps://buildbuddy.buildbuddy.io/invocation/4e88c7fc-6514-4c26-9796-a1fdc3bc4b48
{e}[90m2026-10-26 16:49:28.978 UTC (command exited with code 3)

Remote run completed at 2026-10-26 16:49:29.224 UTC
""".format(e=ESC)


class ParseTest(unittest.TestCase):
    def test_invocation_links(self):
        self.assertEqual(server.invocation_links(LOG), [
            "https://app.buildbuddy.io/invocation/5cd3a676-3e5f-4dea-8cd8-a6589f63e29d",
            "https://buildbuddy.buildbuddy.io/invocation/4e88c7fc-6514-4c26-9796-a1fdc3bc4b48",
        ])

    def test_links_are_buildbuddy_https_only(self):
        self.assertEqual(server.invocation_links(
            "Streaming build results to: javascript:alert(1)//invocation/abcd\n"), [])

    def test_copy_redacted(self):
        import io
        out = io.StringIO()
        server.copy_redacted(io.BytesIO(b"a KEY b\nc\n"), out, "KEY")
        self.assertEqual(out.getvalue(), "a <REDACTED> b\nc\n")

    def test_target_results_only_outer_summary(self):
        self.assertEqual(server.target_results(LOG), {
            "//abseil-cpp:test": "PASSED",
            "//re2:test": "FAILED",
            "//rules_go:test": "FAILED TO BUILD",
        })

    def test_no_summary(self):
        self.assertEqual(server.target_results("ERROR: no such package\n"), {})

    def test_classify(self):
        self.assertEqual(server.classify(0), "passed")
        self.assertEqual(server.classify(3), "failed")  # tests failed
        self.assertEqual(server.classify(1), "failed")  # build failed
        for code in (2, 4, 8, 34, 37):  # flags, no tests, interrupted, remote errors
            self.assertEqual(server.classify(code), "error")

    def test_redact(self):
        self.assertEqual(server.redact("--remote_header=x-buildbuddy-api-key=s3cr3t", "s3cr3t"),
                         "--remote_header=x-buildbuddy-api-key=<REDACTED>")
        self.assertEqual(server.redact("text", ""), "text")


PROBE_LOG = """
==================== Test output for //canary:tls_probe_test:
tls_probe: Ubuntu 22.04, CANARY_EXPECT=distrusted, host abc
FAIL    emudhra_fixture: eMudhra chain still verifies (root or a cross-sign still trusted)

=== tls_probe summary (CANARY_EXPECT=distrusted): 40 checks, 35 PASS, 5 FAIL, 0 NETERR, 1s
  FAIL    trust_store/bundle: vs canary/roots/22.04.txt minus emudhra.txt: 42 missing, 20 added (want 142, have 120)
  FAIL    emudhra_fixture: eMudhra chain still verifies (root or a cross-sign still trusted)
  FAIL    emudhra_online/www.internet2.edu/python: want CERT, got OK: verified, TLSv1.3
  FAIL    emudhra_online/www.internet2.edu/curl: want CERT, got OK: verified, 301 https://www.internet2.edu/
  NETERR  host/pypi.org/curl: timeout
================================================================================
==================== Test output for //zlib:test:
=== tls_probe summary (CANARY_EXPECT=trusted): 1 checks, 0 PASS, 1 FAIL, 0 NETERR, 1s
  FAIL    x: y
"""


class ProbeSummaryTest(unittest.TestCase):
    def test_failures(self):
        got = server.probe_failures(PROBE_LOG)
        self.assertEqual(sorted(got), ["//canary:tls_probe_test"])  # //zlib:test isn't the probe
        self.assertEqual([c for _, c, _ in got["//canary:tls_probe_test"]], [
            "trust_store/bundle", "emudhra_fixture", "emudhra_online/www.internet2.edu/python",
            "emudhra_online/www.internet2.edu/curl", "host/pypi.org/curl"])
        self.assertEqual(server.summarize_failures(got["//canary:tls_probe_test"]), [
            "trust_store/bundle: 42 missing, 20 added (want 142, have 120)",
            "emudhra_fixture: eMudhra chain still verifies (root or a cross-sign still trusted)",
            "emudhra_online x2: verified, TLSv1.3",
            "NETERR host/pypi.org/curl: timeout",
        ])


CHECKS_LOG = """
==================== Test output for //canary:tls_probe_test:
tls_probe: Ubuntu 22.04, CANARY_EXPECT=distrusted, host abc
PASS    tools: found /bin/curl
PASS    trust_store/bundle: removed 4 (emSign Root CA - G1, ...), added 0
FAIL    emudhra/fixture: eMudhra chain still verifies
PASS    emudhra/online/www.internet2.edu/curl: rejected
FAIL    host/github.com/curl: curl 60
NETERR  host/pypi.org/curl: timeout

=== tls_probe summary (CANARY_EXPECT=distrusted): 5 checks, 2 PASS, 2 FAIL, 1 NETERR, 1s
  FAIL    emudhra/fixture: eMudhra chain still verifies
"""


class ProbeChecksTest(unittest.TestCase):
    def test_checks(self):
        got = server.probe_checks(CHECKS_LOG)
        self.assertEqual(got["emudhra/fixture"], ["FAIL", "eMudhra chain still verifies"])
        self.assertEqual(got["host/pypi.org/curl"][0], "NETERR")
        self.assertEqual(len(got), 6)
        self.assertTrue(server.is_emudhra("emudhra/online/x") and server.is_emudhra("emudhra_fixture"))
        self.assertFalse(server.is_emudhra("trust_store/bundle"))


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
        # tools/bb.sh reads the runner image the same way.
        self.assertEqual(re.findall(r"container-image=[^ \n]*", new), ["container-image=" + self.REF])
        self.assertEqual(server.rewrite_image(new, self.REF), new)

    def test_rejects_unpinned_ref(self):
        with self.assertRaises(ValueError):
            server.rewrite_image(self.rc, "docker://gcr.io/flame-public/rbe-ubuntu24-04:latest")

    def test_rejects_missing_line(self):
        with self.assertRaises(ValueError):
            server.rewrite_image("common --jobs=1\n", self.REF)


def run(name, step, status, start, targets=None, ref="r", arch="amd64"):
    return {"id": name + arch + step + start, "cycle": 1, "image": {"name": name, "ref": ref, "arch": arch},
            "step": step,
            "start": start, "end": start, "status": status, "targets": targets or {},
            "invocations": [], "log": "x.log"}


class RegressionTest(unittest.TestCase):
    IMAGES = server.columns([
        {"name": "b22", "ref": "r", "role": "baseline", "release": "22.04"},
        {"name": "c22", "ref": "r", "role": "candidate", "release": "22.04"},
        {"name": "b24", "ref": "r", "role": "baseline", "release": "24.04"},
        {"name": "c24", "ref": "r", "role": "candidate", "release": "24.04"},
    ])

    def test_regressions(self):
        runs = [
            run("b22", "subset", "failed", "1", {"//a:test": "PASSED", "//b:test": "FAILED"}),
            # An older candidate run is superseded by the newer one.
            run("c22", "subset", "passed", "1", {"//a:test": "PASSED", "//b:test": "PASSED"}),
            run("c22", "subset", "failed", "2", {"//a:test": "FAILED", "//b:test": "FAILED"}),
            run("b24", "subset", "passed", "1", {"//c:test": "PASSED"}),
            run("c24", "subset", "failed", "1", {"//a:test": "FAILED", "//c:test": "PASSED"}),
            run("b22", "probe", "passed", "1"),
            run("c22", "probe", "failed", "1"),
            # arm64 compares with arm64 only.
            run("b22", "probe", "failed", "1", arch="arm64"),
            run("c22", "probe", "failed", "1", arch="arm64"),
            run("c24", "probe", "failed", "1", arch="arm64"),
            run("b24", "probe", "passed", "1", arch="arm64"),
        ]
        rows = [("probe", None), ("subset", None), ("subset", "//a:test"), ("subset", "//b:test"),
                ("subset", "//c:test")]
        got = server.regressions(self.IMAGES, server.latest(runs), rows)
        # c24's //a:test fails, but no 24.04 baseline ran it (its step as a
        # whole still regressed); //b:test fails on both.
        # Probe rows never count here (see verdicts()).
        self.assertEqual(got, {("c22", "amd64", ("subset", "//a:test")), ("c24", "amd64", ("subset", None))})

    def test_ignores_other_digests_and_running(self):
        runs = [run("b22", "subset", "passed", "1", {"//a:test": "PASSED"}, ref="old"),
                run("c22", "subset", "failed", "1", {"//a:test": "FAILED"}),
                run("b22", "subset", "running", "2")]
        got = server.regressions(self.IMAGES, server.latest(runs), [("subset", "//a:test")])
        self.assertEqual(got, set())


class ScheduleTest(unittest.TestCase):
    def test_order_and_commands(self):
        images = [
            {"name": "b22", "ref": "r", "role": "baseline", "release": "22.04"},
            {"name": "c22", "ref": "r", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
            {"name": "b24", "ref": "r", "role": "baseline", "release": "24.04"},
        ]
        cfg = {"images": images, "subset": {"22.04": ["zlib"], "22.04/arm64": ["rules_go"]},
               "salt_inner": True, "bazel": "bazel", "output_root": "/out"}
        got = [(c["name"], c["arch"], step) for c, step in server.schedule(cfg)]
        self.assertEqual(got, [
            ("c22", "amd64", "probe"),
            ("b22", "amd64", "probe"), ("b22", "arm64", "probe"),
            ("b24", "amd64", "probe"), ("b24", "arm64", "probe"),
            ("b22", "amd64", "subset"), ("b22", "arm64", "subset"), ("c22", "amd64", "subset"),
        ])
        runner = server.Runner("/nonexistent", "/nonexistent", None)
        rbe = ["--config=remote-minimal", "--remote_header=x-buildbuddy-api-key=KEY", "--nocache_test_results"]
        arm = dict(images[0], arch="arm64")
        self.assertEqual(runner.command(cfg, 7, arm, "probe", "KEY"), [
            "bazel", "--output_base=/out/arm64", "test", "//canary:tls_probe_test"] + rbe + [
            "--remote_default_exec_properties=Arch=arm64", "--test_output=all",
            "--test_env=CANARY_EXPECT=trusted"])
        amd = dict(images[1], arch="amd64")
        self.assertIn("--test_env=CANARY_EXPECT=distrusted", runner.command(cfg, 7, amd, "probe", "KEY"))
        self.assertEqual(runner.command(cfg, 7, dict(images[0], arch="amd64"), "subset", "KEY"), [
            "bazel", "--output_base=/out/amd64", "test", "//zlib:test"] + rbe + [
            "--//:inner_flags=--remote_instance_name=canary-7"])
        self.assertEqual(runner.command(cfg, 7, arm, "subset", "KEY")[-3:], [
            "--remote_default_exec_properties=Arch=arm64",
            "--//:inner_flags=--remote_default_exec_properties=Arch=arm64",
            "--//:inner_flags=--remote_instance_name=canary-7"])
        self.assertIsNone(runner.command(cfg, 7, dict(images[2], arch="amd64"), "subset", "KEY"))


class VerdictTest(unittest.TestCase):
    def test_verdicts(self):
        cfg = {"subset": {"22.04": ["a", "b"]}, "images": []}
        cols = server.columns([
            {"name": "b", "ref": "r", "role": "baseline", "release": "22.04", "archs": ["amd64"]},
            {"name": "c", "ref": "r", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
            {"name": "d", "ref": "r", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
        ])
        def probe(name, checks):
            r = run(name, "probe", "passed", "1")
            r["probe_checks"] = checks
            return r
        runs = [
            probe("b", {"emudhra/fixture": ["PASS", "verifies"], "host/x": ["PASS", "ok"]}),
            run("b", "subset", "failed", "1", {"//a:test": "PASSED", "//b:test": "FAILED"}),
            probe("c", {"emudhra/fixture": ["PASS", "rejected"], "host/x": ["PASS", "ok"],
                        "trust_store/bundle": ["PASS", "removed 4"]}),
            run("c", "subset", "failed", "1", {"//a:test": "PASSED", "//b:test": "FAILED"}),
            probe("d", {"emudhra/fixture": ["FAIL", "still verifies"], "host/x": ["FAIL", "curl 60"]}),
            run("d", "subset", "failed", "1", {"//a:test": "FAILED", "//b:test": "FAILED"}),
        ]
        lat = server.latest(runs)
        v = {c["name"]: server.verdicts(cfg, cols, lat, c) for c in cols}
        self.assertEqual(v["b"][0][0], "baseline")
        self.assertEqual(v["b"][1], ("no", ["fails //b:test"]))
        # //b:test fails on the baseline too: not a regression.
        self.assertEqual(v["c"], (("yes", []), ("yes", [])))
        self.assertEqual(v["d"], (("no", ["emudhra/fixture: still verifies"]),
                                  ("no", ["host/x: curl 60", "regresses //a:test"])))
        none = server.verdicts(cfg, cols, {}, cols[1])
        self.assertEqual([none[0][0], none[1][0]], ["pending", "pending"])

    def test_unproven_is_pending_and_build_failure_regresses(self):
        cfg = {"subset": {"22.04": ["a"]}, "images": []}
        cols = server.columns([
            {"name": "b", "ref": "r", "role": "baseline", "release": "22.04", "archs": ["amd64"]},
            {"name": "c", "ref": "r", "role": "candidate", "release": "22.04", "archs": ["amd64"]},
        ])
        p = run("c", "probe", "failed", "1")
        p["probe_checks"] = {"emudhra/fixture": ["NETERR", "timeout"], "host/x": ["NETERR", "timeout"]}
        runs = [run("b", "subset", "passed", "1", {"//a:test": "PASSED"}), p,
                run("c", "subset", "failed", "1", {})]
        rejects, works = server.verdicts(cfg, cols, server.latest(runs), cols[1])
        self.assertEqual(rejects, ("pending", ["NETERR emudhra/fixture: timeout"]))
        self.assertEqual(works, ("no", ["NETERR host/x: timeout", "subset failed (baseline passed)"]))
        # A timed-out probe with a few PASS lines proves nothing.
        p.update(status="timeout", probe_checks={"tools": ["PASS", "found"]})
        rejects, works = server.verdicts({"subset": {}}, cols, server.latest(runs), cols[1])
        self.assertEqual((rejects[0], works[0]), ("pending", "pending"))


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def test_seed(self):
        cfg = server.load_config(self.dir)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "config.json")))
        self.assertEqual(cfg["repo_branch"], "rbe-image-canary")
        self.assertTrue(cfg["salt_inner"])
        self.assertEqual([(i["release"], i["role"]) for i in cfg["images"]],
                         [("22.04", "baseline"), ("22.04", "candidate"), ("24.04", "baseline"),
                          ("24.04", "candidate")])
        for im in cfg["images"]:
            server.rewrite_image("--remote_default_exec_properties=container-image=x\n", im["ref"])
        self.assertTrue(cfg["subset"]["22.04"])
        self.assertTrue(set(cfg["subset"]["24.04"]) <= set(cfg["subset"]["22.04"]))

    def test_seed_22_04_is_remote_bazelrc(self):
        with open(os.path.join(ROOT, "tools", "remote.bazelrc")) as f:
            self.assertIn("container-image=" + server.BASELINE_2204 + "\n", f.read())

    def test_edits_survive(self):
        server.load_config(self.dir)
        path = os.path.join(self.dir, "config.json")
        with open(path) as f:
            cfg = json.load(f)
        cfg["images"].append({"name": "c", "ref": "x", "role": "candidate", "release": "22.04"})
        del cfg["salt_inner"]
        with open(path, "w") as f:
            json.dump(cfg, f)
        got = server.load_config(self.dir)
        self.assertEqual(len(got["images"]), 5)
        self.assertTrue(got["salt_inner"])  # defaulted
        self.assertEqual([i["name"] for i in server.ordered_images(got["images"])],
                         ["ubuntu22-04", "ubuntu22-04-candidate", "c", "ubuntu24-04", "ubuntu24-04-candidate"])


class StoreAndUiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.store = server.Store(self.dir)

    def test_interrupted_on_restart(self):
        r = run("b22", "subset", "running", "1")
        self.store.append(r)
        done = dict(run("b22", "probe", "running", "0"))
        self.store.append(done)
        done["status"] = "passed"
        self.store.append(done)
        self.store.mark_interrupted()
        self.assertEqual({x["step"]: x["status"] for x in self.store.runs()},
                         {"probe": "passed", "subset": "interrupted"})
        self.assertEqual(self.store.next_cycle(), 2)

    def test_http(self):
        cfg = server.load_config(self.dir)
        im = cfg["images"][0]
        r = run(im["name"], "subset", "failed", "1", {"//zlib:test": "FAILED"}, ref=im["ref"])
        self.store.append(r)
        with open(os.path.join(self.dir, "logs", "x.log"), "w") as f:
            f.write("line1\nline2\nline3\n")
        with open(os.path.join(self.dir, "secret"), "w") as f:
            f.write("no")
        srv = server.http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), server.make_handler(self.dir, self.store, None))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]

        def get(path):
            with urllib.request.urlopen(base + path) as resp:
                return resp.read().decode()

        page = get("/")
        self.assertIn("//zlib:test", page)
        self.assertIn(">n/a<", page)  # arm64 subset cells
        self.assertIn('http-equiv="refresh" content="30"', page)
        self.assertEqual(json.loads(get("/api/runs"))[0]["status"], "failed")
        self.assertEqual(get("/logs/x.log?tail=1"), "line3\n")
        for bad in ("/logs/../secret", "/logs/%2e%2e/secret", "/logs/..%2fsecret", "/logs/.x"):
            with self.assertRaises(urllib.error.HTTPError, msg=bad) as e:
                get(bad)
            self.assertEqual(e.exception.code, 404)
            e.exception.close()


if __name__ == "__main__":
    unittest.main()
