"""Authority registry — which domains may establish which kinds of claim.

Phase 3.1 carried a flat list of "authoritative domains". That is enough to say a
source is official, and not enough to say *what it is official about*: the Walloon
energy portal is authoritative on Walloon premiums and says nothing about Flemish
grid rules, and a federal tax page is authoritative on VAT everywhere.

So each domain carries metadata — authority type, region, the claim categories it
speaks for, and a priority — and all of it lives in vertical configuration.
Nothing here knows what a Belgian regulator is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from app.core.enums import ClaimCategory
from app.services.region import Region
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile


class AuthorityType(StrEnum):
    GOVERNMENT = "GOVERNMENT"
    REGULATOR = "REGULATOR"
    GRID_OPERATOR = "GRID_OPERATOR"
    PUBLIC_AGENCY = "PUBLIC_AGENCY"
    OFFICIAL_PROGRAM = "OFFICIAL_PROGRAM"
    UNKNOWN = "UNKNOWN"

    @property
    def source_quality(self) -> SourceQuality:
        """Every recognised authority type maps to OFFICIAL.

        A commercial installer is never in this registry, so it can never acquire
        OFFICIAL through this path — the guarantee the mission asks for.
        """
        return (SourceQuality.OFFICIAL if self is not AuthorityType.UNKNOWN
                else SourceQuality.UNKNOWN)


@dataclass(frozen=True)
class AuthorityEntry:
    domain: str
    authority_type: AuthorityType
    region: Region
    market: str
    languages: tuple[str, ...]
    claim_categories: frozenset[ClaimCategory]
    priority: int = 50
    name: str = ""

    def speaks_for(self, category: ClaimCategory) -> bool:
        """An empty category set means "general authority", not "no authority"."""
        return not self.claim_categories or category in self.claim_categories

    def as_dict(self) -> dict:
        return {
            "domain": self.domain, "name": self.name,
            "authority_type": self.authority_type.value,
            "region": self.region.value, "market": self.market,
            "languages": list(self.languages),
            "claim_categories": sorted(c.value for c in self.claim_categories),
            "priority": self.priority,
        }


@dataclass
class AuthorityRegistry:
    entries: list[AuthorityEntry] = field(default_factory=list)

    @property
    def domains(self) -> list[str]:
        return [e.domain for e in self.entries]

    def lookup(self, url: str | None) -> AuthorityEntry | None:
        """Match a URL to its authority entry by host suffix."""
        if not url:
            return None
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return None
        if not host:
            return None
        bare = host[4:] if host.startswith("www.") else host

        # Longest domain wins, so `energie.wallonie.be` beats a hypothetical
        # `wallonie.be` entry rather than losing to it by ordering accident.
        best: AuthorityEntry | None = None
        for entry in self.entries:
            domain = entry.domain.lower()
            if bare == domain or bare.endswith(f".{domain}"):
                if best is None or len(domain) > len(best.domain):
                    best = entry
        return best

    def for_category(self, category: ClaimCategory, *,
                     region: Region | None = None) -> list[AuthorityEntry]:
        """Domains entitled to speak for a category, most relevant first."""
        candidates = [e for e in self.entries if e.speaks_for(category)]
        if region is not None and region is not Region.UNKNOWN:
            # An entry covering the claim's region, or the claim's region covering
            # the entry (a national query wants regional portals too).
            candidates = [e for e in candidates
                          if e.region.covers(region) or region.covers(e.region)]
        return sorted(candidates, key=lambda e: (-e.priority, e.domain))

    def is_official(self, url: str | None) -> bool:
        return self.lookup(url) is not None


def _as_category_set(values) -> frozenset[ClaimCategory]:
    out: set[ClaimCategory] = set()
    for value in values or []:
        try:
            out.add(ClaimCategory(str(value).upper()))
        except ValueError:
            continue
    return frozenset(out)


def build_registry(profile: VerticalProfile) -> AuthorityRegistry:
    """Build the registry from vertical configuration.

    Accepts both shapes: the Phase 3.1 flat list of domain strings (which become
    UNKNOWN-region general authorities), and the Phase 3.2 richer form with
    metadata. Supporting both means a vertical that has not been migrated still
    works rather than silently losing its authorities.
    """
    policy = profile.official_source_policy or {}
    registry = AuthorityRegistry()
    seen: set[str] = set()

    for raw in policy.get("domains") or []:
        if isinstance(raw, str):
            domain = raw.strip().lower()
            if not domain or domain in seen:
                continue
            seen.add(domain)
            registry.entries.append(AuthorityEntry(
                domain=domain, authority_type=AuthorityType.PUBLIC_AGENCY,
                region=Region.UNKNOWN, market=profile.market,
                languages=tuple(profile.languages),
                claim_categories=frozenset(), priority=50,
                name=domain))
            continue

        if not isinstance(raw, dict):
            continue
        domain = str(raw.get("domain", "")).strip().lower()
        if not domain or domain in seen:
            continue
        seen.add(domain)

        try:
            authority_type = AuthorityType(str(raw.get("authority_type", "")).upper())
        except ValueError:
            authority_type = AuthorityType.PUBLIC_AGENCY
        try:
            region = Region(str(raw.get("region", "")).upper())
        except ValueError:
            region = Region.UNKNOWN

        registry.entries.append(AuthorityEntry(
            domain=domain,
            authority_type=authority_type,
            region=region,
            market=str(raw.get("market") or profile.market).upper(),
            languages=tuple(raw.get("languages") or profile.languages),
            claim_categories=_as_category_set(raw.get("claim_categories")),
            priority=int(raw.get("priority", 50) or 50),
            name=str(raw.get("name") or domain),
        ))

    # Legacy `authoritative_domains` remains honoured as a general authority.
    for domain in profile.authoritative_domains or []:
        normalized = domain.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        registry.entries.append(AuthorityEntry(
            domain=normalized, authority_type=AuthorityType.PUBLIC_AGENCY,
            region=Region.UNKNOWN, market=profile.market,
            languages=tuple(profile.languages), claim_categories=frozenset(),
            priority=40, name=normalized))

    return registry
