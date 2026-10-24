import unittest

import run


class SelectTest(unittest.TestCase):
    PROJECTS = [{"name": "a", "known_failing": None},
                {"name": "b", "known_failing": ("build", "r")},
                {"name": "c", "known_failing": ("test", "r")}]

    def test_skips_known_failing(self):
        self.assertEqual(run.select_projects(self.PROJECTS, "build", [], False), ["a", "c"])
        self.assertEqual(run.select_projects(self.PROJECTS, "test", [], False), ["a"])
        self.assertEqual(run.select_projects(self.PROJECTS, "test", [], True), ["a", "b", "c"])
        self.assertEqual(run.select_projects(self.PROJECTS, "test", ["a", "c"], False), ["a"])
        with self.assertRaises(ValueError):
            run.select_projects(self.PROJECTS, "test", ["z"], False)

    def test_shard(self):
        self.assertEqual(run.shard(["c", "a", "b", "d", "e"], 2), [["a", "c", "e"], ["b", "d"]])
        self.assertEqual(run.shard(["a"], 4), [["a"]])


class ParseLogTest(unittest.TestCase):
    def test_test(self):
        log = "\n".join([
            "INFO: Streaming build results to: https://x.io/invocation/0123-abcd",
            "//zlib:test                                  (cached) PASSED in 30.1s",
            "\x1b[32m//re2:test\x1b[0m    FAILED in 10s",
            "//other:test PASSED in 1s",
            "\x1b[90m2026-10-24 (command exited with code 3)",
        ])
        code, link, status = run.parse_log(log, "test", ["zlib", "re2", "fmt"])
        self.assertEqual(code, 3)
        self.assertEqual(link, "https://x.io/invocation/0123-abcd")
        self.assertEqual(status, {"zlib": "PASSED", "re2": "FAILED", "fmt": "UNKNOWN"})

    def test_build(self):
        log = "\n".join([
            "ERROR: /root/workspace/repo-root/re2/BUILD.bazel:5:8: Building re2 with inner Bazel 9.3.1 failed: (Exit 1)",
            "(command exited with code 1)",
        ])
        _, _, status = run.parse_log(log, "build", ["zlib", "re2"])
        self.assertEqual(status, {"zlib": "PASSED", "re2": "FAILED"})
        _, _, status = run.parse_log("(command exited with code 0)", "build", ["zlib"])
        self.assertEqual(status, {"zlib": "PASSED"})
        # A failure that names no project: nothing is known.
        _, _, status = run.parse_log("(command exited with code 1)", "build", ["zlib", "re2"])
        self.assertEqual(status, {"zlib": "UNKNOWN", "re2": "UNKNOWN"})


if __name__ == "__main__":
    unittest.main()
