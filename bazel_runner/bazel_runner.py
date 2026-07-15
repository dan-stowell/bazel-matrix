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
import xml.etree.ElementTree as ET

try:
    from python.runfiles import runfiles
except ImportError:
    runfiles = None


def resolve(rf, path):
    resolved = rf.Rlocation(path)
    if not resolved or not os.path.exists(resolved):
        sys.exit("could not resolve runfile %r -> %r" % (path, resolved))
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


_PASSING_TEST_STATUSES = {"PASSED", "FLAKY"}


def _test_case_counts(path):
    root = ET.parse(path).getroot()
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for case in root.iter("testcase"):
        if case.find("skipped") is not None:
            counts["skipped"] += 1
        elif case.find("failure") is not None or case.find("error") is not None:
            counts["failed"] += 1
        else:
            counts["passed"] += 1
    return counts


def _matrix_status(passed, failed):
    total = passed + failed
    if total == 0:
        return "no_tests"
    if failed == 0:
        return "pass"
    if passed / total > 0.90:
        return "mostly_pass"
    return "fail"


def _load_test_result(path, job, returncode=0, console_outcomes=None):
    summaries = {}
    configured_tests = set()
    failed_completions = set()
    explicit_skips = set()
    attempts = {}
    invocation_id = ""

    with open(path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            event_id = event.get("id", {})
            if "started" in event_id:
                invocation_id = event.get("started", {}).get("uuid", "")

            configured_id = event_id.get("targetConfigured")
            configured = event.get("configured", {})
            if configured_id and "testSize" in configured:
                configured_tests.add(configured_id.get("label", ""))

            summary_id = event_id.get("testSummary")
            if summary_id:
                key = summary_id.get("label", "")
                summaries[key] = event.get("testSummary", {}).get("overallStatus", "NO_STATUS")

            completed_id = event_id.get("targetCompleted")
            completed = event.get("completed", {})
            if completed_id and completed.get("skipped"):
                explicit_skips.add(completed_id.get("label", ""))
            if completed_id and completed.get("success") is False:
                failed_completions.add(completed_id.get("label", ""))

            result_id = event_id.get("testResult")
            if result_id:
                base_key = (
                    result_id.get("label", ""),
                    result_id.get("configuration", {}).get("id", ""),
                    result_id.get("run", 0),
                    result_id.get("shard", 0),
                )
                attempt = result_id.get("attempt", 0)
                previous = attempts.get(base_key)
                if previous is None or attempt >= previous[0]:
                    attempts[base_key] = (attempt, event.get("testResult", {}))

    failed_completions.intersection_update(configured_tests)
    failed_completions.difference_update(summaries)
    unresolved = configured_tests.difference(summaries, failed_completions, explicit_skips)
    if returncode:
        # A failed build often emits no targetCompleted event for test targets
        # whose shared dependency failed. They are failed-to-build targets, not
        # skipped tests. On a successful invocation, the same absence represents
        # a configured test that Bazel intentionally did not run.
        failed_completions.update(unresolved)
    else:
        explicit_skips.update(unresolved)
    skipped = explicit_skips
    passed = sum(status in _PASSING_TEST_STATUSES for status in summaries.values())
    failed = len(summaries) - passed + len(failed_completions)
    if console_outcomes:
        console_labels = set(console_outcomes)
        if not configured_tests or console_labels == configured_tests:
            passed = sum(status in _PASSING_TEST_STATUSES for status in console_outcomes.values())
            failed = sum(
                status not in _PASSING_TEST_STATUSES and status != "SKIPPED"
                for status in console_outcomes.values()
            )
            skipped = {
                label for label, status in console_outcomes.items()
                if status == "SKIPPED"
            }
    cases = {"passed": 0, "failed": 0, "skipped": 0, "complete": True}
    xml_results = 0
    for _, result in attempts.values():
        xml_path = None
        for output in result.get("testActionOutput", []):
            if output.get("name") == "test.xml":
                xml_path = _file_uri_path(output.get("uri", ""))
                break
        if not xml_path or not os.path.isfile(xml_path):
            cases["complete"] = False
            continue
        try:
            counts = _test_case_counts(xml_path)
        except (ET.ParseError, OSError):
            cases["complete"] = False
            continue
        xml_results += 1
        for field in ("passed", "failed", "skipped"):
            cases[field] += counts[field]

    parts = job.split("/")
    project, variant, environment, command = (parts + [""] * 4)[:4]
    status = _matrix_status(passed, failed)
    if returncode and status in ("pass", "no_tests"):
        status = "fail"
    result = {
        "status": status,
        "passed": passed,
        "total": passed + failed,
    }
    if skipped:
        result["skipped"] = len(skipped)
    if attempts:
        result["cases"] = cases
    if invocation_id:
        result["invocation"] = "https://app.buildbuddy.io/invocation/" + invocation_id
    return {
        "schema_version": 1,
        "job": job,
        "project": project,
        "variant": variant,
        "environment": environment,
        "command": command,
        "exit_code": returncode,
        "result_key": "{}_{}".format(variant, environment),
        "result": result,
        "collection": {
            "configured_tests": len(configured_tests),
            "test_summaries": len(summaries),
            "failed_targets": failed,
            "test_attempts": len(attempts),
            "xml_results": xml_results,
        },
    }


def _write_test_result(bep, job, output_dir, returncode=0, console_outcomes=None):
    if not output_dir or not os.path.exists(bep):
        return None
    os.makedirs(output_dir, exist_ok=True)
    output = os.path.join(output_dir, "matrix-result.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            _load_test_result(bep, job, returncode, console_outcomes),
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")
    return output


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


_ENV_REF_RE = re.compile(r"\$(\w+)|\$\{([^}]+)\}")


def _expand_env_refs(value, env):
    def replace(match):
        name = match.group(1) or match.group(2)
        if name not in env:
            raise RuntimeError("environment variable {} is required by flag {!r}".format(name, value))
        return env[name]

    return _ENV_REF_RE.sub(replace, value)


def _log_prefix(job):
    return "[{}] ".format(job.replace("/", " ")) if job else ""


def _matrix_target(project, variant, environment, command):
    return "//projects/{}/{}:{}_{}_{}".format(project, variant, project, environment, command)


def _job_metadata(job):
    parts = job.split("/")
    if len(parts) != 4:
        return []

    project, variant, environment, command = parts
    return [
        "--build_metadata=ROLE=inner",
        "--build_metadata=PROJECT=" + project,
        "--build_metadata=VARIANT=" + variant,
        "--build_metadata=ENVIRONMENT=" + environment,
        "--build_metadata=COMMAND=" + command,
        "--build_metadata=MATRIX_JOB=" + job,
        "--tool_tag=" + _matrix_target(project, variant, environment, command),
    ]


_TARGET_OUTCOME_RE = re.compile(
    r"^(//\S+)\s+(FAILED TO BUILD|PASSED|FAILED|TIMEOUT|FLAKY|SKIPPED)(?:\s|$)"
)


def _record_target_outcome(line, outcomes):
    match = _TARGET_OUTCOME_RE.match(line)
    if match:
        outcomes[match.group(1)] = match.group(2)


def _run_with_prefix(cmd, cwd, env, prefix, outcomes=None):
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if outcomes is not None:
            _record_target_outcome(line, outcomes)
        sys.stderr.write(prefix + line)
    return proc.wait()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices = ["build", "test"], required=True)
    parser.add_argument("--job", default="")
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

    prefix = _log_prefix(args.job)

    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(_dedupe([
        os.path.join(source, ".bazel-runner-tools"),
        env.get("PATH", ""),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]))
    startup_flags = []
    if args.mode == "build":
        output_user_root = os.path.abspath(".bazel-runner-output-user-root")
        os.makedirs(output_user_root, exist_ok=True)
        startup_flags.append("--output_user_root=" + output_user_root)

    bep = os.path.join(os.environ.get("TEST_TMPDIR", os.getcwd()), "bazel_runner.bep.json")
    try:
        expanded_flags = [_expand_env_refs(flag, env) for flag in args.flag]
    except RuntimeError as e:
        print(prefix + "error: " + str(e), file=sys.stderr)
        return 2

    command_flags = [
        "--color=no",
        "--curses=no",
        "--show_progress",
        "--show_progress_rate_limit=0.0",
        "--progress_report_interval=10",
    ] + _job_metadata(args.job) + expanded_flags
    # Inner test invocations get a fresh output root inside the test sandbox,
    # so without a shared repository cache every run refetches all external
    # archives (the hermetic LLVM prebuilts alone are hundreds of MB). The
    # outer .bazelrc exports BAZEL_RUNNER_REPO_CACHE and makes it writable
    # inside the sandbox.
    repo_cache = os.environ.get("BAZEL_RUNNER_REPO_CACHE")
    if repo_cache:
        os.makedirs(repo_cache, exist_ok=True)
        command_flags = ["--repository_cache=" + repo_cache] + command_flags
    if os.path.isdir(os.path.join(source, ".bazel-runner-tools")):
        command_flags = [
            "--action_env=PATH=" + env["PATH"],
            "--host_action_env=PATH=" + env["PATH"],
        ] + command_flags
    if args.mode == "test":
        command_flags = [
            "--build_event_json_file=" + bep,
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

    console_outcomes = {} if args.mode == "test" else None
    returncode = _run_with_prefix(
        cmd,
        cwd=source,
        env=env,
        prefix=prefix,
        outcomes=console_outcomes,
    )
    if args.mode == "test":
        result_output = _write_test_result(
            bep,
            args.job,
            os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ""),
            returncode,
            console_outcomes,
        )
        if result_output:
            print(prefix + "matrix result: " + result_output, file=sys.stderr)
    if returncode != 0:
        return returncode

    if args.bundle:
        outputs = _load_bep_outputs(bep) if os.path.exists(bep) else []
        with tarfile.open(args.bundle, "w") as tar:
            for output in outputs:
                tar.add(output["path"], arcname=output["arcname"])
            manifest = {
                "mode": args.mode,
                "job": args.job,
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
