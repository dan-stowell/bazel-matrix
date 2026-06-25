"""Thin wrapper around the hermetic `gh` CLI for GitHub API enrichment.

Token handling (this is what makes `gh` usable inside `bazel run`):
  1. If GH_TOKEN or GITHUB_TOKEN is set in the environment, use it.
  2. Otherwise ask the (hermetic) gh for the host's stored token via
     `gh auth token` -- this reads ~/.config/gh, so an already-authenticated
     host `gh login` is picked up transparently.
The resolved token is then passed explicitly to every `gh api` call via
GH_TOKEN, so the binary never depends on a host-installed gh.
"""

import json
import os
import subprocess


class GhError(Exception):
    pass


def resolve_token(gh_path):
    """Return (token, source) or (None, None)."""
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val, var
    try:
        r = subprocess.run(
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), "gh auth token"
    except Exception:  # noqa: BLE001
        pass
    return None, None


class Gh:
    def __init__(self, gh_path, token=None):
        self.gh_path = gh_path
        self.token = token

    def _env(self):
        env = dict(os.environ)
        if self.token:
            env["GH_TOKEN"] = self.token
        env["GH_PROMPT_DISABLED"] = "true"
        env["GH_NO_UPDATE_NOTIFIER"] = "1"
        return env

    def api(self, path, jq=None, timeout=30):
        cmd = [self.gh_path, "api", path]
        if jq:
            cmd += ["--jq", jq]
        r = subprocess.run(
            cmd, capture_output=True, text=True, env=self._env(), timeout=timeout
        )
        if r.returncode != 0:
            raise GhError(r.stderr.strip() or f"gh api {path} failed")
        return r.stdout

    _REPO_JQ = (
        "{stars: .stargazers_count, archived: .archived, "
        "language: (.language // \"\"), pushed_at: (.pushed_at // \"\"), "
        "full_name: .full_name, description: (.description // \"\")}"
    )

    def repo_info(self, owner, repo):
        """Return a dict of repo metadata, following renames/redirects."""
        out = self.api(f"repos/{owner}/{repo}", jq=self._REPO_JQ)
        return json.loads(out)

    def repo_bazel_markers(self, owner, repo, markers):
        """Return which of `markers` exist at the repo's default-branch root.

        One API call (the root tree listing). A non-empty result means the repo
        itself ships Bazel build files — i.e. it's a first-party Bazel project,
        not merely something packaged for Bazel elsewhere (e.g. in the BCR).
        """
        out = self.api(f"repos/{owner}/{repo}/contents", jq=".[].name")
        names = set(out.split("\n"))
        return [m for m in markers if m in names]
