"""Emit a deterministic JSONL queue of projects to consider for the matrix."""

import argparse
import json
import os
import sys

from pipeline import inventory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=None)
    parser.add_argument("--output", default="-")
    parser.add_argument("--top", type=int, default=50)
    parser.add_argument("--language", default=None)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--include-built", action="store_true")
    parser.add_argument("--require-first-party-bazel", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args(argv)

    path = args.input or inventory.default_snapshot_path()
    if not os.path.exists(path):
        print("snapshot not found: {}\nRun //pipeline:gather first.".format(path), file=sys.stderr)
        return 1

    rows = inventory.load_jsonl(path)
    candidates = inventory.candidate_rows(
        rows,
        include_built=args.include_built,
        language=args.language,
        require_first_party_bazel=args.require_first_party_bazel,
        min_score=args.min_score,
    )
    if args.top >= 0:
        candidates = candidates[:args.top]

    if args.output == "-":
        for row in candidates:
            json.dump(row, sys.stdout, ensure_ascii=False, sort_keys=True)
            sys.stdout.write("\n")
    else:
        inventory.write_jsonl(args.output, candidates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
