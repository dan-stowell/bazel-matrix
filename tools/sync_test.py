import unittest

import sync


class ParseProjectsTest(unittest.TestCase):
    def test_forms(self):
        text = "\n".join([
            'module(name = "x")',
            'bazel_dep(name = "zlib", version = "1.3")',
            '# bazel_dep(name = "dropped", version = "1")',
            "bazel_dep(name = 'fmt', version = '12')  # single quotes",
            'bazel_dep(',
            '    name = "re2",  # name = "wrong"',
            '    version = "2025-11-05.bcr.1",',
            '    repo_name = "com_googlesource_code_re2",',
            ')',
            'bazel_dep(dev_dependency = True, name = "rules_python", version = "2")',
            'include("//:overrides.MODULE.bazel")',
        ])
        self.assertEqual(sync.parse_projects(text), [
            ("zlib", "1.3", "zlib"),
            ("fmt", "12", "fmt"),
            ("re2", "2025-11-05.bcr.1", "com_googlesource_code_re2"),
        ])


class UndevTest(unittest.TestCase):
    def check(self, before, after, available=lambda name, version: True):
        self.assertEqual(sync.undev(before, available), after)

    def test_last_argument(self):
        self.check('bazel_dep(name = "g", version = "1", dev_dependency = True)\n',
                   'bazel_dep(name = "g", version = "1")\n')

    def test_first_argument(self):
        self.check('bazel_dep(dev_dependency = True, name = "g")\n',
                   'bazel_dep(name = "g")\n')

    def test_middle_argument(self):
        self.check('bazel_dep(name = "g", dev_dependency = True, repo_name = "x")\n',
                   'bazel_dep(name = "g", repo_name = "x")\n')

    def test_only_argument(self):
        self.check('register_toolchains(dev_dependency = True)\n',
                   'register_toolchains()\n')

    def test_multi_line_with_comments(self):
        self.check(
            'x = use_extension(\n    "@a//:b.bzl",  # (not a paren\n    "c",\n'
            '    dev_dependency = True,  # dev only\n)\n',
            'x = use_extension(\n    "@a//:b.bzl",  # (not a paren\n    "c",  # dev only\n)\n',
        )

    def test_commented_out_dev_dependency_is_left_alone(self):
        text = 'bazel_dep(name = "g")  # dev_dependency = True\n'
        self.check(text, text)

    def test_single_quotes(self):
        self.check("bazel_dep(name = 'g', version = '1', dev_dependency = True)\n",
                   "bazel_dep(name = 'g', version = '1')\n")

    def test_keeps_overridden_and_unavailable_deps_dev_only(self):
        text = "\n".join([
            'bazel_dep(name = "a", version = "1", dev_dependency = True)',
            'bazel_dep(name = "b", version = "1", dev_dependency = True)',
            "archive_override(module_name = 'b', urls = ['x'])",
            'bazel_dep(name = "c", version = "9", dev_dependency = True, repo_name = "cc")',
            'e = use_extension("@cc//:e.bzl", "e", dev_dependency = True)',
            'f = use_extension("@a//:f.bzl", "f", dev_dependency = True)',
            'use_repo(e, "e_repo", other = "e_other")',
            'register_toolchains("@e_repo//:all", dev_dependency = True)',
            'register_toolchains("@e_other//:all", dev_dependency = True)',
            'register_toolchains("@cc-tools//:all", dev_dependency = True)',
            '',
        ])
        self.check(text, "\n".join([
            'bazel_dep(name = "a", version = "1")',
            'bazel_dep(name = "b", version = "1", dev_dependency = True)',
            "archive_override(module_name = 'b', urls = ['x'])",
            'bazel_dep(name = "c", version = "9", dev_dependency = True, repo_name = "cc")',
            'e = use_extension("@cc//:e.bzl", "e", dev_dependency = True)',
            'f = use_extension("@a//:f.bzl", "f")',
            'use_repo(e, "e_repo", other = "e_other")',
            'register_toolchains("@e_repo//:all", dev_dependency = True)',
            'register_toolchains("@e_other//:all", dev_dependency = True)',
            'register_toolchains("@cc-tools//:all")',
            '',
        ]), lambda name, version: name != "c")

    def test_no_dev_deps_no_patch(self):
        self.assertIsNone(sync.make_patch('bazel_dep(name = "g", version = "1")\n'))

    def test_patch_headers(self):
        patch = sync.make_patch('bazel_dep(name = "g", version = "1", dev_dependency = True)\n')
        self.assertTrue(patch.startswith("--- a/MODULE.bazel\n+++ b/MODULE.bazel\n"))


