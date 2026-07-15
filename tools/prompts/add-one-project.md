Advance the Bazel matrix project backlog until this invocation actually reaches
a test-bearing project.

Repository: /home/exedev/bazel-matrix

Goal:
- Add one realistic project to the active README matrix with verified results,
  or run far enough into one realistic candidate to prove why it cannot be added.
- Do not stop after pure metadata triage. If a candidate is rejected before any
  project test target is run, commit and push that triage finding, then continue
  to the next candidate in the same invocation.
- Commit and push each durable finding before moving on.
- Leave the worktree clean.

Candidate selection:
- Use data/projects.jsonl and data/project_tags.json.
- Skip candidates tagged "not_matrix_candidate" unless you are only improving their triage note.
- Prefer small BCR-backed projects with real upstream Bazel test targets.
- Prefer C++ projects first because the existing matrix and hermetic LLVM path are best established there.
- Do not add projects to the README status table until they have active matrix targets and measured results.

If a candidate is not realistic/useful:
- Add or update its entry in data/project_tags.json.
- Also update the matching row in data/projects.jsonl when the current snapshot
  contains that repository, so the queue skips it before the next full gather.
- Use tags such as:
  - not_matrix_candidate
  - no_upstream_bazel_tests
  - not_project
  - too_large_for_automatic_loop
  - incompatible_bazel_layout
- Include a short note explaining the decision.
- Run focused pipeline validation.
- Commit and push the tag update.
- If you did not run a real project build/test target for this candidate,
  continue to the next candidate instead of exiting.

If adding a real matrix project:
- Prefer bcr_module_source + bcr_project_from_spec when the candidate is in the Bazel Central Registry.
- Otherwise pin a GitHub release/archive with sha256.
- Activate the as_is and hermetic_llvm packages only after the source is valid.
- Run all four README columns:
  1. local as-is test
  2. local hermetic_llvm test
  3. RBE hermetic_llvm test
  4. RBE minimal image hermetic_llvm test
- Record pass/fail counts and BuildBuddy invocation links in README.md.
- If there is no normal upstream Bazel test target, tag the project instead of adding it to the table.
- Run buildifier on touched Bazel/Starlark files.
- Run any focused validation needed to prove the change.
- Commit and push.

Operational constraints:
- Keep going through pure triage candidates until one of these happens:
  1. you run at least one real project test target for a candidate, then finish
     that candidate by adding it to the README matrix or tagging it with the
     verified test/build failure reason;
  2. you have recorded and pushed 10 pure-triage candidates in this invocation;
  3. the invocation has spent roughly 90 minutes without reaching a test-bearing
     candidate.
- Once you have run a real project test target, finish that candidate cleanly,
  commit and push, then stop.
- If a previous automation run left a dirty worktree, inspect it first and either finish that work into a valid commit or report why it cannot be safely completed. Do not discard work blindly.
- Do not run broad or expensive sweeps beyond what is needed for one project.
- Prefer clear commits over large mixed changes.
