# Using bazel-matrix

## Running tests

Install [Bazelisk](https://github.com/bazelbuild/bazelisk#installation), then run
the local smoke suite:

```sh
bazel test //:smoke_as_is_local_tests
```

With a [BuildBuddy API key](https://www.buildbuddy.io/docs/quickstart/)
configured, run the hermetic LLVM smoke tests through BuildBuddy RBE:

```sh
bazel test //:smoke_hermetic_llvm_rbe_tests
```

To test one project:

```sh
bazel test //projects/re2/hermetic_llvm:re2_local_test
```

## Project data

The repository has two URL-ordered structured project datasets:

- `data/projects.jsonl` contains all Bazel projects known to the discovery
  pipeline.
- `data/matrix_projects.jsonl` contains the published matrix projects, their
  four test results, BuildBuddy invocation URLs, and any maintenance notes.

Candidate queues are derived from the known-project inventory. They are not a
separate stored dataset:

```sh
bazel run //pipeline:next_candidates
bazel run //pipeline:next_candidates -- --ruleset rules_go --no-require-first-party-bazel
```

The `featured` tag in `data/project_tags.json` controls the README's curated
"Projects you may have heard of" table.

## Updating the README

Generate `README.md` from the matrix dataset and project tags:

```sh
bazel run //pipeline:render_readme
```

Check that the committed README is current without modifying it:

```sh
bazel run //pipeline:render_readme -- --check
```

Result statuses are `pass`, `fail`, `no_tests`, and `not_tracked`. When a sweep
has run, its result also records `passed`, `total`, and a BuildBuddy
`invocation` URL. Project-specific failure and exclusion context remains in the
structured `notes` field. Repositories intentionally excluded from the matrix
carry `not_matrix_candidate` tags and explanatory `tag_note` values in the
all-known dataset.
