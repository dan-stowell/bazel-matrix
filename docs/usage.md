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

The repository has two structured project datasets. Matrix projects are
displayed and ordered in the README by their matrix project `name`; links still
point to the full GitHub repository URL:

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

Result statuses are `pass`, `mostly_pass`, `fail`, `no_tests`, and
`not_tracked`. When a sweep
has run, its result also records `passed`, runnable `total`, separately reported
`skipped` targets, and a BuildBuddy `invocation` URL. A completely passing run
uses `pass`; a run with a pass rate strictly greater than 90% uses
`mostly_pass`. Skipped targets are excluded from the pass-rate denominator.
Project-specific failure and exclusion context remains in the structured
`notes` field. Repositories intentionally excluded from the matrix carry
`not_matrix_candidate` tags and explanatory `tag_note` values in the all-known
dataset.

RBE jobs explicitly use `--remote_download_minimal` and `--jobs=32`. The former
avoids downloading remote outputs that are not required by local actions; the
latter caps inner-Bazel action concurrency at 32.

Each project test writes `matrix-result.json` as an undeclared test output. Run
the project normally:

```sh
bazel test //projects/grpc/as_is:grpc_local_test
```

Then explicitly promote its result artifact into the checked-in dataset:

```sh
bazel run //pipeline:update_matrix -- \
  --result bazel-testlogs/projects/grpc/as_is/grpc_local_test/test.outputs/matrix-result.json
```

The updater also accepts a containing directory or an `outputs.zip` produced by
a Bazel configuration that packages undeclared outputs.

The artifact is written even when the project test fails. It contains target
summaries, skipped-target counts, the inner BuildBuddy invocation, and case
counts aggregated from available test XML. Updating the dataset remains a
separate, intentional operation.

Results may incrementally add framework-level test case counts as XML result
collection is enabled for each project:

```json
"cases": {
  "passed": 85,
  "failed": 6,
  "skipped": 2,
  "complete": true
}
```

Case `failed` includes both assertion failures and framework-reported errors.
The case pass-rate denominator is `passed + failed`; skipped cases are shown
separately. `complete` indicates whether every executed test action supplied
structured case XML. Case and skipped-target counts remain structured data and
are intentionally not rendered in the compact README table. Case data may be
omitted until reliable collection is available.
