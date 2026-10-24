#!/bin/bash
# Runs a Bazel command on a BuildBuddy remote runner, e.g.
#   tools/bb.sh test //zlib/...
# The runner uses the executor image tools/remote.bazelrc pins, so the C++
# toolchain the inner Bazels autodetect on it works on the executors.
set -euo pipefail
cd "$(dirname "$0")/.."
image=$(grep -o 'container-image=[^ ]*' tools/remote.bazelrc | cut -d= -f2)
exec bb remote --container_image="$image" "$@" --config=remote-minimal
