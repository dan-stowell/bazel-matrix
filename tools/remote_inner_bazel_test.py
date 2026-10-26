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

    def test_inner_killed_by_signal_is_infra(self):
        def inner(argv):
            proc = mock.Mock(returncode=-9)
            inner_bazel.wait_exit(proc, 10)
            with open(os.environ["XML_OUTPUT_FILE"], "w") as f:
                f.write("<testsuites/>")
            return 1
        with mock.patch.object(inner_bazel, "wait_exit", lambda proc, t: True):
            code, _, out, tmp = self.run_main(inner)
            with open(os.path.join(tmp, "test.xml")) as f:
                xml = f.read()
        self.assertEqual(code, 1)
        self.assertNotIn(r.DONE_MARKER, out)
        self.assertIn('name="%s"' % r.INFRA_CASE, xml)

    def test_inner_timeout_is_not_infra(self):
        def inner(argv):
            inner_bazel.wait_exit(mock.Mock(returncode=-15), 10)
            return 1
        with mock.patch.object(inner_bazel, "wait_exit", lambda proc, t: False):
            code, _, out, _ = self.run_main(inner)
        self.assertIn(r.DONE_MARKER + " (exit 1)", out)

    def test_exception_is_wrapper_error(self):
        def inner(argv):
            raise OSError("no tar")
        tmp_xml = {}
        def run():
            try:
                self.run_main(inner)
            except OSError:
                pass
        with mock.patch.object(r, "write_xml", lambda text: tmp_xml.setdefault("last", []).append(text)):
            run()
        self.assertIn("wrapper_error", tmp_xml["last"][-1])

    def test_no_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(r.main([]), 1)


if __name__ == "__main__":
    unittest.main()
