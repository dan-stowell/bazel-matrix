"""Rank museum candidates from an existing snapshot — offline, no network.

This is the "order the universe of next projects" tool. It reads the snapshot
written by //pipeline:gather and ranks PROJECT-category entries by candidate
score (recognition x alive x buildable; see pipeline/model.py), so picking the
next project to add is reproducible rather than an ad-hoc query.

    bazel run //pipeline:rank                      # top 30 candidates
    bazel run //pipeline:rank -- --top 50
    bazel run //pipeline:rank -- --language C++    # filter to one toolchain
    bazel run //pipeline:rank -- --by-language     # best-per-language coverage view
    bazel run //pipeline:rank -- --include-built   # don't hide what's already in

It recomputes the score from the raw fields, so it works on older snapshots that
predate the score being written into the file.
"""

import argparse
import json
import os
import sys

from pipeline import model

# Already in the museum (builds/<dir>) — hidden by default so the list answers
# "what's *next*". Keyed by repo slug (last path segment, lowercased).
_BUILT = {"abseil-cpp", "copybara", "cxx", "protobuf"}


def _slug(repo):
    return repo.rstrip("/").rsplit("/", 1)[-1].lower()


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _as_project(d):
    """Rebuild a model.Project from a snapshot dict (enough to score it)."""
    gh = model.parse_github(d.get("repo", "")) or ("", "")
    p = model.Project(owner=gh[0], repo_name=gh[1])
    p.name = d.get("name", "")
    p.category = d.get("category", model.CATEGORY_UNKNOWN)
    p.sources = list(d.get("sources", []))
    p.stars = int(d.get("stars") or 0)
    p.archived = bool(d.get("archived"))
    p.language = d.get("language") or ""
    p.pushed_at = d.get("pushed_at") or ""
    p.first_party_bazel = d.get("first_party_bazel")
    return p


def _flags(p):
    bcr = "BCR" if p.in_bcr else "   "
    if p.first_party_bazel is True:
        fp = "1st-party"
    elif p.first_party_bazel is False:
        fp = "ported   "
    else:
        fp = "?        "
    return f"{bcr} {fp}"


def _row(p, score):
    return (f"{score:>6.2f}  {p.stars:>7}  {_flags(p)}  "
            f"{(p.language or '?'):<11} {p.repo_url}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None,
                        help="snapshot path (default: $BUILD_WORKSPACE_DIRECTORY/data/projects.json)")
    parser.add_argument("--top", type=int, default=30, help="how many to show (default: 30)")
    parser.add_argument("--language", default=None, help="filter to one GitHub language")
    parser.add_argument("--by-language", action="store_true",
                        help="show the top few per language (toolchain-coverage view)")
    parser.add_argument("--include-built", action="store_true",
                        help="include projects already in the museum")
    args = parser.parse_args(argv)

    path = args.input
    if not path:
        base = os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()
        path = os.path.join(base, "data", "projects.json")
    if not os.path.exists(path):
        print(f"snapshot not found: {path}\nRun //pipeline:gather first.", file=sys.stderr)
        return 1

    doc = _load(path)
    reference = doc.get("reference_pushed_at") or max(
        (d.get("pushed_at", "") for d in doc["projects"]), default="")

    cands = []
    for d in doc["projects"]:
        if d.get("category") != model.CATEGORY_PROJECT or d.get("archived"):
            continue
        if not args.include_built and _slug(d.get("repo", "")) in _BUILT:
            continue
        if args.language and (d.get("language") or "") != args.language:
            continue
        p = _as_project(d)
        cands.append((model.candidate_score(p, reference), p))
    cands.sort(key=lambda sp: (-sp[0], -sp[1].stars, sp[1].key))

    header = f"{'score':>6}  {'stars':>7}  {'reg buildable':<13}  {'language':<11} repo"
    print(f"# museum candidates  (reference={reference or 'n/a'}, "
          f"{'incl. built' if args.include_built else 'excl. built'})")
    print(f"# score = log10(stars) x freshness x buildable(BCR=+1, 1st-party=+0.5)\n")

    if args.by_language:
        by_lang = {}
        for score, p in cands:
            by_lang.setdefault(p.language or "?", []).append((score, p))
        # Order languages by their best candidate's score.
        for lang in sorted(by_lang, key=lambda L: -by_lang[L][0][0]):
            rows = by_lang[lang][:5]
            print(f"\n## {lang}  ({len(by_lang[lang])} candidates)")
            print(header)
            for score, p in rows:
                print(_row(p, score))
        return 0

    print(header)
    for score, p in cands[:args.top]:
        print(_row(p, score))
    return 0


if __name__ == "__main__":
    sys.exit(main())
