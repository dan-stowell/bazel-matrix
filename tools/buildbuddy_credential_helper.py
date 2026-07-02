#!/usr/bin/env python3
"""Bazel credential helper for BuildBuddy.

When BUILDBUDDY_API_KEY is set, Bazel uses this for BuildBuddy gRPC requests
including BEP-referenced test log uploads. Without the variable, the helper
returns no credentials so fresh clones still work without local secrets.
"""

import json
import os
import sys


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] != "get":
        return 0

    # Consume the helper request even though the BuildBuddy header is only
    # controlled by the environment.
    sys.stdin.read()

    api_key = os.environ.get("BUILDBUDDY_API_KEY")
    if api_key:
        json.dump({"headers": {"x-buildbuddy-api-key": [api_key]}}, sys.stdout)
    else:
        json.dump({}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
