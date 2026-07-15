"""Render the product README from structured matrix status data."""

import argparse
import os
import sys

from pipeline import inventory, matrix
from pipeline import tags as tagmod


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default=None)
    parser.add_argument("--tags", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = inventory.workspace_root()
    matrix_path = args.matrix or inventory.default_matrix_path()
    tags_path = args.tags or tagmod.default_tags_path(root)
    output = args.output or os.path.join(root, "README.md")
    content = matrix.render(matrix.load(matrix_path), tagmod.load(tags_path))

    if args.check:
        try:
            with open(output, encoding="utf-8") as f:
                current = f.read()
        except FileNotFoundError:
            current = ""
        if current != content:
            print("{} is stale; run //pipeline:render_readme".format(output), file=sys.stderr)
            return 1
        return 0

    matrix.write(output, content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
