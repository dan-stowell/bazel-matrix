import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

import inner_bazel


def ev(**kw):
    return json.dumps(kw)


BEP = [
    ev(id={"started": {}}, started={"uuid": "abc"}),
    ev(id={"targetConfigured": {"label": "//:t1"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:t2"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:t3"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:skip"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetConfigured": {"label": "//:lib"}}, configured={}),
    ev(id={"targetConfigured": {"label": "//:badlib"}}, configured={}),
    ev(id={"targetCompleted": {"label": "//:lib"}}, completed={"success": True}),
    ev(id={"targetCompleted": {"label": "//:badlib"}}, completed={}),
    ev(id={"targetCompleted": {"label": "//:t3"}}, completed={}),
    ev(id={"targetConfigured": {"label": "//:t4"}}, configured={"testSize": "SMALL"}),
    ev(id={"targetCompleted": {"label": "//:t4"}}, completed={"success": True}),
    ev(id={"targetCompleted": {"label": "//:skip"}}, aborted={"reason": "SKIPPED"}),
    ev(id={"testSummary": {"label": "//:t1"}}, testSummary={"overallStatus": "PASSED", "totalRunDurationMillis": "1500"}),
    ev(id={"testSummary": {"label": "//:t2"}}, testSummary={"overallStatus": "FAILED"}),
    "",
]


class LoadBepTest(unittest.TestCase):
    def test_results(self):
        invocation, tests, failed = inner_bazel.load_bep(BEP)
        self.assertEqual(invocation, "abc")
        self.assertEqual(tests, {
            "//:t1": ("PASSED", 1500),
            "//:t2": ("FAILED", 0),
            "//:t3": ("FAILED_TO_BUILD", 0),
            "//:skip": ("SKIPPED", 0),
            "//:t4": ("BUILT", 0),
        })
        self.assertEqual(failed, ["//:badlib"])


class TestXmlTest(unittest.TestCase):
    def test_xml(self):
        _, tests, failed = inner_bazel.load_bep(BEP)
        root = ET.fromstring(inner_bazel.test_xml("p", tests, failed, "https://x/abc"))
        suite = root.find("testsuite")
        self.assertEqual((suite.get("tests"), suite.get("failures"), suite.get("skipped")), ("6", "4", "1"))
        cases = {c.get("name"): c for c in suite.iter("testcase")}
        self.assertIsNone(cases["//:t1"].find("failure"))
        self.assertEqual(cases["//:t1"].get("time"), "1.500")
        self.assertEqual(cases["//:t2"].find("failure").get("message"), "FAILED")
        self.assertIsNotNone(cases["//:skip"].find("skipped"))
        self.assertEqual(cases["//:badlib"].get("classname"), "p.build")
        self.assertIn("https://x/abc", suite.find("system-out").text)


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
                                      "--output_user_root=/out", "--bazelrc=/r1", "--bazelrc=/r2",
                                      "--experimental_remote_repo_contents_cache"])
        self.assertIn("--credential_helper=*.buildbuddy.io=/h", cmd)
        self.assertIn("--test_output=errors", cmd)
        self.assertEqual(cmd[-4:], ["--copt=-w", "--", "//...", "-//x/..."])
        self.assertFalse(any("api-key" in c for c in cmd))

    def test_results_url(self):
        self.assertEqual(inner_bazel.results_url(["x", "common:c --bes_results_url=https://h/invocation"]),
                         "https://h/invocation/")


class RemoveStaleTest(unittest.TestCase):
    def test_dead_pid_removed(self):
        with tempfile.TemporaryDirectory() as root:
            for name, pid in (("dead", 2 ** 22 + 7), ("live", os.getpid())):
                os.makedirs(os.path.join(root, name, "ro"))
                with open(os.path.join(root, name, "pid"), "w") as f:
                    f.write(str(pid))
                os.chmod(os.path.join(root, name, "ro"), 0o500)
            inner_bazel.remove_stale(root)
            self.assertEqual(os.listdir(root), ["live"])
            os.chmod(os.path.join(root, "live", "ro"), 0o700)


if __name__ == "__main__":
    unittest.main()
