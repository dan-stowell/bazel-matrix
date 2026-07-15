"""Thin wrapper around the hermetic GitHub CLI."""

import json
import os
import subprocess

class GhError(Exception):
    pass

def _profile_token():
    home = os.environ.get("HOME")
    if not home:
        return None
    try:
        result = subprocess.run(
            ["bash", "-lc", 'source "$HOME/.profile" >/dev/null 2>&1; printf "%s" "${BAZEL_MATRIX_GITHUB_TOKEN:-}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001
        return None
    token = result.stdout.strip()
    return token or None

def resolve_token(gh_path):
    for var in ("BAZEL_MATRIX_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val, var
    token = _profile_token()
    if token:
        return token, "$HOME/.profile:BAZEL_MATRIX_GITHUB_TOKEN"
    try:
        result = subprocess.run(
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), "gh auth token"
    except Exception:  # noqa: BLE001
        pass
    return None, None

class Gh:
    _REPO_JQ = (
        "{stars: .stargazers_count, archived: .archived, "
        "language: (.language // \"\"), pushed_at: (.pushed_at // \"\"), "
        "full_name: .full_name, description: (.description // \"\")}"
    )

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

    def api(self, path, jq=None, paginate=False, timeout=60):
        cmd = [self.gh_path, "api", path]
        if paginate:
            cmd.append("--paginate")
        if jq:
            cmd += ["--jq", jq]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=self._env(),
            timeout=timeout,
        )
        if result.returncode != 0:
            raise GhError(result.stderr.strip() or "gh api {} failed".format(path))
        return result.stdout

    def repo_info(self, owner, repo):
        return json.loads(self.api("repos/{}/{}".format(owner, repo), jq=self._REPO_JQ))

    def repo_bazel_markers(self, owner, repo, markers):
        out = self.api("repos/{}/{}/contents".format(owner, repo), jq=".[].name")
        names = set(out.splitlines())
        return [marker for marker in markers if marker in names]

    def org_repos(self, org):
        jq = (
            ".[] | {full_name: .full_name, name: .name, description: (.description // \"\"), "
            "stars: .stargazers_count, archived: .archived, language: (.language // \"\"), "
            "pushed_at: (.pushed_at // \"\")}"
        )
        out = self.api("orgs/{}/repos?per_page=100".format(org), jq=jq, paginate=True)
        repos = []
        for line in out.splitlines():
            if line.strip():
                repos.append(json.loads(line))
        return repos
