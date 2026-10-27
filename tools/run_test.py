import unittest

import run


class SelectTest(unittest.TestCase):
    PROJECTS = [{"name": "a", "known_failing": None},
                {"name": "b", "known_failing": ("build", "r")},
                {"name": "c", "known_failing": ("test", "r")}]

    def test_leaves_out_known_failing(self):
        self.assertEqual(run.select_projects(self.PROJECTS, "build", [], False),
                         {"a": "build", "c": "build"})
        # A known-failing test project still runs its build.
        self.assertEqual(run.select_projects(self.PROJECTS, "test", [], False),
                         {"a": "test", "c": "build"})
        self.assertEqual(run.select_projects(self.PROJECTS, "test", [], True),
                         {"a": "test", "b": "test", "c": "test"})
        self.assertEqual(run.select_projects(self.PROJECTS, "test", ["a", "b"], False),
                         {"a": "test", "b": "test"})
        with self.assertRaises(ValueError):
            run.select_projects(self.PROJECTS, "test", ["z"], False)

    def test_depending_on(self):
        entries = [{"name": "a", "deps": ["x"], "dev_deps": ["y"]},
                   {"name": "b", "deps": ["y"], "dev_deps": []},
                   {"name": "c", "deps": [], "dev_deps": []}]
        self.assertEqual(run.depending_on(entries, ["x"]), {"a"})
        self.assertEqual(run.depending_on(entries, ["y"]), {"a", "b"})
        self.assertEqual(run.depending_on(entries, ["x", "y"]), {"a", "b"})
        with self.assertRaises(ValueError):
            run.depending_on(entries, ["z"])

    def test_shard(self):
        self.assertEqual(run.shard(["c", "a", "b", "d", "e"], 2), [["a", "c", "e"], ["b", "d"]])
        self.assertEqual(run.shard(["a"], 4), [["a"]])


OUTER = "INFO: Streaming build results to: https://x.io/invocation/0000-aaaa"
INNER = "INFO: Streaming build results to: https://x.io/invocation/1111-bbbb"


class ParseLogTest(unittest.TestCase):
    def test_test(self):
        log = "\n".join([
            OUTER,
            "INFO: Elapsed time: 9s",
            "INFO: Build completed, 1 test FAILED, 3 total actions",
            "//projects/zlib:test                                  (cached) PASSED in 30.1s",
            "\x1b[32m//projects/re2:test\x1b[0m    FAILED in 10s",
            "  /path/to/re2/test.log",
            "//projects/other:test PASSED in 1s",
            "",
            "Executed 1 out of 3 tests: 2 tests pass and 1 fails remotely.",
            OUTER,
            "\x1b[90m2026-10-24 (command exited with code 3)",
        ])
        code, link, status = run.parse_log(log, "test", {"zlib": "test", "re2": "test", "fmt": "test"})
        self.assertEqual(code, 3)
        self.assertEqual(link, "https://x.io/invocation/0000-aaaa")
        self.assertEqual(status, {"zlib": "PASSED", "re2": "FAILED", "fmt": "UNKNOWN"})

    def test_inner_output_is_not_a_result(self):
        inner_block = [
            "==================== Test output for //projects/zlib:test:",
            INNER,
            "//projects/zlib:test   PASSED in 1s",
            "",
            "Executed 1 out of 1 test: 1 test passes.",
            INNER,
            "wall time: 20s",
            "================================================================================",
        ]
        summary = ["//projects/zlib:test  FAILED in 25s", "  /path/test.log", "",
                   "Executed 1 out of 1 test: 1 fails locally.", OUTER,
                   "(command exited with code 3)"]
        log = "\n".join([OUTER] + inner_block + summary)
        self.assertEqual(run.parse_log(log, "test", {"zlib": "test"})[2], {"zlib": "FAILED"})
        # The outer Bazel died before its summary: nothing is known.
        log = "\n".join([OUTER] + inner_block + ["(command exited with code 37)"])
        self.assertEqual(run.parse_log(log, "test", {"zlib": "test"})[2], {"zlib": "UNKNOWN"})

    def test_build(self):
        log = "\n".join([
            OUTER,
            "INFO: From Building zlib with inner Bazel 9.3.1:",
            "Target //projects/zlib:build up-to-date:",  # inner-looking noise outside the summary
            "INFO: Found 3 targets...",
            "Target //projects/zlib:build up-to-date:",
            "  bazel-bin/projects/zlib/build.txt",
            "\x1b[31mTarget //projects/re2:build failed to build\x1b[0m",
            "INFO: Elapsed time: 11.1s, Critical Path: 0.3s",
            "INFO: 19 processes: 7 remote cache hit, 12 internal.",
            "ERROR: Build did NOT complete successfully",
            OUTER,
            "(command exited with code 1)",
        ])
        _, _, status = run.parse_log(log, "build", {"zlib": "build", "re2": "build", "fmt": "build"})
        self.assertEqual(status, {"zlib": "PASSED", "re2": "FAILED", "fmt": "UNKNOWN"})
        _, _, status = run.parse_log("(command exited with code 0)", "build", {"zlib": "build"})
        self.assertEqual(status, {"zlib": "UNKNOWN"})

    def test_build_failure_summary(self):
        log = "\n".join([
            OUTER,
            "INFO: Found 1 target...",
            "Target //projects/apple_support:build failed to build",
            "Use --verbose_failures to see the command lines of failed build steps.",
            "INFO: Elapsed time: 41.7s, Critical Path: 41.0s",
            "INFO: 2 processes: 11 action cache hit, 2 internal.",
            "ERROR: Build did NOT complete successfully",
            OUTER,
            "(command exited with code 1)",
        ])
        self.assertEqual(run.parse_log(log, "build", {"apple_support": "build"})[2],
                         {"apple_support": "FAILED"})

    def test_build_of_known_failing_test_project(self):
        log = "\n".join([
            OUTER,
            "Target //projects/c:build up-to-date:",
            "  bazel-bin/projects/c/build.txt",
            "INFO: Elapsed time: 5s",
            "//projects/a:test   PASSED in 3s",
            "",
            "Executed 1 out of 1 test: 1 test passes.",
            OUTER,
            "(command exited with code 0)",
        ])
        self.assertEqual(run.parse_log(log, "test", {"a": "test", "c": "build"})[2],
                         {"a": "PASSED", "c": "BUILT"})


