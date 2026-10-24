#!/usr/bin/env python3
"""Bazel credential helper for BuildBuddy, used by the inner Bazels.

Returns the x-buildbuddy-api-key header read from the file
$BAZEL_MATRIX_KEY_FILE names (written by tools/credentials.bzl); with no such
file, no credentials.
"""

import json
import os
import sys


def api_key(env=os.environ):
    try:
        with open(env.get("BAZEL_MATRIX_KEY_FILE", "")) as f:
            return f.read().strip()
    except OSError:
        return ""


def main(argv=sys.argv):
    if len(argv) < 2 or argv[1] != "get":
        return 0
    sys.stdin.read()
    key = api_key()
    json.dump({"headers": {"x-buildbuddy-api-key": [key]}} if key else {}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
