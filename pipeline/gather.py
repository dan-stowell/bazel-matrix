"""Gather public Bazel projects into deterministic JSONL.

Run:
  bazel run //pipeline:gather
  bazel run //pipeline:gather -- --enrich=none
  bazel run //pipeline:gather -- --output /tmp/projects.jsonl

Default output is $BUILD_WORKSPACE_DIRECTORY/data/projects.jsonl. Each line is
one project object, ordered by canonical GitHub repo URL.
"""

import argparse
import concurrent.futures
import json
import os
import sys

from pipeline import github as ghmod
from pipeline import inventory
from pipeline import model
from pipeline import tags as tagmod
from pipeline.sources import bcr, jin, nicolov

_SOURCES = [nicolov, jin, bcr]
_HERMETICBUILD_ORG = "hermeticbuild"

def _locate_gh(rlocation):
    if rlocation:
        try:
            from python.runfiles import runfiles

            path = runfiles.Create().Rlocation(rlocation)
            if path and os.path.exists(path):
                return path
        except Exception as exc:  # noqa: BLE001
            print("warning: could not resolve gh via runfiles: {}".format(exc), file=sys.stderr)
    from shutil import which

    return which("gh")

def _merge(projects):
    by_key = {}
    for project in projects:
        existing = by_key.get(project.key)
        if existing:
            existing.merge(project)
        else:
            by_key[project.key] = project
    return by_key

def _collect_static_sources():
    projects = []
    reports = []
    for source in _SOURCES:
        report = {"id": source.SOURCE_ID, "url": source.SOURCE_URL, "ok": False, "raw_count": 0}
        try:
            found = source.fetch()
            report["ok"] = True
            report["raw_count"] = len(found)
            projects.extend(found)
        except Exception as exc:  # noqa: BLE001
            report["error"] = str(exc)
            print("warning: source '{}' failed: {}".format(source.SOURCE_ID, exc), file=sys.stderr)
        reports.append(report)
    return projects, reports


def _collect_matrix_source(path):
    projects = []
    for row in inventory.load_jsonl(path):
        repo = model.parse_github(row.get("repo", ""))
        if not repo:
            continue
        owner, repo_name = repo
        projects.append(model.Project(
            owner=owner,
            repo_name=repo_name,
            name=row.get("name") or repo_name,
            category=model.CATEGORY_PROJECT,
            classification_reason="published in bazel-matrix",
            sources=["matrix"],
        ))
    return projects

def _collect_org_source(gh, org):
    projects = []
    for repo in gh.org_repos(org):
        full_name = repo.get("full_name", "")
        if "/" not in full_name:
            continue
        owner, repo_name = full_name.split("/", 1)
        project = model.Project(
            owner=owner,
            repo_name=repo_name,
            name=repo.get("name") or repo_name,
            description=repo.get("description") or "",
            category=model.CATEGORY_PROJECT,
            classification_reason="listed under GitHub org '{}'".format(org),
            sources=["github_org:" + org],
            enriched=True,
            stars=int(repo.get("stars") or 0),
            archived=bool(repo.get("archived")),
            language=repo.get("language") or "",
            pushed_at=repo.get("pushed_at") or "",
        )
        projects.append(project)
    return projects

def _enrich(projects, gh, workers=8, detect_bazel_min_stars=1000):
    def one(project):
        try:
            info = gh.repo_info(project.owner, project.repo_name)
        except ghmod.GhError:
            return
        full_name = info.get("full_name") or ""
        if "/" in full_name:
            project.owner, project.repo_name = full_name.split("/", 1)
        project.stars = int(info.get("stars") or 0)
        project.archived = bool(info.get("archived"))
        project.language = info.get("language") or ""
        project.pushed_at = info.get("pushed_at") or ""
        if not project.description:
            project.description = info.get("description") or ""
        project.enriched = True

        if detect_bazel_min_stars is not None and not project.archived and project.stars >= detect_bazel_min_stars:
            try:
                markers = gh.repo_bazel_markers(project.owner, project.repo_name, model.BAZEL_MARKERS)
                project.bazel_markers = markers
                project.first_party_bazel = bool(markers)
            except ghmod.GhError:
                pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, projects))

