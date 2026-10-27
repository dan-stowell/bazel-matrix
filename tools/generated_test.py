"""Checks the committed projects.json, docs/coverage.md and projects/<module>/BUILD.bazel files
against projects.txt: they drift when projects.txt changes without a re-run
of `python3 tools/sync.py`. Needs no BCR clone: what it checks depends only on
projects.txt and projects.json."""

import json
import os
import unittest

import sync

# The test runs in the runfiles tree's main repo, which has the data files
# at their workspace paths.
ROOT = os.path.join(os.environ.get("TEST_SRCDIR", ""), os.environ.get("TEST_WORKSPACE", ""))
FIX = "; run python3 tools/sync.py"


def read(path):
    with open(os.path.join(ROOT, path)) as f:
        return f.read()


class GeneratedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Raises on duplicates and malformed lines.
        cls.projects = sync.parse_projects_txt(read("projects.txt"))
        cls.data = json.loads(read("projects.json"))
        cls.fetched = [e["name"] for e in cls.data["projects"]]

    def test_no_orphans(self):
        # tools/BUILD.bazel passes the packages with a generated BUILD.bazel.
        generated = set(os.environ["GENERATED"].split())
        orphans, missing = sorted(generated - set(self.fetched)), sorted(set(self.fetched) - generated)
        self.assertFalse(orphans or missing, "generated packages but not fetched: %s; fetched "
                         "but no generated package: %s%s" % (orphans, missing, FIX))

    def test_projects_json(self):
        errors = sync.module_mismatch(self.projects, self.data)
        self.assertFalse(errors, "projects.json:\n  " + "\n  ".join(errors) + FIX)

    def test_build_files(self):
        stale = []
        for path, text in sorted(sync.build_files(self.projects, self.data["projects"]).items()):
            try:
                if read(path) != text:
                    stale.append(path)
            except OSError:
                stale.append(path + " (missing)")
        self.assertFalse(stale, "stale generated files:\n  " + "\n  ".join(stale) + FIX)

    def test_coverage(self):
        self.assertEqual(read(sync.COVERAGE), sync.render_coverage(self.projects, self.data),
                         sync.COVERAGE + " is stale" + FIX)


if __name__ == "__main__":
    unittest.main()
