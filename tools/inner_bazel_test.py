import json
import os
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

import inner_bazel


def ev(**kw):
    return json.dumps(kw)


def tc(label, cfg="c1"):
    return {"label": label, "configuration": {"id": cfg}}


BEP = [
    ev(id={"started": {}}, started={"uuid": "abc"}),
    ev(id={"targetConfigured": {"label": "//:t1"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:t2"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:t3"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:t4"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:skip"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:lib"}}, configured={}),
    ev(id={"targetConfigured": {"label": "//:badlib"}}, configured={}),
    ev(id={"targetCompleted": tc("//:lib")}, completed={"success": True}),
    ev(id={"targetCompleted": tc("//:badlib")}, completed={}),
    ev(id={"targetCompleted": tc("//:t1")}, completed={"success": True}),
    ev(id={"targetCompleted": tc("//:t3")}, completed={}),
    ev(id={"targetCompleted": tc("//:t4")}, completed={"success": True}),
    ev(id={"targetCompleted": tc("//:skip")}, aborted={"reason": "SKIPPED"}),
    ev(id={"testSummary": tc("//:t1")}, testSummary={"overallStatus": "PASSED", "totalRunDurationMillis": "1500"}),
    ev(id={"testSummary": tc("//:t2")}, testSummary={"overallStatus": "FAILED"}),
    "",
    '{"id": {"testSummary": {"label": "//:trunc',
]


class LoadBepTest(unittest.TestCase):
    def test_results(self):
        invocation, tests, failed = inner_bazel.load_bep(BEP)
        self.assertEqual(invocation, "abc")
        self.assertEqual(tests, {
            ("//:t1", "c1"): ("PASSED", 1500),
            ("//:t2", "c1"): ("FAILED", 0),
            ("//:t3", "c1"): ("FAILED_TO_BUILD", 0),
            ("//:t4", "c1"): ("BUILT", 0),
            ("//:skip", ""): ("SKIPPED", 0),
        })
        self.assertEqual(failed, ["//:badlib"])

    def test_configurations_kept_apart(self):
        bep = [
            ev(id={"testSummary": tc("//:t", "a")}, testSummary={"overallStatus": "FAILED"}),
            ev(id={"testSummary": tc("//:t", "b")}, testSummary={"overallStatus": "PASSED"}),
        ]
        tests = inner_bazel.load_bep(bep)[1]
        self.assertEqual(tests, {("//:t", "a"): ("FAILED", 0), ("//:t", "b"): ("PASSED", 0)})
        root = ET.fromstring(inner_bazel.test_xml("p", tests, [], "L"))
        names = sorted(c.get("name") for c in root.iter("testcase"))
        self.assertEqual(names, ["//:t [a]", "//:t [b]"])
        self.assertEqual(root.find("testsuite").get("failures"), "1")

    def test_garbage_only(self):
        self.assertEqual(inner_bazel.load_bep(["not json", "[1]", '{"x": 1}']), ("", {}, []))


class TestXmlTest(unittest.TestCase):
    def test_xml(self):
        _, tests, failed = inner_bazel.load_bep(BEP)
        root = ET.fromstring(inner_bazel.test_xml("p", tests, failed, "https://x/abc"))
        suite = root.find("testsuite")
        self.assertEqual((suite.get("tests"), suite.get("failures"), suite.get("skipped")), ("6", "3", "2"))
        cases = {c.get("name"): c for c in suite.iter("testcase")}
        self.assertIsNone(cases["//:t1"].find("failure"))
        self.assertEqual(cases["//:t1"].get("time"), "1.500")
        self.assertEqual(cases["//:t2"].find("failure").get("message"), "FAILED")
        self.assertIsNotNone(cases["//:skip"].find("skipped"))
        self.assertEqual(cases["//:t4"].find("skipped").get("message"), "BUILT")
        self.assertEqual(cases["//:badlib"].get("classname"), "p.build")
        self.assertIn("https://x/abc", suite.find("system-out").text)

    def test_unexplained_failure(self):
        root = ET.fromstring(inner_bazel.test_xml("p", {("//:t", "c"): ("PASSED", 0)}, [], "L", ok=False))
        suite = root.find("testsuite")
        self.assertEqual((suite.get("tests"), suite.get("failures")), ("2", "1"))
        self.assertIn("invocation", [c.get("name") for c in suite.iter("testcase")])

    def test_explained_failure_adds_nothing(self):
        root = ET.fromstring(inner_bazel.test_xml("p", {("//:t", "c"): ("FAILED", 0)}, [], "L", ok=False))
        self.assertNotIn("invocation", [c.get("name") for c in root.iter("testcase")])


class CommandTest(unittest.TestCase):
    def test_command(self):
        args = inner_bazel.parse_args([
            "--mode=test", "--project=p", "--source=s", "--bazel=/b", "--bazel_version=9.3.1",
            "--rc=/r1", "--rc=/r2", "--credential_helper=/h",
            "--startup_flag=--experimental_remote_repo_contents_cache",
            "--flag=--copt=-w", "--target=//...", "--target=-//x/...",
        ])
        cmd = inner_bazel.inner_command(args, "/out", "/bep")
        mode = cmd.index("test")
        self.assertEqual(cmd[:mode], ["/b", "--batch", "--nosystem_rc", "--nohome_rc",
                                      "--output_user_root=/out", "--host_jvm_args=-Xmx2g",
                                      "--bazelrc=/r1", "--bazelrc=/r2",
                                      "--experimental_remote_repo_contents_cache"])
        self.assertIn("--credential_helper=*.buildbuddy.io=/h", cmd)
        self.assertIn("--test_output=errors", cmd)
        self.assertFalse(any(c.startswith("--repository_cache") for c in cmd))
        self.assertEqual(cmd[-4:], ["--copt=-w", "--", "//...", "-//x/..."])
        self.assertFalse(any("api-key" in c for c in cmd))

    def test_env_is_explicit(self):
        env = inner_bazel.inner_env("/w", "/w/bin", "/k")
        self.assertEqual(sorted(env), ["BAZEL_MATRIX_KEY_FILE", "HOME", "LANG", "PATH", "TMPDIR"])
        self.assertTrue(env["PATH"].startswith("/w/bin:"))
        self.assertEqual(env["BAZEL_MATRIX_KEY_FILE"], "/k")


class OutputBaseTest(unittest.TestCase):
    def test_found_from_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            ob = os.path.realpath(d)
            for cwd in ("execroot/_main", "execroot/_main/bazel-out/k8/bin/x/test.sh.runfiles/_main"):
                os.makedirs(os.path.join(ob, cwd), exist_ok=True)
                self.assertEqual(inner_bazel.output_base(os.path.join(ob, cwd)), ob)

    def test_not_in_execroot(self):
        with self.assertRaises(RuntimeError):
            inner_bazel.output_base("/")


class KillTest(unittest.TestCase):
    def test_kills_whole_group(self):
        # The leader exits on SIGTERM; its child ignores SIGTERM.
        proc = subprocess.Popen(
            ["sh", "-c", "sh -c 'trap \"\" TERM; echo $$; exec sleep 60' & wait"],
            stdout=subprocess.PIPE, text=True, start_new_session=True)
        child = int(proc.stdout.readline())
        inner_bazel.kill(proc)

        def gone(pid):
            try:
                with open("/proc/%d/stat" % pid) as f:
                    return f.read().split(") ", 1)[1].startswith("Z")
            except OSError:
                return True

        for _ in range(50):
            if gone(child):
                break
            time.sleep(0.1)
        self.assertTrue(gone(child))


class KillReapedTest(unittest.TestCase):
    def test_reaped_leader_not_signalled(self):
        proc = subprocess.Popen(["true"], start_new_session=True)
        proc.wait()
        calls = []
        orig, inner_bazel.os.killpg = inner_bazel.os.killpg, lambda *a: calls.append(a)
        try:
            inner_bazel.kill(proc)
        finally:
            inner_bazel.os.killpg = orig
        self.assertEqual(calls, [])

    def test_wait_exit_does_not_reap(self):
        proc = subprocess.Popen(["true"], start_new_session=True)
        self.assertTrue(inner_bazel.wait_exit(proc, 10))
        self.assertIsNone(proc.returncode)
        inner_bazel.kill(proc)
        self.assertEqual(proc.returncode, 0)


class RemoveStaleTest(unittest.TestCase):
    def test_dead_pid_removed(self):
        with tempfile.TemporaryDirectory() as root:
            for name, pid in (("dead", 2 ** 22 + 7), ("live", os.getpid())):
                os.makedirs(os.path.join(root, name, "ro"))
                with open(os.path.join(root, name, "pid"), "w") as f:
                    f.write(str(pid))
                os.chmod(os.path.join(root, name, "ro"), 0o500)
            os.makedirs(os.path.join(root, "new"))  # no pid file yet
            inner_bazel.remove_stale(root)
            self.assertEqual(sorted(os.listdir(root)), ["live", "new"])
            os.chmod(os.path.join(root, "live", "ro"), 0o700)

    def test_missing_root(self):
        inner_bazel.remove_stale("/nonexistent/bazel-matrix")


if __name__ == "__main__":
    unittest.main()
