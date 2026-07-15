"""Normalized project model for the discovery pipeline."""

import math
import re
from dataclasses import dataclass, field

CATEGORY_PROJECT = "project"
CATEGORY_RULESET = "ruleset"
CATEGORY_TOOLING = "tooling"
CATEGORY_UNKNOWN = "unknown"

_CATEGORY_PRIORITY = {
    CATEGORY_PROJECT: 3,
    CATEGORY_UNKNOWN: 2,
    CATEGORY_RULESET: 1,
    CATEGORY_TOOLING: 0,
}

_GITHUB_RE = re.compile(
    r"github\.com[:/]+(?P<owner>[^/\s]+)/(?P<repo>[^/\s#?)]+)",
    re.IGNORECASE,
)
_NON_REPO_OWNERS = {"about", "features", "orgs", "settings", "sponsors", "topics"}

BAZEL_MARKERS = ("MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel", "BUILD", "BUILD.bazel")
FRESH_MONTHS = 18
STALE_MONTHS = 60

def parse_github(url):
    match = _GITHUB_RE.search(url or "")
    if not match:
        return None
    owner = match.group("owner")
    repo = match.group("repo").removesuffix(".git").rstrip("/")
    if owner.lower() in _NON_REPO_OWNERS or not owner or not repo:
        return None
    return owner, repo

@dataclass
class Project:
    owner: str
    repo_name: str
    name: str = ""
    description: str = ""
    category: str = CATEGORY_UNKNOWN
    classification_reason: str = ""
    sources: list = field(default_factory=list)
    enriched: bool = False
    stars: int = 0
    archived: bool = False
    language: str = ""
    pushed_at: str = ""
    first_party_bazel: object = None
    bazel_markers: list = field(default_factory=list)

    @property
    def key(self):
        return "{}/{}".format(self.owner.lower(), self.repo_name.lower())

    @property
    def repo_url(self):
        return "https://github.com/{}/{}".format(self.owner, self.repo_name)

    @property
    def in_bcr(self):
        return "bcr" in self.sources

    def merge(self, other):
        for source in other.sources:
            if source not in self.sources:
                self.sources.append(source)
        if not self.name:
            self.name = other.name
        if not self.description:
            self.description = other.description
        if _CATEGORY_PRIORITY[other.category] > _CATEGORY_PRIORITY[self.category]:
            self.category = other.category
            self.classification_reason = other.classification_reason
        if other.enriched:
            self.enriched = True
            self.stars = other.stars
            self.archived = other.archived
            self.language = other.language
            self.pushed_at = other.pushed_at
            if other.description and not self.description:
                self.description = other.description
        if self.first_party_bazel is None and other.first_party_bazel is not None:
            self.first_party_bazel = other.first_party_bazel
            self.bazel_markers = list(other.bazel_markers)

    def to_dict(self, reference_pushed_at=""):
        return {
            "repo": self.repo_url,
            "name": self.name or self.repo_name,
            "category": self.category,
            "description": self.description,
            "sources": sorted(self.sources),
            "classification_reason": self.classification_reason,
            "stars": self.stars,
            "archived": self.archived,
            "language": self.language,
            "pushed_at": self.pushed_at,
            "in_bcr": self.in_bcr,
            "first_party_bazel": self.first_party_bazel,
            "bazel_markers": sorted(self.bazel_markers),
            "candidate_score": candidate_score(self, reference_pushed_at),
            "enriched": self.enriched,
        }

def _month_ordinal(iso):
    if not iso or len(iso) < 7:
        return None
    try:
        return int(iso[:4]) * 12 + int(iso[5:7])
    except ValueError:
        return None

def _freshness(pushed_at, reference):
    pushed = _month_ordinal(pushed_at)
    ref = _month_ordinal(reference)
    if pushed is None or ref is None:
        return 0.0
    stale = max(0, ref - pushed)
    if stale <= FRESH_MONTHS:
        return 1.0
    if stale >= STALE_MONTHS:
        return 0.0
    return 1.0 - (stale - FRESH_MONTHS) / (STALE_MONTHS - FRESH_MONTHS)

def candidate_score(project, reference_pushed_at=""):
    if project.category != CATEGORY_PROJECT or project.archived:
        return 0.0
    recognition = math.log10((project.stars or 0) + 1)
    buildable = 1.0
    if project.in_bcr:
        buildable += 1.0
    if project.first_party_bazel:
        buildable += 0.5
    return round(recognition * _freshness(project.pushed_at, reference_pushed_at) * buildable, 3)
