"""Hands BUILDBUDDY_API_KEY to the inner Bazels without putting it, or
anything that depends on where it's kept, in any outer action's key.

The repo rule reads the key from the outer client environment and writes it
(mode 0600) into the outer output base, as KEY_FILE, or deletes that file
when the variable is unset. Each outer workspace has its own output base, so
workspaces can't see each other's keys. The repo itself holds only a
constant `marker`: the inner build and test targets take it as an input so
the repo, and so the key file, exist before they run. tools/inner_bazel.py
finds the output base from its own working directory at execution time and
hands the file's path to the inner Bazels' credential helper
(tools/buildbuddy_credential_helper.py). The repo is not marked
reproducible, so the remote repo contents cache never serves it in place of
running it.
"""

# Relative to the output base; keep in sync with tools/inner_bazel.py.
KEY_FILE = "bazel-matrix/api-key"

def _impl(rctx):
    # <output base>/external/<this repo>
    key_file = "%s/%s" % (rctx.path(".").dirname.dirname, KEY_FILE)
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

    # Where earlier versions of this rule kept the key.
    rctx.execute(["rm", "-rf", "/tmp/bazel-matrix/buildbuddy-api-key", "/tmp/bazel-matrix/credentials"])
    rctx.file("marker", "")
    rctx.file("REPO.bazel", "")
    rctx.file("BUILD.bazel", 'exports_files(["marker"])\n')

buildbuddy_credentials = repository_rule(implementation = _impl, local = True)
