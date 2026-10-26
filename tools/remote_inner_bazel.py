#!/usr/bin/env python3
"""tools/inner_bazel.py for a project test running on an RBE executor.

With --//:inner_remote (see README.md), the test runs remotely, where there
is no outer output base holding the key file (tools/credentials.bzl). The
key arrives instead as $BUILDBUDDY_API_KEY, set by BuildBuddy from the
`x-buildbuddy-platform.env-overrides` header, which is not part of the
action key. This writes it to a 0600 file laid out as in an output base,
makes inner_bazel.py look for it there, and removes the variable, so the
inner Bazel and its children only get it through the credential helper.
"""

import os
import shutil
import sys
import tempfile

import inner_bazel


def key_dir(key):
    """A new dir with the key at inner_bazel.KEY_FILE below it."""
    root = tempfile.mkdtemp(prefix="bazel-matrix-key-")
    path = os.path.join(root, inner_bazel.KEY_FILE)
    os.makedirs(os.path.dirname(path), mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return root


def main():
    key = os.environ.pop("BUILDBUDDY_API_KEY", "")
    if not key:
        print("BUILDBUDDY_API_KEY is not set: pass the env-overrides header (README.md)",
              file=sys.stderr)
        return 1
    root = key_dir(key)
    inner_bazel.output_base = lambda _cwd: root
    try:
        return inner_bazel.main()
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
