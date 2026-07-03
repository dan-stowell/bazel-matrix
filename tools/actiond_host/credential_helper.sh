#!/bin/sh
# Bazel forbids uplevel references in %workspace% rc paths, so this wrapper
# forwards to the repo-level BuildBuddy credential helper one directory up.
exec "$(dirname "$0")/../buildbuddy_credential_helper.py" "$@"
