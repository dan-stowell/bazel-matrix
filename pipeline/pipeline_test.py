import io
import json
import tarfile
import unittest

from pipeline import inventory, model
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


if __name__ == "__main__":
    unittest.main()
