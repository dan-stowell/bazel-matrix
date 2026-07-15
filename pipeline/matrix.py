"""Structured matrix status data and README rendering helpers."""

import os

from pipeline import inventory

RESULT_COLUMNS = (
    ("as_is_local", "local as-is"),
    ("hermetic_llvm_local", "local hermetic LLVM"),
    ("hermetic_llvm_rbe", "BuildBuddy RBE"),
    ("hermetic_llvm_rbe_minimal", "BuildBuddy minimal RBE"),
)

STATUS_MARKERS = {
    "pass": "✅",
    "fail": "❌",
    "no_tests": "🚫",
    "not_tracked": "💤",
}


def load(path):
    rows = inventory.load_jsonl(path)
    expected_order = sorted(rows, key=lambda row: (row["repo"].lower(), row["name"].lower()))
    if rows != expected_order:
        raise ValueError("matrix rows must be ordered by repo URL, then name")
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("matrix project names must be unique")
    for row in rows:
        for key, _ in RESULT_COLUMNS:
            result = row.get("results", {}).get(key)
            if not result:
                raise ValueError("{} has no {} result".format(row["name"], key))
            if result.get("status") not in STATUS_MARKERS:
                raise ValueError("{} has invalid {} status".format(row["name"], key))
            if "invocation" in result and not result["invocation"].startswith(
                    "https://app.buildbuddy.io/invocation/"):
                raise ValueError("{} has an invalid invocation URL".format(row["name"]))
    return rows


def result_cell(result):
    marker = STATUS_MARKERS[result["status"]]
    if "passed" not in result or "total" not in result:
        return marker
    counts = "{} / {}".format(result["passed"], result["total"])
    invocation = result.get("invocation")
    if invocation:
        counts = "[{}]({})".format(counts, invocation)
    return "{} {}".format(marker, counts)


def table(rows):
    headers = ["project"] + [label for _, label in RESULT_COLUMNS]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        display_name = row.get("display_name") or row["name"]
        cells = ["[`{}`]({})".format(display_name, row["repo"])]
        cells.extend(result_cell(row["results"][key]) for key, _ in RESULT_COLUMNS)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


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
    ])


def write(path, content):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
