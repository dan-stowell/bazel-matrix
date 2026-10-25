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

    def test_override(self):
        p = sync.parse_projects_txt("m\n  override rules_cc 0.2.27  drops the root includes check\n")[0]
        self.assertEqual(p["overrides"], [("rules_cc", "0.2.27", "drops the root includes check")])
        self.assertEqual(sync.module_append(p["overrides"], 'module(name = "m")\n'),
                         ([], '\n# bazel-matrix: drops the root includes check\n'
                          'single_version_override(module_name = "rules_cc", version = "0.2.27")\n'))
        with self.assertRaises(ValueError):
            sync.parse_projects_txt("m\n  override rules_cc 0.2.27\n")

    def test_override_conflicts(self):
        o = [("rules_cc", "0.2.27", "r")]
        with self.assertRaisesRegex(ValueError, "listed twice for rules_cc"):
            sync.module_append(o + [("rules_cc", "0.2.26", "r")], "")
        with self.assertRaisesRegex(ValueError, "already has single_version_override for rules_cc"):
            sync.module_append(o, 'single_version_override(\n    version = "1",\n    module_name = "rules_cc",\n)\n')
        with self.assertRaisesRegex(ValueError, "already has git_override"):
            sync.module_append(o, 'git_override(module_name = "rules_cc", remote = "x", commit = "y")')
        with self.assertRaisesRegex(ValueError, "isn't a string literal"):
            sync.module_append(o, 'N = "rules_cc"\nsingle_version_override(module_name = N, version = "1")\n')
        with self.assertRaisesRegex(ValueError, "include"):
            sync.module_append(o, 'include("//:deps.MODULE.bazel")\n')
        with self.assertRaisesRegex(ValueError, "already has archive_override"):
            sync.module_append(o, 'archive_override(module_name = "rules_cc", urls = ["x"])')
        # Other modules' overrides and commented-out ones are fine.
        sync.module_append(o, 'single_version_override(module_name = "zlib", version = "1")\n'
                              '# single_version_override(module_name = "rules_cc", version = "1")\n')

    def test_override_version_in_bcr(self):
        o = [("rules_cc", "0.2.27", "r")]
        sync.module_append(o, "", lambda m, v: (m, v) == ("rules_cc", "0.2.27"))
        with self.assertRaisesRegex(ValueError, "rules_cc@0.2.27 isn't in the BCR"):
            sync.module_append(o, "", lambda m, v: False)

    def test_override_replaces_local_path_override(self):
        o = [("core", "0.1.2", "r")]
        lpo = ('local_path_override(\n    module_name = "core",  # the sibling\n'
               '    path = "../core",\n)')
        text = 'module(name = "m")\nbazel_dep(name = "core", version = "0.1.2")\n\n%s\n' % lpo
        remove, append = sync.module_append(o, text)
        self.assertEqual(remove, [lpo])
        self.assertEqual(append, sync.render_append(o))
        # Another module's local_path_override stays.
        other = 'local_path_override(module_name = "zz", path = "..")\n'
        self.assertEqual(sync.module_append(o, other), ([], sync.render_append(o)))

    def test_override_local_path_override_not_literal(self):
        o = [("core", "0.1.2", "r")]
        bad = {
            "not top level": 'x = local_path_override(module_name = "core", path = "..")\n',
            "a comment after it": 'local_path_override(module_name = "core", path = "..")  # x\n',
            "in a loop": '[local_path_override(module_name = "core", path = p) for p in [".."]]\n',
            "more after it": 'local_path_override(module_name = "core", path = "..") + 1\n',
            "nested call": 'local_path_override(module_name = "core", path = str(".."))\n',
            "twice": 'local_path_override(module_name = "core", path = "..")\n'
                     'local_path_override(module_name = "core", path = "..")\n',
        }
        for what, text in bad.items():
            with self.assertRaisesRegex(ValueError, "isn't whole lines found once", msg=what):
                sync.module_append(o, text)
        with self.assertRaisesRegex(ValueError, "isn't a string literal"):
            sync.module_append(o, '[local_path_override(module_name = m, path = "..") for m in ["core"]]\n')
        with self.assertRaisesRegex(ValueError, "isn't a string literal"):
            sync.module_append(o, 'local_path_override(module_name = "core" + "_x", path = "..")\n')
        with self.assertRaisesRegex(ValueError, "include"):
            sync.module_append(o, 'include("//:deps.MODULE.bazel")\n')

    def test_rc_drop(self):
        p = sync.parse_projects_txt("\n".join([
            "m",
            "  rc-drop .bazelrc `build --x`  Bazel 9 removed it",
            "  rc-drop .bazelrc ` import %workspace%/../a.rc `  outside the archive",
            "  rc-drop .aspect/b.rc `common:ci --y=1 --z`  also removed",
            ""]))[0]
        self.assertEqual(p["rc_drop"], [
            (".bazelrc", "build --x", "Bazel 9 removed it"),
            (".bazelrc", "import %workspace%/../a.rc", "outside the archive"),
            (".aspect/b.rc", "common:ci --y=1 --z", "also removed")])
        self.assertEqual(sync.rc_remove(p["rc_drop"]), {
            ".bazelrc": ["build --x", "import %workspace%/../a.rc"],
            ".aspect/b.rc": ["common:ci --y=1 --z"]})
        for text in ["m\n  rc-drop .bazelrc `build --x`", "m\n  rc-drop .bazelrc build --x  why",
                     "m\n  rc-drop `build --x`  why", "m\n  rc-drop ../.bazelrc `build --x`  why",
                     "m\n  rc-drop /etc/bazel.bazelrc `build --x`  why",
                     "m\n  rc-drop MODULE.bazel `bazel_dep(name = \"x\")`  why",
                     "m\n  rc-drop .bazelrc `build --x`  a\n  rc-drop .bazelrc ` build --x`  b"]:
            with self.assertRaises(ValueError, msg=text):
                sync.parse_projects_txt(text)

    def test_remove_lines(self):
        rc = "build --x\n  build --x=1\ncommon --y\n"
        self.assertEqual(sync.remove_lines(rc, "build --x"), "  build --x=1\ncommon --y\n")
        self.assertEqual(sync.remove_lines(rc, "build --x=1"), "build --x\ncommon --y\n")
        # Whole lines only: no prefix or substring matches.
        self.assertIsNone(sync.remove_lines(rc, "build"))
        self.assertIsNone(sync.remove_lines(rc, "--y"))
        self.assertIsNone(sync.remove_lines(rc, "build --z"))
        self.assertIsNone(sync.remove_lines(rc, ""))
        self.assertIsNone(sync.remove_lines("a\na\n", "a"))
        # Several lines, in order.
        self.assertEqual(sync.remove_lines("x(\n  a,\n)\ny\n", "x(\na,\n)"), "y\n")
        self.assertIsNone(sync.remove_lines("x(\n  a,\n)\n", "x(\n)"))

    def test_known_failing(self):
        projects = sync.parse_projects_txt(
            "a\n  known-failing build  no Bazel 9: native.cc_library\nb\n  known-failing test  x y\nc\n")
        self.assertEqual([p["known_failing"] for p in projects],
                         [("build", "no Bazel 9: native.cc_library"), ("test", "x y"), None])

    def test_blank_line_ends_project(self):
        with self.assertRaisesRegex(ValueError, "line 3: indented line after a blank line"):
            sync.parse_projects_txt("a\n\n  known-failing build  why\n")
        # Comments may sit between, and blank lines between projects.
        projects = sync.parse_projects_txt("a\n# c\n  -//x  why\n\nb\n")
        self.assertEqual([(p["name"], p["exclude"]) for p in projects],
                         [("a", [("//x", "why")]), ("b", [])])

    def test_errors(self):
        for text in ["zlib\n  -//foo/...", "  -//x  why", "zlib\nzlib",
                     "zlib\n  //foo  why", "zlib\n  -//foo/*  why", "Bad Name",
                     "zlib\n  known-failing run  why", "zlib\n  known-failing build",
                     "zlib\n  known-failing build  a\n  known-failing test  b"]:
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
        self.assertIn("no version admits Bazel 9.3.1", why)

    def test_older_compatible(self):
        meta = {"versions": ["1.0", "2.0"]}
        texts = {"1.0": "module()", "2.0": 'module(bazel_compatibility = ["<9.0.0"])'}
        self.assertEqual(sync.pick(meta, texts.get, "9.3.1"), ("1.0", None))

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
        }, b"module()")
        self.assertEqual(entry["urls"], ["https://a/m.zip", "https://b/m.zip"])
        self.assertEqual([p["url"] for p in entry["patches"]], [
            "https://bcr.bazel.build/modules/m/1.0/patches/b.patch",
            "https://bcr.bazel.build/modules/m/1.0/patches/a.patch"])
        self.assertEqual(entry["patch_strip"], 1)
        self.assertEqual([o["path"] for o in entry["overlay"]], ["BUILD", "z/BUILD"])
        self.assertNotIn("archive_type", entry)
        self.assertEqual(entry["module_file"], {
            "url": "https://bcr.bazel.build/modules/m/1.0/MODULE.bazel",
            "integrity": "sha256-GDnKZZcR0m/WJM8eh8ATv29Jxdy5Mg2ckuYNbDixJDk="})

    def test_git_unsupported(self):
        with self.assertRaises(ValueError):
            sync.source_entry("m", "1", {"type": "git_repository", "remote": "x"}, b"")


