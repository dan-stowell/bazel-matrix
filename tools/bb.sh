#!/bin/bash
# Runs a Bazel command on a BuildBuddy remote runner, e.g.
#   tools/bb.sh test //zlib/...
# The runner uses the executor image tools/remote.bazelrc pins, so the C++
# toolchain the inner Bazels autodetect on it works on the executors.
set -euo pipefail
cd "$(dirname "$0")/.."
image=$(grep -o 'container-image=[^ ]*' tools/remote.bazelrc | cut -d= -f2)
# A bigger runner than the default 6 CPUs / 7 GB: each inner Bazel reserves
# 2 CPUs and 2.5 GB, so this one runs about 8 at once instead of 2.
exec bb remote --container_image="$image" \
  --runner_exec_properties=EstimatedCPU=16 \
  --runner_exec_properties=EstimatedMemory=32GB \
  --runner_exec_properties=EstimatedFreeDiskBytes=100GB \
  "$@" --config=remote-minimal
