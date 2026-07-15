"""Create an inactive scaffold for adding a discovered project to the matrix."""

import argparse
import json
import os
import sys
import textwrap

from pipeline import inventory
from pipeline import model


def _write(path, content, force=False):
    if os.path.exists(path) and not force:
        raise FileExistsError(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _project_bzl(slug, row):
    constant = inventory.starlark_constant(slug)
    archive = inventory.archive_repo_name(slug)
    description = (row.get("description") or row.get("name") or slug).replace("\n", " ")
    repo = row.get("repo") or ""
    return textwrap.dedent("""\
        load("//bazel_runner:defs.bzl", "LOCAL", "RBE", "build_spec", "project_spec", "tarball_source")

        # Candidate discovered by //pipeline:next_candidates.
        # Upstream: {repo}
        # Description: {description}
        #
        # TODO: add {archive} to _PROJECT_SOURCES in //bazel_runner:extension.bzl.
        # TODO: add "{archive}" to the project_sources use_repo() call in MODULE.bazel.
        # TODO: replace strip_prefix with the archive's top-level directory.
        # TODO: narrow the build targets once the project loads successfully.
        {constant} = project_spec(
            name = "{slug}",
            source = tarball_source(
                archive = "@{archive}//file",
                strip_prefix = "TODO",
            ),
            environments = [LOCAL, RBE],
            build = build_spec(targets = ["//..."]),
        )
        """).format(
        archive=archive,
        constant=constant,
        description=description,
        repo=repo,
        slug=slug,
    )


def _root_build():
    return 'exports_files(["candidate.json"])\n'


def _as_is_build(slug):
    constant = inventory.starlark_constant(slug)
    return textwrap.dedent("""\
        # Activate after the source archive is pinned in //bazel_runner:extension.bzl.
        #
        # load("//bazel_runner:defs.bzl", "matrix_project")
        # load("//projects/{slug}:project.bzl", "{constant}")
        #
        # matrix_project(project = {constant})
        """).format(constant=constant, slug=slug)


def _hermetic_build(slug):
    constant = inventory.starlark_constant(slug)
    return textwrap.dedent("""\
        # Activate after //projects/{slug}/as_is is active and builds locally.
        #
        # load("//bazel_runner:defs.bzl", "hermetic_llvm_project_modification")
        # load("//projects/{slug}:project.bzl", "{constant}")
        #
        # hermetic_llvm_project_modification(project = {constant})
        """).format(constant=constant, slug=slug)


def _readme(slug, row):
    return textwrap.dedent("""\
        # {slug}

        Upstream: {repo}

        This is an inactive scaffold generated from `data/projects.jsonl`.

        Next steps:

        1. Choose a release tag or commit archive.
        2. Add the archive URL, sha256, and filename to `_PROJECT_SOURCES` in `//bazel_runner:extension.bzl`.
        3. Add the generated archive repo name to the `project_sources` `use_repo()` call in `MODULE.bazel`.
        4. Update `strip_prefix` and build targets in `project.bzl`.
        5. Activate `as_is/BUILD.bazel`, then `hermetic_llvm/BUILD.bazel`.
        """).format(repo=row.get("repo") or "", slug=slug)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="GitHub repo URL, owner/repo, or discovered project slug")
    parser.add_argument("--input", default=None)
    parser.add_argument("--slug", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    snapshot = args.input or inventory.default_snapshot_path()
    if not os.path.exists(snapshot):
        print("snapshot not found: {}\nRun //pipeline:gather first.".format(snapshot), file=sys.stderr)
        return 1

    rows = inventory.load_jsonl(snapshot)
    row = inventory.find_row(rows, args.repo)
    if not row:
        print("project not found in snapshot: {}".format(args.repo), file=sys.stderr)
        return 1
    if row.get("category") != model.CATEGORY_PROJECT:
        print("refusing to scaffold non-project entry: {}".format(row.get("repo")), file=sys.stderr)
        return 1

    slug = args.slug or inventory.slug_from_repo(row.get("repo", ""))
    if not inventory.valid_project_slug(slug):
        print("invalid project slug: {}".format(slug), file=sys.stderr)
        return 1

    root = inventory.workspace_root()
    if not args.force and inventory.project_name_keys(slug).intersection(inventory.existing_project_keys(root)):
        print("project appears to already exist in the matrix: {}".format(slug), file=sys.stderr)
        return 1
    project_dir = os.path.join(root, "projects", slug)
    if os.path.exists(project_dir) and not args.force:
        print("project directory already exists: {}".format(project_dir), file=sys.stderr)
        return 1

    os.makedirs(project_dir, exist_ok=args.force)
    candidate = dict(row)
    candidate["slug"] = slug
    candidate["archive_repo"] = inventory.archive_repo_name(slug)
    candidate["starlark_constant"] = inventory.starlark_constant(slug)

    _write(os.path.join(project_dir, "candidate.json"), json.dumps(candidate, indent=2, sort_keys=True) + "\n", args.force)
    _write(os.path.join(project_dir, "README.md"), _readme(slug, row), args.force)
    _write(os.path.join(project_dir, "BUILD.bazel"), _root_build(), args.force)
    _write(os.path.join(project_dir, "project.bzl"), _project_bzl(slug, row), args.force)
    _write(os.path.join(project_dir, "as_is", "BUILD.bazel"), _as_is_build(slug), args.force)
    _write(os.path.join(project_dir, "hermetic_llvm", "BUILD.bazel"), _hermetic_build(slug), args.force)

    print("created inactive scaffold: {}".format(project_dir))
    print("archive repo: {}".format(candidate["archive_repo"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
