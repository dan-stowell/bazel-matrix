#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.parse

try:
    from python.runfiles import runfiles
except ImportError:
    runfiles = None


def resolve(rf, path):
    resolved = rf.Rlocation(path)
    if not resolved or not os.path.exists(resolved):
        sys.exit("kiss: could not resolve runfile %r -> %r" % (path, resolved))
    return resolved


def _file_uri_path(uri):
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "file":
        return None
    return urllib.parse.unquote(parsed.path)


def _safe_name(label):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    return name or "target"


def _load_bep_outputs(path):
    named_sets = {}
    completed_sets = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            event_id = event.get("id", {})
            if "namedSet" in event_id:
                named_sets[event_id["namedSet"]["id"]] = event.get("namedSetOfFiles", {})
                continue

            completed_id = event_id.get("targetCompleted")
            completed = event.get("completed")
            if not completed_id or not completed or not completed.get("success"):
                continue

            for group in completed.get("outputGroup", []):
                if group.get("name") != "default":
                    continue
                completed_sets.append((
                    completed_id.get("label", "target"),
                    [file_set["id"] for file_set in group.get("fileSets", [])],
                ))

    def files_for_set(set_id, seen=None):
        if seen is None:
            seen = set()
        if set_id in seen:
            return []
        seen.add(set_id)

        result = []
        named_set = named_sets.get(set_id, {})
        result.extend(named_set.get("files", []))
        for child in named_set.get("fileSets", []):
            result.extend(files_for_set(child["id"], seen))
        return result

    outputs = []
    seen = set()
    for label, set_ids in completed_sets:
        for set_id in set_ids:
            for file_event in files_for_set(set_id):
                uri = file_event.get("uri", "")
                path = _file_uri_path(uri)
                if not path or not os.path.isfile(path):
                    continue

                rel = os.path.join(*(file_event.get("pathPrefix", []) + [file_event.get("name", os.path.basename(path))]))
                arcname = os.path.join("outputs", _safe_name(label), rel)
                key = (label, path, arcname)
                if key in seen:
                    continue
                seen.add(key)
                outputs.append({
                    "label": label,
                    "path": path,
                    "arcname": arcname,
                    "digest": file_event.get("digest", ""),
                    "size": int(file_event.get("length", 0)),
                })
    return sorted(outputs, key=lambda output: output["arcname"])


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dedupe(items):
    seen = set()
    result = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices = ["build", "test"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source_subdir", default="")
    parser.add_argument("--bazel", required=True)
    parser.add_argument("--bundle", default="")
    parser.add_argument("--flag", action="append", default=[])
    parser.add_argument("--target", action="append", default=[])
    args = parser.parse_args(argv)

    if runfiles:
        rf = runfiles.Create()
        source = resolve(rf, args.source)
        bazel = resolve(rf, args.bazel)
    else:
        source = os.path.abspath(args.source)
        bazel = os.path.abspath(args.bazel)

    if args.source_subdir:
        source = os.path.abspath(os.path.join(source, args.source_subdir))

    print("kiss: source =", source, file=sys.stderr)
    print("kiss: bazel  =", bazel, file=sys.stderr)

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(_dedupe([
        os.path.join(source, ".kiss-tools"),
        env.get("PATH", ""),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]))
    startup_flags = []
    if args.mode == "build":
        output_user_root = os.path.abspath(".kiss-output-user-root")
        os.makedirs(output_user_root, exist_ok=True)
        startup_flags.append("--output_user_root=" + output_user_root)

    bep = os.path.join(os.environ.get("TEST_TMPDIR", os.getcwd()), "kiss.bep.json")
    command_flags = [
        "--color=no",
        "--curses=no",
        "--show_progress",
        "--show_progress_rate_limit=0.0",
        "--progress_report_interval=10",
    ] + list(args.flag)
    if os.path.isdir(os.path.join(source, ".kiss-tools")):
        command_flags = [
            "--action_env=PATH=" + env["PATH"],
            "--host_action_env=PATH=" + env["PATH"],
        ] + command_flags
    if args.mode == "test":
        command_flags = [
            "--test_output=errors",
            "--keep_going",
        ] + command_flags
    elif args.bundle:
        command_flags = ["--build_event_json_file=" + bep] + command_flags

    cmd = [
        bazel,
        "--batch",
        "--ignore_all_rc_files",
        "--nohome_rc",
        "--nosystem_rc",
    ] + startup_flags + [
        args.mode,
    ] + command_flags + ["--"] + args.target

    print("kiss: command =", " ".join(cmd), file=sys.stderr)
    proc = subprocess.run(cmd, cwd=source, env=env)
    if proc.returncode != 0:
        return proc.returncode

    if args.bundle:
        outputs = _load_bep_outputs(bep) if os.path.exists(bep) else []
        with tarfile.open(args.bundle, "w") as tar:
            if os.path.exists(bep):
                tar.add(bep, arcname="build.bep.json")
            for output in outputs:
                tar.add(output["path"], arcname=output["arcname"])
            manifest = {
                "mode": args.mode,
                "source": args.source,
                "targets": args.target,
                "flags": args.flag,
                "outputs": [
                    {
                        "label": output["label"],
                        "path": output["arcname"],
                        "size": os.path.getsize(output["path"]),
                        "sha256": _sha256(output["path"]),
                    }
                    for output in outputs
                ],
            }
            info = tarfile.TarInfo("manifest.json")
            data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            info.size = len(data)
            tar.addfile(info, fileobj=io.BytesIO(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
