import unittest

import sync


class ParseProjectsTxtTest(unittest.TestCase):
    def test_forms(self):
        projects = sync.parse_projects_txt("\n".join([
            "# comment",
            "zlib",
            "re2@2025-11-05.bcr.1",
            "  -//python/...  needs a python toolchain",
            "  -//:bench   slow",
            "  --copt=-w   noisy warnings",
            "  bazel 8.4.2 needs Bazel 8",
            "",
        ]))
        self.assertEqual([p["name"] for p in projects], ["zlib", "re2"])
        self.assertIsNone(projects[0]["version"])
        re2 = projects[1]
        self.assertEqual(re2["version"], "2025-11-05.bcr.1")
        self.assertEqual(re2["exclude"], [("//python/...", "needs a python toolchain"),
                                          ("//:bench", "slow")])
        self.assertEqual(re2["flags"], [("--copt=-w", "noisy warnings")])
        self.assertEqual(re2["bazel"], ("8.4.2", "needs Bazel 8"))
        self.assertEqual(sync.targets(re2), ["//...", "-//python/...", "-//:bench"])

    def test_errors(self):
        for text in ["zlib\n  -//foo/...", "  -//x  why", "zlib\nzlib",
                     "zlib\n  //foo  why", "zlib\n  -//foo/*  why", "Bad Name"]:
            with self.assertRaises(ValueError, msg=text):
                sync.parse_projects_txt(text)


class PickTest(unittest.TestCase):
    def test_latest_stable_compatible(self):
        meta = {"versions": ["1.0", "1.10", "1.9", "2.0-rc1", "1.11"], "yanked_versions": {"1.11": "bad"}}
        texts = {"1.10": 'module(name = "m", bazel_compatibility = [">=7.0.0"])'}
        self.assertEqual(sync.pick(meta, texts.get, "9.3.1"), ("1.10", None))

    def test_incompatible(self):
        meta = {"versions": ["1.0"]}
        text = 'module(\n  name = "m",\n  # bazel_compatibility = [">=99"]\n  bazel_compatibility = ["<9.0.0"],\n)'
        version, why = sync.pick(meta, {"1.0": text}.get, "9.3.1")
        self.assertIsNone(version)
        self.assertIn("excludes Bazel 9.3.1", why)

    def test_date_versions(self):
        meta = {"versions": ["2024-07-02", "2025-11-05.bcr.1", "2025-11-05"]}
        self.assertEqual(sync.pick(meta, lambda v: "", "9.3.1"), ("2025-11-05.bcr.1", None))

    def test_deprecated(self):
        self.assertEqual(sync.pick({"deprecated": "x", "versions": ["1"]}, lambda v: "", "9"),
                         (None, "deprecated"))


class SourceEntryTest(unittest.TestCase):
    def test_archive(self):
        entry = sync.source_entry("m", "1.0", {
            "url": "https://a/m.zip", "mirror_urls": ["https://b/m.zip"],
            "integrity": "sha256-x", "strip_prefix": "m-1.0",
            "patches": {"b.patch": "sha256-b", "a.patch": "sha256-a"}, "patch_strip": 1,
            "overlay": {"z/BUILD": "sha256-z", "BUILD": "sha256-o"},
        })
        self.assertEqual(entry["urls"], ["https://a/m.zip", "https://b/m.zip"])
        self.assertEqual([p["url"] for p in entry["patches"]], [
            "https://bcr.bazel.build/modules/m/1.0/patches/b.patch",
            "https://bcr.bazel.build/modules/m/1.0/patches/a.patch"])
        self.assertEqual(entry["patch_strip"], 1)
        self.assertEqual([o["path"] for o in entry["overlay"]], ["BUILD", "z/BUILD"])
        self.assertNotIn("archive_type", entry)

    def test_git_unsupported(self):
        with self.assertRaises(ValueError):
            sync.source_entry("m", "1", {"type": "git_repository", "remote": "x"})


class RenderBuildTest(unittest.TestCase):
    def test_render(self):
        text = sync.render_build({"name": "re2", "exclude": [("//python/...", "why")],
                                  "flags": [("--copt=-w", "because")], "bazel": ("8.4.2", "old")})
        self.assertTrue(text.startswith(sync.GENERATED))
        self.assertIn('    name = "re2",\n', text)
        self.assertIn('        # why\n        "-//python/...",\n', text)
        self.assertIn('        # because\n        "--copt=-w",\n', text)
        self.assertIn('    # old\n    bazel_version = "8.4.2",\n', text)

    def test_minimal(self):
        text = sync.render_build({"name": "zlib", "exclude": [], "flags": [], "bazel": None})
        self.assertNotIn("flags", text)
        self.assertNotIn("bazel_version", text)


if __name__ == "__main__":
    unittest.main()
