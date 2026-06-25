"""Core data model: the normalized representation of a discovered project."""

import math
import re
from dataclasses import dataclass, field, asdict

# Category of an entry. Awesome-list "projects" sections yield PROJECT; BCR
# entries are classified heuristically (see classify.py).
CATEGORY_PROJECT = "project"
CATEGORY_RULESET = "ruleset"
CATEGORY_TOOLING = "tooling"
CATEGORY_UNKNOWN = "unknown"

# When the same repo shows up under different categories across sources, the
# more specific / more "buildable project" category wins.
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

# Owners/paths on github.com that are never real repositories.
_NON_REPO_OWNERS = {"sponsors", "about", "features", "topics", "orgs", "settings"}


def parse_github(url):
    """Return (owner, repo) for a github.com URL, or None if not parseable."""
    m = _GITHUB_RE.search(url or "")
    if not m:
        return None
    owner = m.group("owner")
    repo = m.group("repo")
    if owner.lower() in _NON_REPO_OWNERS:
        return None
    repo = repo.removesuffix(".git").rstrip("/")
    if not owner or not repo:
        return None
    return owner, repo


@dataclass
class Project:
    """A single discovered project, normalized across sources."""

    owner: str
    repo_name: str
    name: str = ""
    description: str = ""
    category: str = CATEGORY_UNKNOWN
    classification_reason: str = ""
    sources: list = field(default_factory=list)

    # Enrichment from the GitHub API (filled in optionally via gh).
    enriched: bool = False
    stars: int = 0
    archived: bool = False
    language: str = ""
    pushed_at: str = ""

    # Buildability signals.
    #   first_party_bazel: does the repo itself ship Bazel build files (i.e. is
    #     it a Bazel project, vs. a BCR-maintained *port* of a CMake/autotools
    #     project)? None = not checked (see gather --detect-bazel).
    #   bazel_markers: which marker files were found at the repo root.
    first_party_bazel: object = None  # None | True | False
    bazel_markers: list = field(default_factory=list)

    @property
    def key(self):
        """Dedup key: case-insensitive owner/repo."""
        return f"{self.owner.lower()}/{self.repo_name.lower()}"

    @property
    def in_bcr(self):
        """True if the project has a module in the Bazel Central Registry.

        The single strongest buildability signal we collect: a BCR entry means
        someone keeps a working Bazel build of this project green.
        """
        return "bcr" in self.sources

    @property
    def repo_url(self):
        return f"https://github.com/{self.owner}/{self.repo_name}"

    def merge(self, other):
        """Fold another record for the same repo into this one."""
        for s in other.sources:
            if s not in self.sources:
                self.sources.append(s)
        if not self.name:
            self.name = other.name
        if not self.description:
            self.description = other.description
        if _CATEGORY_PRIORITY[other.category] > _CATEGORY_PRIORITY[self.category]:
            self.category = other.category
            self.classification_reason = other.classification_reason
        if self.first_party_bazel is None and other.first_party_bazel is not None:
            self.first_party_bazel = other.first_party_bazel
            self.bazel_markers = other.bazel_markers

    def to_dict(self, reference_pushed_at=""):
        d = asdict(self)
        d.pop("owner")
        d.pop("repo_name")
        # Present a stable, readable ordering.
        return {
            "name": self.name or self.repo_name,
            "repo": self.repo_url,
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


# --- Candidate ranking -----------------------------------------------------
#
# "Which well-known, mature project should we add next?" is a function of three
# things we already collect:
#
#   recognition — how well-known (stars, log-scaled so 100k isn't 1000x a 100)
#   alive       — recently pushed and not archived (mature *and* maintained)
#   buildable   — does a Bazel build demonstrably exist? (BCR membership is the
#                 strong signal; a first-party Bazel repo is a further boost)
#
# score = recognition * alive * buildable. Deterministic given the snapshot: the
# freshness "now" is the most recent pushed_at across the dataset, not wall-clock
# time, so re-ranking the same snapshot yields the same numbers.

# Bazel build-file names that mark a repo as a first-party Bazel project.
BAZEL_MARKERS = ("MODULE.bazel", "WORKSPACE", "WORKSPACE.bazel", "BUILD", "BUILD.bazel")

# Freshness window (months): pushed within FRESH_MONTHS scores 1.0, decaying
# linearly to 0.0 at STALE_MONTHS.
FRESH_MONTHS = 18
STALE_MONTHS = 60


def _month_ordinal(iso):
    """Year*12+month from an ISO date like '2026-06-24T...', or None."""
    if not iso or len(iso) < 7:
        return None
    try:
        return int(iso[0:4]) * 12 + int(iso[5:7])
    except ValueError:
        return None


def _freshness(pushed_at, reference):
    pm = _month_ordinal(pushed_at)
    rm = _month_ordinal(reference)
    if pm is None or rm is None:
        return 0.0
    stale = max(0, rm - pm)
    if stale <= FRESH_MONTHS:
        return 1.0
    if stale >= STALE_MONTHS:
        return 0.0
    return 1.0 - (stale - FRESH_MONTHS) / (STALE_MONTHS - FRESH_MONTHS)


def candidate_score(proj, reference_pushed_at=""):
    """A 0..~10 score ranking a project as a museum candidate (higher = better).

    Only PROJECT-category, non-archived entries score above zero. reference_
    pushed_at calibrates freshness (pass the max pushed_at across the snapshot
    for a stable, self-relative "now").
    """
    if proj.category != CATEGORY_PROJECT or proj.archived:
        return 0.0
    recognition = math.log10((proj.stars or 0) + 1)
    fresh = _freshness(proj.pushed_at, reference_pushed_at)
    buildable = 1.0
    if proj.in_bcr:
        buildable += 1.0
    if proj.first_party_bazel:
        buildable += 0.5
    return round(recognition * fresh * buildable, 3)
