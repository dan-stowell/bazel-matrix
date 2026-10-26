#!/usr/bin/env python3
"""Credential helper for an outer Bazel with --config=inner-remote.

Like tools/buildbuddy_credential_helper.py (the x-buildbuddy-api-key header
from the file $BAZEL_MATRIX_KEY_FILE names), plus
`x-buildbuddy-platform.env-overrides: BUILDBUDDY_API_KEY=<key>`, so the
projects' tests running on RBE get the key in their environment
(tools/remote_inner_bazel.py). BuildBuddy keeps env-overrides out of the
action key and redacts them; as a helper's header the key stays off Bazel's
command line, so out of its logs and build event files too. Only for the
outer Bazel: an inner Bazel with it would hand the key to every action.
"""

import json
import sys

from buildbuddy_credential_helper import api_key


def main(argv=sys.argv):
    if len(argv) < 2 or argv[1] != "get":
        return 0
    sys.stdin.read()
    key = api_key()
    headers = {
        "x-buildbuddy-api-key": [key],
        "x-buildbuddy-platform.env-overrides": ["BUILDBUDDY_API_KEY=" + key],
    } if key else {}
    json.dump({"headers": headers} if headers else {}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
