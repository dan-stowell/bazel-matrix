"""Gather public projects that build with Bazel into data/projects.json.

Run it:  bazel run //pipeline:gather
         bazel run //pipeline:gather -- --enrich=none      # offline, no gh
         bazel run //pipeline:gather -- --enrich=all       # enrich rulesets too

The output is written to $BUILD_WORKSPACE_DIRECTORY/data/projects.json (i.e.
back into the source tree) so it can be committed as the project's snapshot.
Output is deterministic (sorted, no timestamps) to keep diffs meaningful.
"""

import argparse
import concurrent.futures
import json
import os
import sys

from pipeline import github as ghmod
from pipeline import model
from pipeline.sources import bcr, jin, nicolov

_SOURCES = [nicolov, jin, bcr]
_CATEGORY_ORDER = {
    model.CATEGORY_PROJECT: 0,
    model.CATEGORY_UNKNOWN: 1,
    model.CATEGORY_RULESET: 2,
    model.CATEGORY_TOOLING: 3,
}


def _locate_gh(rlocation):
    """Resolve the hermetic gh binary from runfiles, or fall back to PATH."""
    if rlocation:
        try:
            from python.runfiles import runfiles

            r = runfiles.Create()
            path = r.Rlocation(rlocation)
            if path and os.path.exists(path):
                return path
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not resolve gh via runfiles: {exc}", file=sys.stderr)
    # Fall back to a host gh if present (keeps the tool usable outside Bazel).
    from shutil import which

    return which("gh")


def _collect():
    """Fetch every source; return (projects_by_key, source_reports)."""
    by_key = {}
    reports = []
    for src in _SOURCES:
        report = {"id": src.SOURCE_ID, "url": src.SOURCE_URL, "ok": False, "raw_count": 0}
        try:
            found = src.fetch()
            report["ok"] = True
            report["raw_count"] = len(found)
            for proj in found:
                existing = by_key.get(proj.key)
                if existing:
                    existing.merge(proj)
                else:
                    by_key[proj.key] = proj
        except Exception as exc:  # noqa: BLE001
            report["error"] = str(exc)
            print(f"warning: source '{src.SOURCE_ID}' failed: {exc}", file=sys.stderr)
        reports.append(report)
    return by_key, reports


