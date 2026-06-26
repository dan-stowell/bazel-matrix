#!/usr/bin/env python3
# Emit one TSV row per museum project for wild/verify.sh:
#   proj_dir <TAB> key <TAB> version <TAB> build_targets <TAB> test_targets
# (targets space-joined; empty field when the project declares none). Mirrors
# wild/gen_targets.py so the swept commands match the //wild/<project> targets.
import re
import pathlib

BUILD_OVERRIDE = {"doctest": ["//:doctest"]}


def labels(text, kind):
    m = re.search(kind + r"\s*\(\s*targets\s*=\s*\[(.*?)\]", text, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


root = pathlib.Path(__file__).resolve().parent.parent
for build_file in sorted((root / "builds").glob("*/BUILD.bazel")):
    text = build_file.read_text()
    if "museum_project(" not in text:
        continue
    proj = build_file.parent.name
    km = re.search(r'source_archive = "@([a-z0-9_]+)_archive//file"', text)
    if not km:
        continue
    key = km.group(1)
    vm = re.search(r'bazel_version = "([^"]+)"', text)
    version = vm.group(1) if vm else "9.1.1"
    build = BUILD_OVERRIDE.get(proj, labels(text, "build_spec"))
    test = labels(text, "test_spec")
    print("\t".join([proj, key, version, " ".join(build), " ".join(test)]))
