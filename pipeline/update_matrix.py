#!/usr/bin/env python3
"""Promote a bazel-runner test result artifact into the matrix dataset."""

import argparse
import json
import os
import zipfile

from pipeline import inventory, matrix


def load_result(path):
    if not os.path.isabs(path):
        path = os.path.join(inventory.workspace_root(), path)
    if os.path.isdir(path):
        matches = []
        for root, _, files in os.walk(path):
            if "matrix-result.json" in files:
                matches.append(os.path.join(root, "matrix-result.json"))
        if len(matches) != 1:
            raise ValueError("{} contains {} matrix-result.json files; expected 1".format(
                path,
                len(matches),
            ))
        path = matches[0]

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            matches = [name for name in archive.namelist() if name.endswith("matrix-result.json")]
            if len(matches) != 1:
                raise ValueError("{} contains {} matrix result artifacts; expected 1".format(
                    path,
                    len(matches),
                ))
            return json.loads(archive.read(matches[0]))

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def apply_result(rows, artifact):
    if artifact.get("schema_version") != 1:
        raise ValueError("unsupported matrix result schema version")
    if artifact.get("command") != "test":
        raise ValueError("matrix result is not from a test job")
    result_key = artifact.get("result_key", "")
    if result_key not in dict(matrix.RESULT_COLUMNS):
        raise ValueError("unknown matrix result key {!r}".format(result_key))

    project = artifact.get("project", "")
    row = next((candidate for candidate in rows if candidate.get("name") == project), None)
    if row is None:
        row = inventory.find_row(rows, project)
    if row is None:
        raise ValueError("no matrix project matches {!r}".format(project))

    result = artifact.get("result")
    matrix.validate_result(row["name"], result_key, result)
    row["results"][result_key] = result
    return row, result_key


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True, help="matrix-result.json, outputs.zip, or containing directory")
    parser.add_argument("--matrix", help="matrix JSONL path")
    args = parser.parse_args(argv)

    matrix_path = args.matrix or inventory.default_matrix_path()
    rows = matrix.load(matrix_path)
    artifact = load_result(args.result)
    row, result_key = apply_result(rows, artifact)
    rows.sort(key=lambda item: (
        inventory.github_repo_slug(item["repo"]).lower(),
        item["name"].lower(),
    ))
    inventory.write_jsonl(matrix_path, rows)
    print("updated {} {} from {}".format(
        inventory.github_repo_slug(row["repo"]),
        result_key,
        args.result,
    ))


if __name__ == "__main__":
    main()
