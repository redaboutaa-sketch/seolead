"""Source quality — a different axis from relevance.

Relevance asks "is this about the query". Quality asks "how much weight should a
claim from here carry". They are independent: a forum thread can be perfectly
relevant and a poor authority for a tax rate; a government page can be
authoritative and off-topic.

Two rules the mission is explicit about, both encoded here:

* **Ranking is not authority.** Nothing in this module reads a SERP position.
  Google ranks for usefulness and SEO, not for whether a claim is checkable.
* **Commercial is not disqualifying.** An installer's pricing page is often the
  best available source on installer pricing. It is classified as commercial so
  QA can reason about it, not rejected.

Classification is deterministic and domain-based. That is coarse — it cannot tell
a careful trade publication from a careless one — and the coarseness is the point:
a rule an operator can read and correct beats a score they cannot audit.
"""
from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlparse


class SourceQuality(StrEnum):
    OFFICIAL = "OFFICIAL"            # government, regulator, grid operator, EU
    INSTITUTIONAL = "INSTITUTIONAL"  # university, research body, standards org
    SPECIALIST = "SPECIALIST"        # trade press, sector association
    COMMERCIAL = "COMMERCIAL"        # vendor, installer, comparison site
    COMMUNITY = "COMMUNITY"          # forum, social, Q&A
    UNKNOWN = "UNKNOWN"

    @property
    def rank(self) -> int:
        """Ordering for "is this strong enough for a high-risk claim"."""
        return {
            SourceQuality.OFFICIAL: 5,
            SourceQuality.INSTITUTIONAL: 4,
            SourceQuality.SPECIALIST: 3,
            SourceQuality.COMMERCIAL: 2,
            SourceQuality.COMMUNITY: 1,
            SourceQuality.UNKNOWN: 0,
        }[self]


# Suffixes and hosts that identify an official or institutional source. Belgian
# and EU entries matter for the pilot; the table is data and grows per market.
_OFFICIAL_SUFFIXES = (
    ".gov", ".gov.be", ".fgov.be", ".belgium.be", ".europa.eu", ".gouv.fr",
    ".overheid.nl", ".gov.uk",
)
_OFFICIAL_HOSTS = frozenset({
    "energie.wallonie.be", "energiesparen.be", "vlaanderen.be", "wallonie.be",
    "brussels.be", "leefmilieu.brussels", "environnement.brussels",
    "economie.fgov.be", "finances.belgium.be", "financien.belgium.be",
    "cwape.be", "vreg.be", "brugel.brussels", "creg.be",
    "fluvius.be", "ores.be", "resa.be", "sibelga.be", "elia.be",
    "apere.org",
})
_INSTITUTIONAL_SUFFIXES = (".edu", ".ac.uk", ".ac.be", ".uni", ".org.be")
_INSTITUTIONAL_HOSTS = frozenset({
    "kuleuven.be", "ugent.be", "uclouvain.be", "ulb.be", "vito.be", "imec.be",
    "iea.org", "irena.org", "jrc.ec.europa.eu",
})
_COMMUNITY_HOSTS = frozenset({
    "reddit.com", "news.ycombinator.com", "quora.com", "stackexchange.com",
    "stackoverflow.com", "facebook.com", "x.com", "twitter.com", "youtube.com",
    "linkedin.com", "tiktok.com", "forum.be", "medium.com",
})
_SPECIALIST_HINTS = ("energie", "energy", "solar", "zonne", "photovolta",
                     "renouvelable", "hernieuwbare")


def classify_domain(url: str | None, *, source_type: str | None = None) -> SourceQuality:
    """Classify a source from its URL, with the provider's channel as a fallback."""
    if not url:
        # Community providers identify themselves by channel rather than domain.
        if source_type in ("reddit", "hackernews", "youtube", "x", "stocktwits"):
            return SourceQuality.COMMUNITY
        return SourceQuality.UNKNOWN

    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return SourceQuality.UNKNOWN
    if not host:
        return SourceQuality.UNKNOWN

    bare = host[4:] if host.startswith("www.") else host

    if bare in _OFFICIAL_HOSTS or any(bare.endswith(s) for s in _OFFICIAL_SUFFIXES):
        return SourceQuality.OFFICIAL
    if bare in _INSTITUTIONAL_HOSTS or any(
        bare.endswith(s) for s in _INSTITUTIONAL_SUFFIXES
    ):
        return SourceQuality.INSTITUTIONAL
    if any(bare.endswith(c) or bare == c for c in _COMMUNITY_HOSTS):
        return SourceQuality.COMMUNITY
    if source_type in ("reddit", "hackernews", "youtube", "x", "stocktwits"):
        return SourceQuality.COMMUNITY
    if any(hint in bare for hint in _SPECIALIST_HINTS):
        return SourceQuality.SPECIALIST

    # Everything else on the open web for a commercial query is, in practice, a
    # commercial page. Saying UNKNOWN would be more cautious and less useful.
    return SourceQuality.COMMERCIAL


def summarize(qualities: list[SourceQuality]) -> dict:
    counts: dict[str, int] = {}
    for quality in qualities:
        counts[quality.value] = counts.get(quality.value, 0) + 1
    return {
        "counts": counts,
        "has_official": any(q is SourceQuality.OFFICIAL for q in qualities),
        "has_institutional": any(q is SourceQuality.INSTITUTIONAL for q in qualities),
        "best": max(qualities, key=lambda q: q.rank).value if qualities else None,
    }