def _enrich(projects, gh, workers=8, detect_bazel_min_stars=None):
    """Fill in stars/archived/etc. via gh, concurrently. Mutates in place.

    If detect_bazel_min_stars is not None, additionally probe each project that
    clears that star threshold for first-party Bazel build files (one extra API
    call per probed repo). Gating by stars keeps the probe cheap: we only care
    about first-party status for plausible candidates.
    """
    def one(proj):
        try:
            info = gh.repo_info(proj.owner, proj.repo_name)
        except ghmod.GhError:
            return  # repo gone/renamed/inaccessible: leave unenriched
        # gh follows renames/redirects; adopt the canonical owner/repo so that
        # aliases (e.g. google/protobuf -> protocolbuffers/protobuf) dedupe.
        full = info.get("full_name") or ""
        if "/" in full:
            proj.owner, proj.repo_name = full.split("/", 1)
        proj.stars = int(info.get("stars") or 0)
        proj.archived = bool(info.get("archived"))
        proj.language = info.get("language") or ""
        proj.pushed_at = info.get("pushed_at") or ""
        if not proj.description:
            proj.description = info.get("description") or ""
        proj.enriched = True

        if (detect_bazel_min_stars is not None
                and not proj.archived
                and proj.stars >= detect_bazel_min_stars):
            try:
                markers = gh.repo_bazel_markers(
                    proj.owner, proj.repo_name, model.BAZEL_MARKERS)
                proj.bazel_markers = markers
                proj.first_party_bazel = bool(markers)
            except ghmod.GhError:
                pass  # leave first_party_bazel = None (unknown)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, projects))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gh-rlocation", default=None,
                        help="runfiles path to the hermetic gh binary")
    parser.add_argument("--enrich", choices=["projects", "all", "none"], default="projects",
                        help="which entries to enrich via the GitHub API (default: projects)")
    parser.add_argument("--detect-bazel-min-stars", type=int, default=1000,
                        help="probe projects with >= this many stars for first-party "
                             "Bazel build files (one extra API call each); set to -1 "
                             "to skip the probe (default: 1000)")
    parser.add_argument("--output", default=None,
                        help="output path (default: $BUILD_WORKSPACE_DIRECTORY/data/projects.json)")
    args = parser.parse_args(argv)

    output = args.output
    if not output:
        workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
        base = workspace if workspace else os.getcwd()
        output = os.path.join(base, "data", "projects.json")

    print("Gathering projects from sources...", file=sys.stderr)
    by_key, reports = _collect()
    projects = list(by_key.values())
    print(f"  {len(projects)} unique repos from {len(_SOURCES)} sources", file=sys.stderr)

    # Enrichment via hermetic gh.
    if args.enrich != "none":
        gh_path = _locate_gh(args.gh_rlocation)
        if not gh_path:
            print("warning: gh not found; skipping enrichment", file=sys.stderr)
        else:
            token, token_src = ghmod.resolve_token(gh_path)
            if token:
                print(f"  using gh token from: {token_src}", file=sys.stderr)
            else:
                print("warning: no gh token; enrichment may hit rate limits", file=sys.stderr)
            gh = ghmod.Gh(gh_path, token=token)
            targets = projects if args.enrich == "all" else [
                p for p in projects if p.category == model.CATEGORY_PROJECT
            ]
            print(f"  enriching {len(targets)} repos via gh...", file=sys.stderr)
            detect_min = None if args.detect_bazel_min_stars < 0 else args.detect_bazel_min_stars
            _enrich(targets, gh, detect_bazel_min_stars=detect_min)
            # Canonicalization may have collapsed aliases onto the same repo;
            # re-dedupe by (now canonical) key.
            merged = {}
            for p in projects:
                existing = merged.get(p.key)
                if existing:
                    existing.merge(p)
                else:
                    merged[p.key] = p
            projects = list(merged.values())
            print(f"  {len(projects)} unique repos after canonicalization", file=sys.stderr)

    # Calibrate freshness against the most recent activity in the snapshot, so
    # candidate scores are deterministic (no wall-clock dependence).
    reference = max((p.pushed_at for p in projects if p.pushed_at), default="")

    # Order projects by candidate score (best first) within the project
    # category; other categories keep the stars ordering.
    projects.sort(key=lambda p: (
        _CATEGORY_ORDER.get(p.category, 9),
        -model.candidate_score(p, reference),
        -p.stars,
        p.key,
    ))

    counts = {"total": len(projects)}
    for cat in (model.CATEGORY_PROJECT, model.CATEGORY_RULESET,
                model.CATEGORY_TOOLING, model.CATEGORY_UNKNOWN):
        counts[cat] = sum(1 for p in projects if p.category == cat)
    counts["enriched"] = sum(1 for p in projects if p.enriched)
    counts["first_party_bazel"] = sum(1 for p in projects if p.first_party_bazel)

    # A quick-glance leaderboard of the strongest candidates.
    top = [p for p in projects
           if p.category == model.CATEGORY_PROJECT and not p.archived][:30]
    top_candidates = [{
        "name": p.name or p.repo_name,
        "repo": p.repo_url,
        "language": p.language,
        "stars": p.stars,
        "in_bcr": p.in_bcr,
        "first_party_bazel": p.first_party_bazel,
        "candidate_score": model.candidate_score(p, reference),
    } for p in top]

    doc = {
        "schema_version": 2,
        "generator": "bazel run //pipeline:gather",
        "reference_pushed_at": reference,
        "sources": reports,
        "counts": counts,
        "top_candidates": top_candidates,
        "projects": [p.to_dict(reference) for p in projects],
    }

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")

    print(f"\nWrote {output}", file=sys.stderr)
    print(f"  {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
