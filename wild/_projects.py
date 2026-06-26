#!/usr/bin/env python3
# Emit one TSV row per unique museum project: archive_key, bazel_version, targets.
# Read by wild/sweep.sh. The archive_key is what wild/build.sh looks up in
# //tools/fetch:extension.bzl; bazel_version is the museum's known-good inner
# (default 9.1.1); targets is the museum's curated *build* target(s) — a bounded,
# meaningful surface (//... is impractical for grpc/protobuf/bazel). Falls back to
# the test targets, then //..., when a project declares no build_spec.
import re, pathlib, sys

def labels(block, kind):
    m = re.search(kind + r'\s*\(\s*targets\s*=\s*\[(.*?)\]', block, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []

best = {}
for b in sorted(pathlib.Path("builds").glob("*/BUILD.bazel")):
    t = b.read_text()
    if "museum_project(" not in t:
        continue
    km = re.search(r'source_archive = "@([a-z0-9_]+)_archive//file"', t)
    if not km:
        continue
    key = km.group(1)
    ver = re.search(r'bazel_version = "([^"]+)"', t)
    ver = ver.group(1) if ver else "9.1.1"
    tgts = labels(t, "build_spec") or labels(t, "test_spec") or ["//..."]
    # First dir for a key wins, but prefer one that actually has a build_spec.
    if key not in best or (best[key][2] == ["//..."] and tgts != ["//..."]):
        best[key] = (key, ver, tgts)

for key, ver, tgts in best.values():
    print(f"{key}\t{ver}\t{' '.join(tgts)}")
