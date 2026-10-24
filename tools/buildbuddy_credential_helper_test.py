import os
import tempfile
import unittest

import buildbuddy_credential_helper as helper


class ApiKeyTest(unittest.TestCase):
    def test_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "key")
            with open(path, "w") as f:
                f.write("fromfile\n")
            self.assertEqual(helper.api_key({"BAZEL_MATRIX_KEY_FILE": path}), "fromfile")

    def test_env_key_ignored(self):
        self.assertEqual(helper.api_key({"BUILDBUDDY_API_KEY": "k"}), "")

    def test_missing_file(self):
        self.assertEqual(helper.api_key({"BAZEL_MATRIX_KEY_FILE": "/nonexistent"}), "")


if __name__ == "__main__":
    unittest.main()
