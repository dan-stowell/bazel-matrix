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

A wrapper killed from outside (OOM, a lost executor, a signal), or whose
inner Bazel was (it exited on a signal before its timeout), leaves no
DONE_MARKER line in its log, and a test.xml whose one testcase is
INFRA_CASE (see README.md, "Inner Bazels on RBE").
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


def one_case_xml(project, name, message, text):
    suite = ET.Element("testsuite", name=project, tests="1", failures="1")
    case = ET.SubElement(suite, "testcase", name=name, classname=project)
    ET.SubElement(case, "failure", message=message).text = text
    root = ET.Element("testsuites")
    root.append(suite)
    return ET.tostring(root, encoding="unicode") + "\n"


def infra_xml(project):
    return one_case_xml(project, INFRA_CASE, "INFRA_KILLED",
                        "the test wrapper or its inner Bazel was killed before it finished")


def write_xml(text):
    if os.environ.get("XML_OUTPUT_FILE"):
        with open(os.environ["XML_OUTPUT_FILE"], "w") as f:
            f.write(text)


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
    project = project_of(argv)
    write_xml(infra_xml(project))
    if os.environ.get("TEST_TMPDIR"):
        inner_bazel.WORK_ROOT = os.path.join(os.environ["TEST_TMPDIR"], "work")
    root = key_dir(key)
    inner_bazel.output_base = lambda _cwd: root
    # The inner Bazel's process, and whether it exited before the timeout.
    waits = []
    wait_exit = inner_bazel.wait_exit

    def recording_wait_exit(proc, timeout):
        exited = wait_exit(proc, timeout)
        waits.append((proc, exited))
        return exited

    inner_bazel.wait_exit = recording_wait_exit
    try:
        code = inner_bazel.main(argv)
    except Exception as e:
        # A failure of the wrapper itself, not a kill.
        write_xml(one_case_xml(project, "wrapper_error", "WRAPPER_ERROR", "%s: %s" % (type(e).__name__, e)))
        print("%s (exception)" % DONE_MARKER, flush=True)
        raise
    finally:
        inner_bazel.wait_exit = wait_exit
        shutil.rmtree(root, ignore_errors=True)
    # The first wait is main()'s for the timeout; kill() waits again.
    if waits and waits[0][1] and (waits[0][0].returncode or 0) < 0:
        # Killed by a signal, not by inner_bazel.py's timeout.
        write_xml(infra_xml(project))
        print("inner bazel killed by signal %d" % -waits[0][0].returncode, flush=True)
        return 1
    print("%s (exit %d)" % (DONE_MARKER, code), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