class ClassifyTest(unittest.TestCase):
    def test_not_known_failing(self):
        self.assertEqual(run.classify("PASSED", "test", None), ("PASSED", "pass"))
        self.assertEqual(run.classify("FAILED", "test", None), ("FAILED", "fail"))

    def test_known_failing_build_excuses_build_and_test(self):
        for target in ("build", "test"):
            self.assertEqual(run.classify("FAILED", target, "build"),
                             ("FAILED (known-failing build)", "expected"))
        self.assertEqual(run.classify("FAILED TO BUILD", "test", "build"),
                         ("FAILED TO BUILD (known-failing build)", "expected"))
        self.assertEqual(run.classify("PASSED", "test", "build"),
                         ("PASSED (known-failing build: candidate to un-mark)", "candidate"))

    def test_known_failing_test_excuses_only_test(self):
        self.assertEqual(run.classify("FAILED", "test", "test"),
                         ("FAILED (known-failing test)", "expected"))
        self.assertEqual(run.classify("TIMEOUT", "test", "test"),
                         ("TIMEOUT (known-failing test)", "expected"))
        self.assertEqual(run.classify("FAILED TO BUILD", "test", "test"),
                         ("FAILED TO BUILD", "fail"))
        # Its :build, run instead of :test or by `run.py build`, must pass.
        self.assertEqual(run.classify("FAILED", "build", "test"), ("FAILED", "fail"))
        self.assertEqual(run.classify("BUILT", "build", "test"), ("BUILT", "pass"))
        self.assertEqual(run.classify("PASSED", "build", "test"), ("PASSED", "pass"))
        self.assertEqual(run.classify("PASSED", "test", "test"),
                         ("PASSED (known-failing test: candidate to un-mark)", "candidate"))

    def test_infrastructure_failures_stay_fatal(self):
        for status in ("ERROR", "UNKNOWN", "NO STATUS", "REMOTE FAILURE", "INCOMPLETE"):
            self.assertEqual(run.classify(status, "test", "build"), (status, "fail"))

    def test_shard_ok(self):
        def shard(code, **status):
            return {"code": code, "status": status}
        targets = {"a": "test", "b": "test", "c": "test", "d": "test", "e": "build"}
        kinds = {"a": "pass", "b": "expected", "c": "fail", "d": "candidate", "e": "expected"}
        self.assertTrue(run.shard_ok(shard(0, a="PASSED"), targets, kinds))
        self.assertTrue(run.shard_ok(shard(3, a="PASSED", b="FAILED", d="PASSED"), targets, kinds))
        self.assertTrue(run.shard_ok(shard(1, b="FAILED TO BUILD"), targets, kinds))
        self.assertTrue(run.shard_ok(shard(1, e="FAILED"), targets, kinds))
        # Unexplained nonzero exits stay fatal.
        self.assertFalse(run.shard_ok(shard(3, a="PASSED"), targets, kinds))
        self.assertFalse(run.shard_ok(shard(3, b="FAILED", c="FAILED"), targets, kinds))
        self.assertFalse(run.shard_ok(shard(1, b="FAILED"), targets, kinds))  # tests fail with 3
        self.assertFalse(run.shard_ok(shard(3, e="FAILED"), targets, kinds))
        self.assertFalse(run.shard_ok(shard(37, b="FAILED"), targets, kinds))
        self.assertFalse(run.shard_ok(shard(None, b="FAILED"), targets, kinds))


class InnerLinksTest(unittest.TestCase):
    def test_links_from_summaries(self):
        log = [
            "==================== Test output for //projects/zlib:test:\n",
            "inner output\n",
            "inner invocation for zlib: https://x.io/invocation/1111\n",
            "command: test\n",
            "INFO: From Building re2 with inner Bazel 9.3.1:\n",
            "\x1b[0minner invocation for re2: (none)\n",
            "\x1b[0minner invocation for fmt: https://x.io/invocation/2222\x1b[0m\n",
            "inner invocation: https://x.io/invocation/3333\n",
        ]
        self.assertEqual(run.inner_links(log), {"zlib": "https://x.io/invocation/1111",
                                                "fmt": "https://x.io/invocation/2222"})


class ShardResultTest(unittest.TestCase):
    def test_exception_is_a_failed_shard(self):
        class Boom:
            def result(self):
                raise OSError("no bb")
        r = run.shard_result(2, Boom(), {"a": "test"})
        self.assertEqual(r["status"], {"a": "ERROR"})
        self.assertIn("no bb", r["error"])


if __name__ == "__main__":
    unittest.main()
