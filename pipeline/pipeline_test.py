import io
import json
import tarfile
import unittest

from pipeline import inventory, matrix, model
from pipeline.sources import bcr


def _archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for path, content in files.items():
            data = content.encode("utf-8")
            info = tarfile.TarInfo("registry/modules/" + path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue()


class BcrEcosystemTest(unittest.TestCase):
    def test_tags_dependencies_from_latest_non_yanked_version(self):
        metadata = lambda repo, versions, yanked=None: json.dumps({
            "repository": ["github:" + repo],
            "versions": versions,
            "yanked_versions": yanked or {},
        })
        data = _archive({
            "demo/metadata.json": metadata("acme/demo", ["1.0.0", "2.0.0"], {"2.0.0": "bad"}),
            "demo/1.0.0/MODULE.bazel": """
                bazel_dep(
                    name = "rules_go",
                    version = "0.1.0",
                )
                bazel_dep(name = "toolchains_llvm", version = "1.0.0")
                # bazel_dep(name = "rules_java", version = "1.0.0")
            """,
            "demo/2.0.0/MODULE.bazel": "bazel_dep(name = \"rules_java\", version = \"1.0.0\")",
            "rules_go/metadata.json": metadata("bazel-contrib/rules_go", ["0.1.0"]),
            "rules_go/0.1.0/MODULE.bazel": "",
            "rules_java/metadata.json": metadata("bazelbuild/rules_java", ["1.0.0"]),
            "rules_java/1.0.0/MODULE.bazel": "",
            "toolchains_llvm/metadata.json": metadata("bazel-contrib/toolchains_llvm", ["1.0.0"]),
            "toolchains_llvm/1.0.0/MODULE.bazel": "",
        })

        projects = {project.name: project for project in bcr.parse(data)}
        self.assertEqual(["rules_go"], projects["demo"].rulesets)
        self.assertEqual(["toolchains_llvm"], projects["demo"].toolchains)
        row = projects["demo"].to_dict()
        self.assertEqual(
            ["ruleset:rules_go", "toolchain:toolchains_llvm"],
            row["ecosystem_tags"],
        )

    def test_merge_unions_ecosystem_metadata(self):
        project = model.Project("acme", "demo", rulesets=["rules_go"])
        project.merge(model.Project(
            "acme",
            "demo",
            rulesets=["rules_go", "rules_proto"],
            toolchains=["toolchains_llvm"],
        ))
        self.assertEqual(["rules_go", "rules_proto"], project.rulesets)
        self.assertEqual(["toolchains_llvm"], project.toolchains)


class CandidateEcosystemFilterTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{
            "repo": "https://github.com/acme/demo",
            "name": "demo",
            "category": model.CATEGORY_PROJECT,
            "first_party_bazel": True,
            "rulesets": ["rules_go"],
            "toolchains": ["toolchains_llvm"],
        }]

    def test_include_filters(self):
        rows = inventory.candidate_rows(
            self.rows,
            include_built=True,
            rulesets=["rules_go"],
            toolchains=["toolchains_llvm"],
        )
        self.assertEqual(1, len(rows))

    def test_exclude_filters(self):
        rows = inventory.candidate_rows(
            self.rows,
            include_built=True,
            exclude_rulesets=["rules_go"],
        )
        self.assertEqual([], rows)


class MatrixReadmeTest(unittest.TestCase):
    def test_render_uses_featured_tags_and_invocation_links(self):
        result = {
            "status": "pass",
            "passed": 2,
            "total": 2,
            "invocation": "https://app.buildbuddy.io/invocation/example",
        }
        row = {
            "name": "demo",
            "display_name": "Demo",
            "repo": "https://github.com/acme/demo",
            "results": {key: dict(result) for key, _ in matrix.RESULT_COLUMNS},
        }
        rendered = matrix.render([row], {
            "https://github.com/acme/demo": {"tags": ["featured"]},
        })
        self.assertEqual(2, rendered.count("[`acme/demo`](https://github.com/acme/demo)"))
        self.assertIn("[2 / 2](https://app.buildbuddy.io/invocation/example)", rendered)

    def test_result_without_invocation_is_rendered(self):
        self.assertEqual("🚫", matrix.result_cell({"status": "no_tests"}))

    def test_skipped_targets_do_not_crowd_primary_result(self):
        self.assertEqual(
            "🟢 49 / 50",
            matrix.result_cell({
                "status": "mostly_pass",
                "passed": 49,
                "total": 50,
                "skipped": 50,
            }),
        )

    def test_result_cases_do_not_crowd_primary_result(self):
        result = {
            "status": "fail",
            "passed": 1,
            "total": 2,
            "cases": {
                "passed": 85,
                "failed": 6,
                "skipped": 2,
                "complete": False,
            },
        }
        self.assertEqual(
            "❌ 1 / 2",
            matrix.result_cell(result),
        )

    def test_case_counts_are_validated(self):
        with self.assertRaisesRegex(ValueError, "invalid as_is_local cases failed"):
            matrix._validate_cases("demo", "as_is_local", {
                "passed": 1,
                "failed": -1,
                "skipped": 0,
                "complete": True,
            })

    def test_target_counts_are_validated(self):
        with self.assertRaisesRegex(ValueError, "invalid as_is_local target counts"):
            matrix.validate_result("demo", "as_is_local", {
                "status": "fail",
                "passed": 2,
                "total": 1,
            })

        with self.assertRaisesRegex(ValueError, "cases missing complete"):
            matrix._validate_cases("demo", "as_is_local", {
                "passed": 1,
                "failed": 0,
                "skipped": 0,
            })


if __name__ == "__main__":
    unittest.main()
