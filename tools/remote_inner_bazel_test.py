import io
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import inner_bazel
import remote_inner_bazel as r


class RemoteInnerBazelTest(unittest.TestCase):
    def test_key_dir(self):
        root = r.key_dir("k")
        path = os.path.join(root, inner_bazel.KEY_FILE)
        with open(path) as f:
            self.assertEqual(f.read(), "k")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def run_main(self, inner):
        tmp = tempfile.mkdtemp()
        xml = os.path.join(tmp, "test.xml")
        env = {"BUILDBUDDY_API_KEY": "k", "XML_OUTPUT_FILE": xml, "TEST_TMPDIR": tmp}
        seen = {}

        def fake_main(argv):
            seen["env_key"] = os.environ.get("BUILDBUDDY_API_KEY")
            seen["work_root"] = inner_bazel.WORK_ROOT
            with open(os.path.join(inner_bazel.output_base("."), inner_bazel.KEY_FILE)) as f:
                seen["key"] = f.read()
            with open(xml) as f:
                seen["xml"] = f.read()
            return inner(argv)

        out = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(inner_bazel, "main", fake_main), \
                mock.patch.object(inner_bazel, "WORK_ROOT", inner_bazel.WORK_ROOT), \
                mock.patch.object(inner_bazel, "output_base", inner_bazel.output_base), redirect_stdout(out):
            try:
                code = r.main(["--project=p"])
            except SystemExit as e:
                code = ("exit", e.code)
        return code, seen, out.getvalue(), tmp

    def test_runs_inner_with_key_file_and_marks_done(self):
        code, seen, out, tmp = self.run_main(lambda argv: 1)
        self.assertEqual(code, 1)
        self.assertIsNone(seen["env_key"])
        self.assertEqual(seen["key"], "k")
        self.assertEqual(seen["work_root"], os.path.join(tmp, "work"))
        self.assertIn('name="%s"' % r.INFRA_CASE, seen["xml"])
        self.assertIn('name="p"', seen["xml"])
        self.assertIn(r.DONE_MARKER + " (exit 1)", out)

    def test_killed_leaves_no_marker(self):
        def killed(argv):
            raise SystemExit(143)  # inner_bazel's SIGTERM handler
        code, _, out, _ = self.run_main(killed)
        self.assertEqual(code, ("exit", 143))
        self.assertNotIn(r.DONE_MARKER, out)

    def test_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(r.main([]), 1)


if __name__ == "__main__":
    unittest.main()
