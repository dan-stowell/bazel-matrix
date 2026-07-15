"""Source: jin/awesome-bazel Projects section."""

import re

from .. import model, netfetch

SOURCE_ID = "jin"
SOURCE_URL = "https://raw.githubusercontent.com/jin/awesome-bazel/master/README.md"

_ITEM_RE = re.compile(r"^\s*[\*\-]\s+\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)(?P<rest>.*)$")

def _clean_desc(rest):
    return rest.strip().lstrip(":- ").strip()

def parse(markdown):
    projects = []
    in_section = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            in_section = stripped[4:].strip().lower() == "projects"
            continue
        if stripped.startswith("## "):
            in_section = False
            continue
        if not in_section or line[:len(line) - len(line.lstrip())]:
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
            classification_reason="listed under jin 'Projects'",
            sources=[SOURCE_ID],
        ))
    return projects

def fetch():
    return parse(netfetch.get_text(SOURCE_URL))
