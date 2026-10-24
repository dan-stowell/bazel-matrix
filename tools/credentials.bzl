"""Hands BUILDBUDDY_API_KEY to the inner Bazels without putting it in any
outer action's key.

The repo rule reads the key from the outer client environment and writes it
(mode 0600) to a file outside the repo, scoped to the outer workspace, or
deletes that file when the variable is unset. The repo itself holds only
`key_file`, naming that file: the inner build and test targets take it as an
input, so the repo exists before they run, and pass the name on to the inner
Bazels' credential helper (tools/buildbuddy_credential_helper.py). The key is
never an action input or environment variable. The repo is not marked
reproducible, so the remote repo contents cache never serves it in place of
running it.
"""

def _impl(rctx):
    scope = str(rctx.workspace_root).strip("/").replace("/", "_")
    key_file = "/tmp/bazel-matrix/credentials/%s/api-key" % scope
    key = rctx.getenv("BUILDBUDDY_API_KEY", "")
    if key:
        result = rctx.execute(
            ["sh", "-c", 'umask 077 && mkdir -p "$(dirname "$1")" && printf %s "$KEY" > "$1.tmp" && mv "$1.tmp" "$1"', "sh", key_file],
            environment = {"KEY": key},
        )
        if result.return_code:
            fail("could not write %s: %s" % (key_file, result.stderr))
    else:
        # Don't leave an earlier run's key behind.
        rctx.execute(["rm", "-f", key_file])
    # Where an earlier version of this rule kept the key.
    rctx.execute(["rm", "-f", "/tmp/bazel-matrix/buildbuddy-api-key"])
    rctx.file("key_file", key_file + "\n")
    rctx.file("REPO.bazel", "")
    rctx.file("BUILD.bazel", 'exports_files(["key_file"])\n')

buildbuddy_credentials = repository_rule(implementation = _impl, local = True)
