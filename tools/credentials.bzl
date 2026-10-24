"""Hands BUILDBUDDY_API_KEY to the inner Bazels without putting it in any
outer action's key.

The repo rule reads the key from the outer client environment and writes it
to KEY_FILE on the machine running the outer Bazel (mode 0600). The repo
itself holds only a constant `marker` file: the inner build/test targets
depend on it so the repo, and so the key file, exist before they run, but the
key never becomes an action input or environment variable. The inner Bazels
read the key through tools/buildbuddy_credential_helper.py. The repo is not
marked reproducible, so the remote repo contents cache never serves it in
place of running it.
"""

# Keep in sync with tools/buildbuddy_credential_helper.py.
KEY_FILE = "/tmp/bazel-matrix/buildbuddy-api-key"

def _impl(rctx):
    key = rctx.getenv("BUILDBUDDY_API_KEY", "")
    if key:
        result = rctx.execute(
            ["sh", "-c", 'umask 077 && mkdir -p "$(dirname "$1")" && printf %s "$KEY" > "$1.tmp" && mv "$1.tmp" "$1"', "sh", KEY_FILE],
            environment = {"KEY": key},
        )
        if result.return_code:
            fail("could not write %s: %s" % (KEY_FILE, result.stderr))
    rctx.file("marker", "")
    rctx.file("REPO.bazel", "")
    rctx.file("BUILD.bazel", 'exports_files(["marker"])\n')

buildbuddy_credentials = repository_rule(implementation = _impl, local = True)
