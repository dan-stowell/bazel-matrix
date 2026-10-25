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
            "//zlib:test                                  (cached) PASSED in 30.1s",
            "\x1b[32m//re2:test\x1b[0m    FAILED in 10s",
            "  /path/to/re2/test.log",
            "//other:test PASSED in 1s",
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
            "==================== Test output for //zlib:test:",
            INNER,
            "//zlib:test   PASSED in 1s",
            "",
            "Executed 1 out of 1 test: 1 test passes.",
            INNER,
            "wall time: 20s",
            "================================================================================",
        ]
        summary = ["//zlib:test  FAILED in 25s", "  /path/test.log", "",
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
            "Target //zlib:build up-to-date:",  # inner-looking noise outside the summary
            "INFO: Found 3 targets...",
            "Target //zlib:build up-to-date:",
            "  bazel-bin/zlib/build.txt",
            "\x1b[31mTarget //re2:build failed to build\x1b[0m",
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

    def test_build_of_known_failing_test_project(self):
        log = "\n".join([
            OUTER,
            "Target //c:build up-to-date:",
            "  bazel-bin/c/build.txt",
            "INFO: Elapsed time: 5s",
            "//a:test   PASSED in 3s",
            "",
            "Executed 1 out of 1 test: 1 test passes.",
            OUTER,
            "(command exited with code 0)",
        ])
        self.assertEqual(run.parse_log(log, "test", {"a": "test", "c": "build"})[2],
                         {"a": "PASSED", "c": "BUILT"})


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
