"""Repo tag metadata for candidate triage."""

import json
import os

DEFAULT_EXCLUDED_TAGS = ("not_matrix_candidate",)


def canonical_repo(repo):
    return (repo or "").strip().rstrip("/").lower()


def default_tags_path(workspace_root):
    return os.path.join(workspace_root, "data", "project_tags.json")


def load(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    result = {}
    for repo, value in raw.items():
        key = canonical_repo(repo)
        if not key:
            continue
        if isinstance(value, list):
            result[key] = {"tags": sorted(set(value)), "note": ""}
        else:
            result[key] = {
                "tags": sorted(set(value.get("tags", []))),
                "note": value.get("note", ""),
            }
    return result


def annotate_row(row, tag_map):
    info = tag_map.get(canonical_repo(row.get("repo", "")), {})
    tags = sorted(info.get("tags", []))
    row["tags"] = tags
    row["tag_note"] = info.get("note", "")
    return row


def has_excluded_tag(row, excluded_tags=DEFAULT_EXCLUDED_TAGS):
    return bool(set(row.get("tags", [])).intersection(excluded_tags))
