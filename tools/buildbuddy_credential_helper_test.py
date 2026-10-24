import os
import tempfile
import unittest

import buildbuddy_credential_helper as helper


class ApiKeyTest(unittest.TestCase):
    def test_env_wins(self):
        self.assertEqual(helper.api_key({"BUILDBUDDY_API_KEY": "k"}, "/nonexistent"), "k")

    def test_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "key")
            with open(path, "w") as f:
                f.write("fromfile\n")
            self.assertEqual(helper.api_key({}, path), "fromfile")

    def test_none(self):
        self.assertEqual(helper.api_key({}, "/nonexistent"), "")


if __name__ == "__main__":
    unittest.main()