class VersionsTest(unittest.TestCase):
    def test_default_inner_bazel(self):
        self.assertEqual(sync.default_inner_bazel('x\nDEFAULT_INNER_BAZEL = "9.3.1"\n'), "9.3.1")
        with self.assertRaises(ValueError):
            sync.default_inner_bazel("")


class GeneratedTest(unittest.TestCase):
    PROJECTS = sync.parse_projects_txt("a\n  known-failing build  why\nb\nc\n")

    def test_build_files(self):
        files = sync.build_files(self.PROJECTS, ["a", "c"])
        self.assertEqual(sorted(files), ["a/BUILD.bazel", "c/BUILD.bazel"])
        self.assertIn('known_failing = "build"', files["a/BUILD.bazel"])

    def test_module_mismatch(self):
        def check(fetched, skipped):
            return sync.module_mismatch(self.PROJECTS, {
                "projects": [{"name": n, "version": "1", "source": {}} for n in fetched],
                "skipped": [{"name": n, "reason": "r"} for n in skipped]})
        self.assertEqual(check(["a", "c"], ["b"]), [])
        differ = "projects.json and projects.txt differ on: "
        self.assertEqual(check(["a"], ["b"]), [differ + "c"])
        self.assertEqual(check(["a", "c", "d"], ["b"]), [differ + "d"])
        self.assertEqual(check(["a", "b", "c"], ["b"]), [differ + "b"])
        self.assertIn(differ + "c", check(["a", "c", "c"], ["b"]))
        self.assertEqual(check(["c", "a"], ["b"]),
                         ["projects.json's projects are not in projects.txt's order"])

    def test_pins_and_overrides(self):
        projects = sync.parse_projects_txt("a@2\nb\n  override rules_cc 0.2.27  why\n")
        _, append = sync.module_append(projects[1]["overrides"], "")
        data = {"skipped": [], "projects": [
            {"name": "a", "version": "2", "source": {}},
            {"name": "b", "version": "1", "source": {"module_append": append}}]}
        self.assertEqual(sync.module_mismatch(projects, data), [])
        # Skipped for its source type at the pinned version: fine.
        data["skipped"] = [{"name": "c", "reason": "c@3: git_repository sources aren't supported yet"}]
        projects = sync.parse_projects_txt("a@2\nb\n  override rules_cc 0.2.27  why\nc@3\n")
        self.assertEqual(sync.module_mismatch(projects, data), [])
        projects = sync.parse_projects_txt("a@2\nb\n  override rules_cc 0.2.27  why\nc@4\n")
        self.assertEqual(sync.module_mismatch(projects, data), [
            "c: pinned 4, but projects.json skips it: c@3: git_repository sources aren't supported yet"])
        data["skipped"] = []
        projects = projects[:2]
        data["projects"][1]["source"]["remove"] = {
            "MODULE.bazel": ['local_path_override(module_name = "rules_cc", path = "..")']}
        self.assertEqual(sync.module_mismatch(projects, data), [])
        data["projects"][1]["source"]["remove"] = {
            "MODULE.bazel": ['local_path_override(module_name = "zlib", path = "..")']}
        self.assertEqual(sync.module_mismatch(projects, data), [
            "b: projects.json's MODULE.bazel removals don't match its override lines"])
        del data["projects"][1]["source"]["remove"]
        data["projects"][0]["version"] = "1"
        data["projects"][1]["source"] = {}
        self.assertEqual(sync.module_mismatch(projects, data), [
            "a: pinned 2, projects.json has 1",
            "b: projects.json's module_append doesn't match its override lines"])


    def test_rc_drop(self):
        projects = sync.parse_projects_txt("a\n  override m 1  r\n  rc-drop .bazelrc `build --x`  why\nb\n")
        lpo = 'local_path_override(module_name = "m", path = "..")'
        data = {"skipped": [], "projects": [
            {"name": "a", "version": "1", "source": {
                "module_append": sync.render_append(projects[0]["overrides"]),
                "remove": {"MODULE.bazel": [lpo], ".bazelrc": ["build --x"]}}},
            {"name": "b", "version": "1", "source": {}}]}
        self.assertEqual(sync.module_mismatch(projects, data), [])
        data["projects"][0]["source"]["remove"] = {"MODULE.bazel": [lpo]}
        data["projects"][1]["source"] = {"remove": {".bazelrc": ["build --x"]}}
        self.assertEqual(sync.module_mismatch(projects, data), [
            "a: projects.json's rc file removals don't match its rc-drop lines",
            "b: projects.json's rc file removals don't match its rc-drop lines"])


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
        self.assertNotIn("known_failing", text)

    def test_known_failing(self):
        text = sync.render_build({"name": "m", "exclude": [], "flags": [], "bazel": None,
                                  "known_failing": ("test", "needs a GPU")})
        self.assertIn('    # needs a GPU\n    known_failing = "test",\n', text)


if __name__ == "__main__":
    unittest.main()
