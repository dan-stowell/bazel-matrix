"""Rank next project candidates from data/projects.jsonl."""

import argparse
import json
import os
import sys

from pipeline import model

def _load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def _as_project(row):
    owner, repo = model.parse_github(row.get("repo", "")) or ("", "")
    project = model.Project(owner=owner, repo_name=repo)
    project.name = row.get("name", "")
    project.category = row.get("category", model.CATEGORY_UNKNOWN)
    project.sources = list(row.get("sources", []))
    project.stars = int(row.get("stars") or 0)
    project.archived = bool(row.get("archived"))
    project.language = row.get("language") or ""
    project.pushed_at = row.get("pushed_at") or ""
    project.first_party_bazel = row.get("first_party_bazel")
    return project

def _project_dirs():
    base = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    projects = os.path.join(base, "projects")
    if not os.path.isdir(projects):
        return set()
    return {name.lower() for name in os.listdir(projects) if os.path.isdir(os.path.join(projects, name))}

def _flags(project):
    bcr = "BCR" if project.in_bcr else "   "
    if project.first_party_bazel is True:
        fp = "1st-party"
    elif project.first_party_bazel is False:
        fp = "ported   "
    else:
        fp = "?        "
    return "{} {}".format(bcr, fp)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--language", default=None)
    parser.add_argument("--include-built", action="store_true")
    args = parser.parse_args(argv)

    path = args.input
    if not path:
        base = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
        path = os.path.join(base, "data", "projects.jsonl")
    if not os.path.exists(path):
        print("snapshot not found: {}\nRun //pipeline:gather first.".format(path), file=sys.stderr)
        return 1

    rows = _load_jsonl(path)
    reference = max((row.get("pushed_at", "") for row in rows), default="")
    built = _project_dirs()
    candidates = []
    for row in rows:
        if row.get("category") != model.CATEGORY_PROJECT or row.get("archived"):
            continue
        if args.language and (row.get("language") or "") != args.language:
            continue
        slug = row.get("repo", "").rstrip("/").rsplit("/", 1)[-1].lower()
        if not args.include_built and slug in built:
            continue
        project = _as_project(row)
        candidates.append((model.candidate_score(project, reference), project))
    candidates.sort(key=lambda item: (-item[0], -item[1].stars, item[1].repo_url.lower()))

    print("{:>6}  {:>7}  {:<13}  {:<11} repo".format("score", "stars", "buildable", "language"))
    for score, project in candidates[:args.top]:
        print("{:>6.2f}  {:>7}  {:<13}  {:<11} {}".format(
            score,
            project.stars,
            _flags(project),
            project.language or "?",
            project.repo_url,
        ))
    return 0

if __name__ == "__main__":
    sys.exit(main())
