#!/usr/bin/env python3
"""tools/inner_bazel.py for a project test running on an RBE executor.

With --//:inner_remote (see README.md), the test runs remotely, where there
is no outer output base holding the key file (tools/credentials.bzl). The
key arrives instead as $BUILDBUDDY_API_KEY, set by BuildBuddy from the
`x-buildbuddy-platform.env-overrides` header, which is not part of the
action key. This writes it to a 0600 file laid out as in an output base,
makes inner_bazel.py look for it there, and removes the variable, so the
inner Bazel and its children only get it through the credential helper.

The work dir (the inner output root) goes under $TEST_TMPDIR, in the
action's workspace, whose disk the executor accounts for, not the
container's /var/tmp.

A wrapper killed from outside (OOM, a lost executor, a signal) leaves no
DONE_MARKER line in its log, and the test.xml written first, whose one
testcase is INFRA_CASE (see README.md, "Inner Bazels on RBE").
"""

import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

import inner_bazel

# Printed (to stdout, so the test log) once the inner Bazel ran to the end,
# passed or not.
DONE_MARKER = "bazel-matrix: inner bazel finished"
# The testcase of the test.xml standing until inner_bazel.py replaces it.
INFRA_CASE = "infra_killed"


def key_dir(key):
    """A new dir with the key at inner_bazel.KEY_FILE below it."""
    root = tempfile.mkdtemp(prefix="bazel-matrix-key-")
    path = os.path.join(root, inner_bazel.KEY_FILE)
    os.makedirs(os.path.dirname(path), mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return root


def infra_xml(project):
    suite = ET.Element("testsuite", name=project, tests="1", failures="1")
    case = ET.SubElement(suite, "testcase", name=INFRA_CASE, classname=project)
    ET.SubElement(case, "failure", message="INFRA_KILLED").text = (
        "the test wrapper was killed before its inner Bazel finished")
    root = ET.Element("testsuites")
    root.append(suite)
    return ET.tostring(root, encoding="unicode") + "\n"


def project_of(argv):
    for a in argv:
        if a.startswith("--project="):
            return a.split("=", 1)[1]
    return "unknown"


def main(argv):
    key = os.environ.pop("BUILDBUDDY_API_KEY", "")
    if not key:
        print("BUILDBUDDY_API_KEY is not set: pass the env-overrides header (README.md)",
              file=sys.stderr)
        return 1
    if os.environ.get("XML_OUTPUT_FILE"):
        with open(os.environ["XML_OUTPUT_FILE"], "w") as f:
            f.write(infra_xml(project_of(argv)))
    if os.environ.get("TEST_TMPDIR"):
        inner_bazel.WORK_ROOT = os.path.join(os.environ["TEST_TMPDIR"], "work")
    root = key_dir(key)
    inner_bazel.output_base = lambda _cwd: root
    try:
        code = inner_bazel.main(argv)
    except Exception:
        # A failure of the wrapper itself, not a kill.
        print("%s (exception)" % DONE_MARKER, flush=True)
        raise
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("%s (exit %d)" % (DONE_MARKER, code), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
