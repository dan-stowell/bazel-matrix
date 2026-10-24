#!/usr/bin/env python3
"""Bazel credential helper for BuildBuddy, used by the inner Bazels.

Returns the x-buildbuddy-api-key header from BUILDBUDDY_API_KEY if set, else
from the file tools/credentials.bzl writes; with neither, no credentials.
"""

import json
import os
import sys

# Keep in sync with tools/credentials.bzl.
KEY_FILE = "/tmp/bazel-matrix/buildbuddy-api-key"


def api_key(env=os.environ, key_file=KEY_FILE):
    key = env.get("BUILDBUDDY_API_KEY", "")
    if not key:
        try:
            with open(key_file) as f:
                key = f.read().strip()
        except OSError:
            pass
    return key


def main(argv=sys.argv):
    if len(argv) < 2 or argv[1] != "get":
        return 0
    sys.stdin.read()
    key = api_key()
    json.dump({"headers": {"x-buildbuddy-api-key": [key]}} if key else {}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
