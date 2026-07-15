"""Source: Bazel Central Registry metadata."""

import io
import json
import tarfile

from .. import classify, model, netfetch

SOURCE_ID = "bcr"
SOURCE_URL = "https://github.com/bazelbuild/bazel-central-registry"
_TARBALL = "https://codeload.github.com/bazelbuild/bazel-central-registry/tar.gz/refs/heads/main"

def _repo_from_metadata(meta):
    for entry in meta.get("repository", []) or []:
        if entry.startswith("github:"):
            spec = entry[len("github:"):]
            if "/" in spec:
                owner, _, repo = spec.partition("/")
                if owner and repo:
                    return owner, repo
    return model.parse_github(meta.get("homepage", ""))

def parse(tar_bytes):
    projects = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if len(parts) < 4 or parts[-3] != "modules" or parts[-1] != "metadata.json":
                continue
            module_name = parts[-2]
            f = tar.extractfile(member)
            if f is None:
                continue
            try:
                meta = json.loads(f.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            repo = _repo_from_metadata(meta)
            if not repo:
                continue
            owner, repo_name = repo
            category, reason = classify.classify_bcr(module_name, owner)
            projects.append(model.Project(
                owner=owner,
                repo_name=repo_name,
                name=module_name,
                category=category,
                classification_reason="BCR: " + reason,
                sources=[SOURCE_ID],
            ))
    return projects

def fetch():
    return parse(netfetch.get_bytes(_TARBALL))
