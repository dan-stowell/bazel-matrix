"""Shared helpers for project inventory commands."""

import json
import os
import re

from pipeline import model

_PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def workspace_root():
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()


def default_snapshot_path():
    return os.path.join(workspace_root(), "data", "projects.jsonl")


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            json.dump(row, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")


def existing_project_names(root=None):
    base = root or workspace_root()
    projects = os.path.join(base, "projects")
    if not os.path.isdir(projects):
        return set()
    return {
        name.lower()
        for name in os.listdir(projects)
        if os.path.isdir(os.path.join(projects, name)) and not name.startswith("_")
    }


def project_name_keys(name):
    lower = (name or "").lower()
    return {
        lower,
        lower.replace("-", "_"),
        lower.replace("_", "-"),
        re.sub(r"[^a-z0-9]+", "", lower),
    }


def existing_project_keys(root=None):
    keys = set()
    for name in existing_project_names(root):
        keys.update(project_name_keys(name))
    return keys


def slug_from_repo(repo_url):
    parsed = model.parse_github(repo_url)
    if not parsed:
        return ""
    repo = parsed[1].removesuffix(".git")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", repo).strip(".-")
    return slug.lower()


def starlark_constant(slug):
    value = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()
    if not value:
        return "PROJECT"
    if value[0].isdigit():
        value = "_" + value
    return value + "_PROJECT"


def archive_repo_name(slug):
    return re.sub(r"[^A-Za-z0-9_]+", "_", slug).strip("_") + "_archive"


def valid_project_slug(slug):
    return bool(_PROJECT_NAME_RE.match(slug or ""))


def find_row(rows, repo_or_slug):
    wanted = (repo_or_slug or "").strip().lower().rstrip("/")
    for row in rows:
        repo = (row.get("repo") or "").lower().rstrip("/")
        if repo == wanted:
            return row
        parsed = model.parse_github(repo)
        if parsed and "/".join(parsed).lower() == wanted:
            return row
        if slug_from_repo(repo) == wanted:
            return row
    return None


def candidate_reasons(row, built):
    reasons = []
    if row.get("first_party_bazel") is True:
        reasons.append("first_party_bazel")
    if row.get("in_bcr"):
        reasons.append("in_bcr")
    if row.get("stars"):
        reasons.append("stars")
    if row.get("pushed_at"):
        reasons.append("recent_activity")
    for source in row.get("sources", []):
        if source.startswith("github_org:hermeticbuild"):
            reasons.append("hermeticbuild_org")
    slug = slug_from_repo(row.get("repo", ""))
    if slug and not project_name_keys(slug).intersection(built):
        reasons.append("not_in_matrix")
    return reasons


def candidate_rows(rows, include_built=False, language=None, require_first_party_bazel=True, min_score=0.0):
    built = existing_project_keys()
    candidates = []
    for row in rows:
        if row.get("category") != model.CATEGORY_PROJECT or row.get("archived"):
            continue
        if require_first_party_bazel and row.get("first_party_bazel") is not True:
            continue
        if language and (row.get("language") or "") != language:
            continue
        slug = slug_from_repo(row.get("repo", ""))
        if not slug:
            continue
        if not include_built and project_name_keys(slug).intersection(built):
            continue
        score = float(row.get("candidate_score") or 0.0)
        if score < min_score:
            continue
        candidates.append({
            "repo": row.get("repo", ""),
            "slug": slug,
            "name": row.get("name") or slug,
            "candidate_score": score,
            "stars": int(row.get("stars") or 0),
            "language": row.get("language") or "",
            "pushed_at": row.get("pushed_at") or "",
            "first_party_bazel": row.get("first_party_bazel"),
            "bazel_markers": row.get("bazel_markers", []),
            "in_bcr": bool(row.get("in_bcr")),
            "sources": row.get("sources", []),
            "description": row.get("description") or "",
            "reasons": candidate_reasons(row, built),
            "next_step": "bazel run //pipeline:add_project -- {}".format(row.get("repo", "")),
        })
    candidates.sort(key=lambda row: (-row["candidate_score"], -row["stars"], row["repo"].lower()))
    return candidates
