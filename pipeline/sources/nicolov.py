"""Source: nicolov/awesome-bazel Projects built with Bazel section."""

import re

from .. import model, netfetch

SOURCE_ID = "nicolov"
SOURCE_URL = "https://raw.githubusercontent.com/nicolov/awesome-bazel/master/README.md"

_ITEM_RE = re.compile(r"^\s*[\*\-]\s*\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)(?P<rest>.*)$")

def _clean_desc(rest):
    return rest.strip().lstrip(":- ").strip()

def parse(markdown):
    projects = []
    in_section = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            in_section = line[3:].strip().lower().startswith("projects built with bazel")
            continue
        if not in_section:
            continue
        match = _ITEM_RE.match(line)
        if not match:
            continue
        repo = model.parse_github(match.group("url"))
        if not repo:
            continue
        owner, repo_name = repo
        projects.append(model.Project(
            owner=owner,
            repo_name=repo_name,
            name=match.group("name").strip(),
            description=_clean_desc(match.group("rest")),
            category=model.CATEGORY_PROJECT,
            classification_reason="listed under nicolov 'Projects built with Bazel'",
            sources=[SOURCE_ID],
        ))
    return projects

def fetch():
    return parse(netfetch.get_text(SOURCE_URL))
