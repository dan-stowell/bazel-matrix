"""Structured matrix status data and README rendering helpers."""

import os
import urllib.parse

from pipeline import inventory

RESULT_COLUMNS = (
    ("as_is_local", "local as-is"),
    ("hermetic_llvm_local", "local hermetic LLVM"),
    ("hermetic_llvm_rbe", "BuildBuddy RBE"),
    ("hermetic_llvm_rbe_minimal", "BuildBuddy minimal RBE"),
)

STATUS_MARKERS = {
    "pass": "✅",
    "mostly_pass": "🟢",
    "fail": "❌",
    "no_tests": "🚫",
    "not_tracked": "💤",
}

_CASE_COUNT_FIELDS = ("passed", "failed", "skipped")


def _validate_cases(project, result_name, cases):
    if not isinstance(cases, dict):
        raise ValueError("{} has invalid {} cases".format(project, result_name))
    missing = [field for field in _CASE_COUNT_FIELDS + ("complete",) if field not in cases]
    if missing:
        raise ValueError("{} {} cases missing {}".format(
            project,
            result_name,
            ", ".join(missing),
        ))
    for field in _CASE_COUNT_FIELDS:
        value = cases[field]
        if type(value) is not int or value < 0:
            raise ValueError("{} has invalid {} cases {}".format(
                project,
                result_name,
                field,
            ))
    if type(cases["complete"]) is not bool:
        raise ValueError("{} has invalid {} cases complete".format(project, result_name))


def validate_result(project, result_name, result):
    if not isinstance(result, dict):
        raise ValueError("{} has invalid {} result".format(project, result_name))
    if result.get("status") not in STATUS_MARKERS:
        raise ValueError("{} has invalid {} status".format(project, result_name))
    has_passed = "passed" in result
    has_total = "total" in result
    if has_passed != has_total:
        raise ValueError("{} {} must have both passed and total".format(project, result_name))
    if has_passed:
        passed = result["passed"]
        total = result["total"]
        if (type(passed) is not int or type(total) is not int or
                passed < 0 or total < 0 or passed > total):
            raise ValueError("{} has invalid {} target counts".format(project, result_name))
    if "skipped" in result and (type(result["skipped"]) is not int or result["skipped"] < 0):
        raise ValueError("{} has invalid {} skipped count".format(project, result_name))
    if "invocation" in result:
        invocation = urllib.parse.urlparse(result["invocation"])
        if (invocation.scheme != "https" or not invocation.netloc or
                not invocation.path.startswith("/invocation/")):
            raise ValueError("{} has an invalid invocation URL".format(project))
    if "cases" in result:
        _validate_cases(project, result_name, result["cases"])


def load(path):
    rows = inventory.load_jsonl(path)
    expected_order = sorted(rows, key=lambda row: (
        inventory.github_repo_slug(row["repo"]).lower(),
        row["name"].lower(),
    ))
    if rows != expected_order:
        raise ValueError("matrix rows must be ordered by GitHub repo slug, then name")
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("matrix project names must be unique")
    for row in rows:
        for key, _ in RESULT_COLUMNS:
            result = row.get("results", {}).get(key)
            if not result:
                raise ValueError("{} has no {} result".format(row["name"], key))
            validate_result(row["name"], key, result)
    return rows


def result_cell(result):
    marker = STATUS_MARKERS[result["status"]]
    cell = marker
    if "passed" in result and "total" in result:
        counts = "{} / {}".format(result["passed"], result["total"])
        invocation = result.get("invocation")
        if invocation:
            counts = "[{}]({})".format(counts, invocation)
        cell += " " + counts
    return cell


def _readme_sort_key(row):
    slug = inventory.github_repo_slug(row["repo"])
    return (row["name"].lower(), slug.lower())


def table(rows):
    headers = ["project"] + [label for _, label in RESULT_COLUMNS]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in sorted(rows, key=_readme_sort_key):
        cells = ["[`{}`]({})".format(row["name"], row["repo"])]
        cells.extend(result_cell(row["results"][key]) for key, _ in RESULT_COLUMNS)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


EXPLICIT_RBE_USAGE = """# Running against another BuildBuddy endpoint

Inner Bazel invocations use the following environment variables. If they are
unset, they default to BuildBuddy Cloud (`remote.buildbuddy.io` and
`app.buildbuddy.io`):

```sh
export BUILDBUDDY_API_KEY='...'
export BUILDBUDDY_BES_RESULTS_URL='https://bazel-matrix.buildbuddy.dev/invocation/'
export BUILDBUDDY_GRPC_ENDPOINT='grpcs://bazel-matrix.buildbuddy.dev'
export BAZEL_RUNNER_REPO_CACHE='/absolute/path/to/bazel-matrix-repository-cache'
mkdir -p "$BAZEL_RUNNER_REPO_CACHE"
```

Run one project's tests without loading `.bazelrc` or `user.bazelrc`:

```sh
bazel --ignore_all_rc_files test \\
  --enable_bzlmod \\
  --noenable_workspace \\
  --jobs=1 \\
  --sandbox_writable_path="$BAZEL_RUNNER_REPO_CACHE" \\
  --test_env=BAZEL_RUNNER_REPO_CACHE \\
  --test_env=BUILDBUDDY_API_KEY \\
  --test_env=BUILDBUDDY_BES_RESULTS_URL \\
  --test_env=BUILDBUDDY_GRPC_ENDPOINT \\
  //projects/re2/hermetic_llvm:re2_rbe_test
```

The same flags work with an aggregate test suite:

```sh
bazel --ignore_all_rc_files test \\
  --enable_bzlmod \\
  --noenable_workspace \\
  --jobs=1 \\
  --sandbox_writable_path="$BAZEL_RUNNER_REPO_CACHE" \\
  --test_env=BAZEL_RUNNER_REPO_CACHE \\
  --test_env=BUILDBUDDY_API_KEY \\
  --test_env=BUILDBUDDY_BES_RESULTS_URL \\
  --test_env=BUILDBUDDY_GRPC_ENDPOINT \\
  //:smoke_hermetic_llvm_rbe_tests
```

For an individual or aggregate build, pass the same values through the action
environment instead:

```sh
bazel --ignore_all_rc_files build \\
  --enable_bzlmod \\
  --noenable_workspace \\
  --jobs=1 \\
  --sandbox_writable_path="$BAZEL_RUNNER_REPO_CACHE" \\
  --action_env=BAZEL_RUNNER_REPO_CACHE \\
  --action_env=BUILDBUDDY_API_KEY \\
  --action_env=BUILDBUDDY_BES_RESULTS_URL \\
  --action_env=BUILDBUDDY_GRPC_ENDPOINT \\
  //projects/re2/hermetic_llvm:re2_rbe_build

# Aggregate build:
# Replace the final target with //:smoke_hermetic_llvm_rbe_builds
```

These settings configure the inner Bazel process. Add outer `--bes_backend`,
`--bes_results_url`, and `--credential_helper` flags separately if the outer
orchestration invocation should also be published to BuildBuddy.
"""


def render(rows, tag_map):
    featured = [
        row for row in rows
        if "featured" in tag_map.get(row["repo"].rstrip("/").lower(), {}).get("tags", [])
    ]
    return "\n".join([
        "# bazel-matrix (🌿-💻)",
        "",
        "Here are working [Bazel](https://bazel.build/) builds and test suites for public projects.",
        "",
        "# Projects you may have heard of",
        "",
        table(featured),
        "",
        "# All projects",
        "",
        table(rows),
        "",
        EXPLICIT_RBE_USAGE.rstrip(),
        "",
    ])


def write(path, content):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
