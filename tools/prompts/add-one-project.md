Add exactly one unit of progress to the Bazel matrix project backlog.

Repository: /home/exedev/bazel-matrix

Goal:
- Either add one realistic project to the active README matrix with verified results, or record one candidate as not useful for the matrix.
- Commit and push the result before exiting.
- Leave the worktree clean.

Candidate selection:
- Use data/projects.jsonl and data/project_tags.json.
- Skip candidates tagged "not_matrix_candidate" unless you are only improving their triage note.
- Prefer small BCR-backed projects with real upstream Bazel test targets.
- Prefer C++ projects first because the existing matrix and hermetic LLVM path are best established there.
- Do not add projects to the README status table until they have active matrix targets and measured results.

If a candidate is not realistic/useful:
- Add or update its entry in data/project_tags.json.
- Use tags such as:
  - not_matrix_candidate
  - no_upstream_bazel_tests
  - not_project
  - too_large_for_automatic_loop
  - incompatible_bazel_layout
- Include a short note explaining the decision.
- Run focused pipeline validation.
- Commit and push the tag update.

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
- Make one bounded attempt, then stop.
- If a previous automation run left a dirty worktree, inspect it first and either finish that work into a valid commit or report why it cannot be safely completed. Do not discard work blindly.
- Do not run broad or expensive sweeps beyond what is needed for one project.
- Prefer clear commits over large mixed changes.
