import json
import os
import tempfile
import unittest

from bazel_runner import bazel_runner


class MatrixResultTest(unittest.TestCase):
    def test_collects_runnable_skipped_and_case_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            xml = os.path.join(directory, "test.xml")
            with open(xml, "w", encoding="utf-8") as f:
                f.write("""<testsuite><testcase name="pass"/><testcase name="fail"><failure/></testcase><testcase name="skip"><skipped/></testcase></testsuite>""")
            bep = os.path.join(directory, "bep.json")
            events = [{"id": {"started": {}}, "started": {"uuid": "abc-123"}}]
            for index in range(10):
                label = "//:pass{}".format(index)
                events.extend([
                    {
                        "id": {"targetConfigured": {
                            "label": label,
                            "configuration": {"id": "configured-id"},
                        }},
                        "configured": {"testSize": "SMALL"},
                    },
                    {
                        "id": {"testSummary": {"label": label}},
                        "testSummary": {"overallStatus": "PASSED"},
                    },
                ])
            events.extend([
                {
                    "id": {"targetConfigured": {"label": "//:fail"}},
                    "configured": {"testSize": "SMALL"},
                },
                {
                    "id": {"targetCompleted": {"label": "//:fail"}},
                    "completed": {"success": False},
                },
                {
                    "id": {"targetConfigured": {"label": "//:windows.exe"}},
                    "configured": {"testSize": "SMALL"},
                },
                {
                    "id": {"targetCompleted": {"label": "//:windows.exe"}},
                    "completed": {"skipped": True},
                },
                {
                    "id": {"testResult": {"label": "//:pass0", "attempt": 1}},
                    "testResult": {"testActionOutput": [{
                        "name": "test.xml",
                        "uri": "file://" + xml,
                    }]},
                },
            ])
            with open(bep, "w", encoding="utf-8") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            artifact = bazel_runner._load_test_result(bep, "grpc/as_is/local/test")

        self.assertEqual("as_is_local", artifact["result_key"])
        self.assertEqual("mostly_pass", artifact["result"]["status"])
        self.assertEqual(10, artifact["result"]["passed"])
        self.assertEqual(11, artifact["result"]["total"])
        self.assertEqual(1, artifact["result"]["skipped"])
        self.assertEqual(12, artifact["collection"]["configured_tests"])
        self.assertEqual(1, artifact["collection"]["failed_targets"])
        self.assertEqual({
            "passed": 1,
            "failed": 1,
            "skipped": 1,
            "complete": True,
        }, artifact["result"]["cases"])
        self.assertEqual(
            "https://app.buildbuddy.io/invocation/abc-123",
            artifact["result"]["invocation"],
        )

    def test_status_cutoff_is_strictly_over_ninety_percent(self):
        self.assertEqual("fail", bazel_runner._matrix_status(9, 1))
        self.assertEqual("mostly_pass", bazel_runner._matrix_status(10, 1))
        self.assertEqual("pass", bazel_runner._matrix_status(1, 0))
        self.assertEqual("no_tests", bazel_runner._matrix_status(0, 0))

    def test_non_test_build_failure_overrides_an_all_passing_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            bep = os.path.join(directory, "bep.json")
            with open(bep, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": {"testSummary": {"label": "//:passes"}},
                    "testSummary": {"overallStatus": "PASSED"},
                }) + "\n")
            artifact = bazel_runner._load_test_result(
                bep,
                "demo/as_is/local/test",
                returncode=1,
            )
        self.assertEqual("fail", artifact["result"]["status"])
        self.assertEqual(1, artifact["exit_code"])

    def test_unresolved_configured_tests_fail_when_build_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            bep = os.path.join(directory, "bep.json")
            events = []
            for label in ("//:passes", "//:fails_one", "//:fails_two"):
                events.append({
                    "id": {"targetConfigured": {"label": label}},
                    "configured": {"testSize": "SMALL"},
                })
            events.append({
                "id": {"testSummary": {"label": "//:passes"}},
                "testSummary": {"overallStatus": "PASSED"},
            })
            with open(bep, "w", encoding="utf-8") as f:
                for event in events:
                    f.write(json.dumps(event) + "\n")

            artifact = bazel_runner._load_test_result(
                bep,
                "demo/hermetic_llvm/local/test",
                returncode=1,
            )

        self.assertEqual("fail", artifact["result"]["status"])
        self.assertEqual(1, artifact["result"]["passed"])
        self.assertEqual(3, artifact["result"]["total"])
        self.assertNotIn("skipped", artifact["result"])
        self.assertEqual(2, artifact["collection"]["failed_targets"])

    def test_console_target_outcomes_are_parsed(self):
        outcomes = {}
        for line in (
                "//:one        PASSED in 0.1s\n",
                "//:two.exe    SKIPPED\n",
                "//:three      FAILED TO BUILD\n"):
            bazel_runner._record_target_outcome(line, outcomes)
        self.assertEqual({
            "//:one": "PASSED",
            "//:two.exe": "SKIPPED",
            "//:three": "FAILED TO BUILD",
        }, outcomes)


if __name__ == "__main__":
    unittest.main()