class QueryTest(unittest.TestCase):
    def test_expr_without_exclusions(self):
        expr = sync.query_expr(["a", "b"], [])
        self.assertNotIn("rdeps", expr)
        self.assertEqual(expr, "kind(rule, @a//... + @b//...) except "
                         "attr(tags, '[\\[ ]manual[,\\]]', @a//... + @b//...)")

    def test_expr_with_exclusions(self):
        self.assertTrue(sync.query_expr(["a"], ["@a//x/...", "@a//:t"]).endswith(
            " except rdeps(@a//..., @a//x/... + @a//:t)"))

    def test_parse_ignores_noise(self):
        out = "\n".join([
            "\x1b[32mINFO: \x1b[mInvocation ID: 123",
            "cc_test rule @re2//:set_test",
            "alias rule @zlib//:z",
            "cc_library rule @abseil-cpp//absl/strings:strings",
            "source file @zlib//:zlib.h",
        ])
        self.assertEqual(sync.parse_query(out), {
            "re2": [("cc_test", "@re2//:set_test")],
            "zlib": [("alias", "@zlib//:z")],
            "abseil-cpp": [("cc_library", "@abseil-cpp//absl/strings:strings")],
        })

    CANON = {"re2+": "re2", "protobuf+": "protobuf", "foo+": "foo", "glog+": "glog"}

    def problems(self, lines, patterns):
        return sync.check_errors("\n".join(lines), self.CANON, patterns)

    def test_covered_load_failures_and_dep_errors_pass(self):
        self.assertEqual(self.problems([
            "\x1b[31;1mERROR: \x1b[mTraceback (most recent call last):",
            '\tFile "/w/output-base/external/re2+/app/BUILD.bazel", line 7, column 10, in <toplevel>',
            "ERROR: package contains errors: app: Traceback (most recent call last):",
            "ERROR: error loading package '@@protobuf+//ruby': Unable to find package",
            "ERROR: Skipping '@protobuf//ruby/...': no targets found beneath 'ruby'",
            "ERROR: /w/external/glog+/BUILD.bazel:15:9: no such package '@@[unknown repo]//cpu': x",
            "ERROR: no such package '@@[unknown repo]//cpu': x",
            "ERROR: error loading package '@@grpc+//': cannot load",
            "ERROR: /w/external/rules_nodejs+/nodejs/toolchain.bzl:99:44: CcInfo was removed",
            "ERROR: /w/external/glog+/BUILD.bazel:1:2: no such package "
            "'@@[unknown repo 'x' requested from @@glog+]//': nope and referenced by '@@glog+//:t'",
            "ERROR: no such package '@@[unknown repo 'x' requested from @@glog+]//': nope",
            "ERROR: /w/external/glog+/BUILD.bazel:3:4: no such package '@@dl+//': tmp1 and "
            "referenced by '@@glog+//:u'",
            "ERROR: no such package '@@dl+//': tmp2",
            "ERROR: Evaluation of query \"kind(rule, ...)\" failed",
        ], ["@re2//app/...", "@protobuf//ruby/..."]), [])

    def test_uncovered_load_failures(self):
        self.assertEqual(self.problems([
            "ERROR: error loading package '@@protobuf+//ruby': Unable to find package",
            "ERROR: Skipping '@foo//...': error loading package under directory '': "
            "no such package '@@foo+//': error downloading",
        ], ["@re2//ruby/..."]), [
            "package failed to load and isn't excluded: @foo//",
            "package failed to load and isn't excluded: @protobuf//ruby",
        ])

    def test_stale_exclusions(self):
        got = self.problems([
            "ERROR: no such package '@@protobuf+//java/core': BUILD file not found",
            "ERROR: no such target '@@re2+//:gone': target 'gone' not declared in package ''",
            "ERROR: Skipping '@glog//old/...': no targets found beneath 'old'",
        ], ["@protobuf//java/core:t", "@re2//:gone", "@glog//old/..."])
        self.assertEqual(len(got), 3)
        self.assertTrue(all(p.startswith("stale exclusion") for p in got), got)

    def test_repo_identity(self):
        # re2//ruby failing to load doesn't make @protobuf//ruby/... non-stale.
        got = self.problems([
            "ERROR: error loading package '@@re2+//ruby': x",
            "ERROR: Skipping '@protobuf//ruby/...': no targets found beneath 'ruby'",
        ], ["@protobuf//ruby/...", "@re2//ruby/..."])
        self.assertEqual(got, ["stale exclusion: @protobuf//ruby/... matches nothing"])

    def test_fails_closed(self):
        self.assertEqual(self.problems(["ERROR: something new"], []),
                         ["unrecognised error: something new"])
        self.assertEqual(self.problems(["ERROR: no such package '@@x+//y': z"], []),
                         ["unrecognised error: no such package '@@x+//y': z"])
        self.assertEqual(self.problems(["oops"], []), ["query failed without ERROR lines"])

    def test_covered(self):
        pats = ["@a//x/...", "@b//...", "@c//:t"]
        self.assertTrue(sync.covered("a", "x", pats))
        self.assertTrue(sync.covered("a", "x/y", pats))
        self.assertFalse(sync.covered("a", "xy", pats))
        self.assertFalse(sync.covered("b2", "x", pats))
        self.assertTrue(sync.covered("b", "any", pats))
        self.assertFalse(sync.covered("c", "", pats))


class ExclusionsTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(sync.parse_exclusions("# c\n\n@a//:b needs tzdata\n"),
                         [("@a//:b", "needs tzdata")])
        with self.assertRaises(ValueError):
            sync.parse_exclusions("@a//:b\n")

    def test_forms(self):
        self.assertEqual(sync.parse_pattern("@a//..."), ("a", "", "..."))
        self.assertEqual(sync.parse_pattern("@a-b//x/y/..."), ("a-b", "x/y", "..."))
        self.assertEqual(sync.parse_pattern("@a//x/y:t.h"), ("a", "x/y", "t.h"))
        self.assertEqual(sync.parse_pattern("@a//:t"), ("a", "", "t"))
        for bad in ["@a//...:all", "@a//x", "@a//x:all", "@a//x:*", "@a//:v25*",
                    "@a//x/...:t", "//x:t", "@a//x/..."[:-1]]:
            self.assertIsNone(sync.parse_pattern(bad), bad)


class RenderBuildTest(unittest.TestCase):
    def test_aliases_and_suite(self):
        text = sync.render_build("m", [
            ("cc_library", "@m//:lib"),
            ("cc_library", "@m//a/b:lib"),
            ("cc_library", "@m//a_b:lib"),
            ("cc_library", "@m//:tests"),
            ("cc_test", "@m//a:t_test"),
            ("test_suite", "@m//a:all_tests"),
        ])
        self.assertIn('name = "lib",\n    actual = "@m//:lib"', text)
        self.assertIn('name = "a_b__lib",\n    actual = "@m//a/b:lib"', text)
        self.assertIn('name = "a_b__lib_2",\n    actual = "@m//a_b:lib"', text)
        self.assertIn('name = "tests_2",\n    actual = "@m//:tests"', text)
        self.assertIn('"@m//a:t_test",', text)
        self.assertNotIn("all_tests", text)
        self.assertTrue(text.startswith(sync.GENERATED))

    def test_no_tests_no_suite(self):
        self.assertNotIn("test_suite", sync.render_build("m", [("cc_library", "@m//:lib")]))


class ContainerImageTest(unittest.TestCase):
    def test_reads_bazelrc(self):
        rc = "common:x --remote_default_exec_properties=container-image=docker://i@sha256:ab\n"
        self.assertEqual(sync.container_image(rc), "docker://i@sha256:ab")


if __name__ == "__main__":
    unittest.main()