def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            json.dump(row, f, ensure_ascii=False, sort_keys=True)
            f.write("\n")

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gh-rlocation", default=None)
    parser.add_argument("--enrich", choices=["projects", "all", "none"], default="projects")
    parser.add_argument("--detect-bazel-min-stars", type=int, default=1000)
    parser.add_argument("--include-hermeticbuild-org", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--tags", default=None)
    parser.add_argument("--matrix", default=None)
    args = parser.parse_args(argv)

    base = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
    output = args.output
    if not output:
        output = os.path.join(base, "data", "projects.jsonl")
    tag_path = args.tags or tagmod.default_tags_path(base)
    matrix_path = args.matrix or inventory.default_matrix_path()
    tag_map = tagmod.load(tag_path)

    print("Gathering project sources...", file=sys.stderr)
    projects, reports = _collect_static_sources()
    if os.path.exists(matrix_path):
        matrix_projects = _collect_matrix_source(matrix_path)
        projects.extend(matrix_projects)
        reports.append({
            "id": "matrix",
            "url": matrix_path,
            "ok": True,
            "raw_count": len(matrix_projects),
        })
    by_key = _merge(projects)
    print("  {} unique repos from static sources".format(len(by_key)), file=sys.stderr)

    gh = None
    if args.enrich != "none" or args.include_hermeticbuild_org:
        gh_path = _locate_gh(args.gh_rlocation)
        if not gh_path:
            print("warning: gh not found; skipping GitHub enrichment and org sources", file=sys.stderr)
        else:
            token, token_source = ghmod.resolve_token(gh_path)
            if token:
                print("  using GitHub token from: {}".format(token_source), file=sys.stderr)
            else:
                print("warning: no GitHub token; requests may hit rate limits", file=sys.stderr)
            gh = ghmod.Gh(gh_path, token=token)

    if gh and args.include_hermeticbuild_org:
        report = {"id": "github_org:" + _HERMETICBUILD_ORG, "url": "https://github.com/" + _HERMETICBUILD_ORG, "ok": False, "raw_count": 0}
        try:
            org_projects = _collect_org_source(gh, _HERMETICBUILD_ORG)
            report["ok"] = True
            report["raw_count"] = len(org_projects)
            for project in org_projects:
                existing = by_key.get(project.key)
                if existing:
                    existing.merge(project)
                else:
                    by_key[project.key] = project
        except Exception as exc:  # noqa: BLE001
            report["error"] = str(exc)
            print("warning: hermeticbuild org source failed: {}".format(exc), file=sys.stderr)
        reports.append(report)

    projects = list(by_key.values())
    if gh and args.enrich != "none":
        targets = projects if args.enrich == "all" else [
            p for p in projects if p.category == model.CATEGORY_PROJECT
        ]
        detect_min = None if args.detect_bazel_min_stars < 0 else args.detect_bazel_min_stars
        print("  enriching {} repos via gh...".format(len(targets)), file=sys.stderr)
        _enrich(targets, gh, detect_bazel_min_stars=detect_min)
        projects = list(_merge(projects).values())

    reference = max((project.pushed_at for project in projects if project.pushed_at), default="")
    rows = [tagmod.annotate_row(project.to_dict(reference), tag_map) for project in projects]
    rows.sort(key=lambda row: row["repo"].lower())
    _write_jsonl(output, rows)

    counts = {
        "total": len(rows),
        "project": sum(1 for row in rows if row["category"] == model.CATEGORY_PROJECT),
        "ruleset": sum(1 for row in rows if row["category"] == model.CATEGORY_RULESET),
        "tooling": sum(1 for row in rows if row["category"] == model.CATEGORY_TOOLING),
        "unknown": sum(1 for row in rows if row["category"] == model.CATEGORY_UNKNOWN),
        "enriched": sum(1 for row in rows if row["enriched"]),
        "first_party_bazel": sum(1 for row in rows if row["first_party_bazel"]),
        "tagged": sum(1 for row in rows if row["tags"]),
        "ecosystem_tagged": sum(1 for row in rows if row["ecosystem_tags"]),
        "ruleset_tagged": sum(1 for row in rows if row["rulesets"]),
        "toolchain_tagged": sum(1 for row in rows if row["toolchains"]),
    }
    print("Wrote {}".format(output), file=sys.stderr)
    print("  reference_pushed_at={}".format(reference or "n/a"), file=sys.stderr)
    print("  counts={}".format(counts), file=sys.stderr)
    print("  sources={}".format(reports), file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
