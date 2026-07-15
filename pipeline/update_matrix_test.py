import copy
import unittest

from pipeline import update_matrix


class UpdateMatrixTest(unittest.TestCase):
    def test_applies_result_by_internal_project_name(self):
        rows = [{
            "name": "grpc",
            "repo": "https://github.com/grpc/grpc",
            "results": {"as_is_local": {"status": "not_tracked"}},
        }]
        result = {
            "status": "mostly_pass",
            "passed": 49,
            "total": 50,
            "skipped": 50,
        }
        artifact = {
            "schema_version": 1,
            "project": "grpc",
            "command": "test",
            "result_key": "as_is_local",
            "result": copy.deepcopy(result),
        }

        row, key = update_matrix.apply_result(rows, artifact)

        self.assertEqual("as_is_local", key)
        self.assertEqual(result, row["results"][key])


if __name__ == "__main__":
    unittest.main()
