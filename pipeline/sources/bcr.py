"""Source: Bazel Central Registry metadata."""

import io
import json
import re
import tarfile

from .. import classify, model, netfetch

SOURCE_ID = "bcr"
SOURCE_URL = "https://github.com/bazelbuild/bazel-central-registry"
_TARBALL = "https://codeload.github.com/bazelbuild/bazel-central-registry/tar.gz/refs/heads/main"

_BAZEL_DEP_RE = re.compile(r"\bbazel_dep\s*\((?P<args>.*?)\)", re.DOTALL)
_NAME_RE = re.compile(r"\bname\s*=\s*([\"'])(?P<name>[^\"']+)\1")


def _repo_from_metadata(meta):
    for entry in meta.get("repository", []) or []:
        if entry.startswith("github:"):
            spec = entry[len("github:"):]
            if "/" in spec:
                owner, _, repo = spec.partition("/")
                if owner and repo:
                    return owner, repo
    return model.parse_github(meta.get("homepage", ""))


def _direct_dependencies(module_text):
    # Removing comment-only lines prevents disabled bazel_dep calls from being
    # mistaken for active dependencies while retaining normal multiline calls.
    text = "\n".join(
        line for line in module_text.splitlines()
        if not line.lstrip().startswith("#")
    )
    dependencies = set()
    for match in _BAZEL_DEP_RE.finditer(text):
        name = _NAME_RE.search(match.group("args"))
        if name:
            dependencies.add(name.group("name"))
    return dependencies


def _latest_version(meta):
    versions = meta.get("versions", []) or []
    yanked = meta.get("yanked_versions", {}) or {}
    available = [version for version in versions if version not in yanked]
    return (available or versions or [""])[-1]


def parse(tar_bytes):
    modules = {}
    module_files = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if "modules" not in parts:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            module_index = parts.index("modules")
            relative = parts[module_index + 1:]
            if len(relative) == 2 and relative[1] == "metadata.json":
                try:
                    modules[relative[0]] = json.loads(f.read().decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            elif len(relative) == 3 and relative[2] == "MODULE.bazel":
                try:
                    module_files[(relative[0], relative[1])] = f.read().decode("utf-8")
                except UnicodeDecodeError:
                    pass

    projects = []
    module_owners = {}
    for module_name, meta in modules.items():
        repo = _repo_from_metadata(meta)
        module_owners[module_name] = repo[0] if repo else ""

    for module_name, meta in modules.items():
        repo = _repo_from_metadata(meta)
        if not repo:
            continue
        owner, repo_name = repo
        category, reason = classify.classify_bcr(module_name, owner)
        version = _latest_version(meta)
        dependencies = _direct_dependencies(module_files.get((module_name, version), ""))
        rulesets = sorted(
            dependency for dependency in dependencies
            if classify.is_ruleset_module(dependency, module_owners.get(dependency, ""))
        )
        toolchains = sorted(
            dependency for dependency in dependencies
            if classify.is_toolchain_module(dependency)
        )
        projects.append(model.Project(
            owner=owner,
            repo_name=repo_name,
            name=module_name,
            category=category,
            classification_reason="BCR: " + reason,
            sources=[SOURCE_ID],
            rulesets=rulesets,
            toolchains=toolchains,
        ))
    return projects


def fetch():
    return parse(netfetch.get_bytes(_TARBALL))
