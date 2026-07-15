# sonnet

Upstream: https://github.com/google-deepmind/sonnet

This is an inactive scaffold generated from `data/projects.jsonl`.

Next steps:

1. Choose a release tag or commit archive.
2. Add the archive URL, sha256, and filename to `_PROJECT_SOURCES` in `//bazel_runner:extension.bzl`.
3. Add the generated archive repo name to the `project_sources` `use_repo()` call in `MODULE.bazel`.
4. Update `strip_prefix` and build targets in `project.bzl`.
5. Activate `as_is/BUILD.bazel`, then `hermetic_llvm/BUILD.bazel`.
