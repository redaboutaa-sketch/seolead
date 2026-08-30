"""Probe an authority domain set, and report where its dates actually live.

Two questions this answers, both of which were being settled by recollection
rather than measurement.

**Ratification.** The registry is a trust gate: an entry lets a domain establish
HIGH-risk claims. Adding one on the strength of "this is the federal planning
bureau, it surely publishes energy economics" is exactly the reasoning the rest
of this pipeline exists to refuse. The probe runs the category's real query
against candidate domains and shows what comes back — titles, URLs, and whether
the page carries anything a freshness check could use.

**Dates.** The live run of 2026-08-30 returned 28 eligible official pages and
`sources_dated: 0`. Every one had `published_at: null`. Before choosing a
mechanism to fix that, we have to know where the dates are: in the provider's
metadata, in an HTTP header, in visible text, or nowhere. The probe reports each
candidate location separately rather than collapsing them into one verdict, so
the answer is read off the data instead of assumed.

Read-only. Nothing is persisted, no package is touched, and the registry is not
modified — a probe that changed what it measured would measure nothing.
"""
from __future__ import annotations

import re

from app.core.enums import ClaimCategory
from app.services.authority_registry import AuthorityRegistry, build_registry
from app.services.freshness import assess as assess_freshness
from app.verticals.profile import VerticalProfile

# Date shapes a European official page actually uses, in the order a reader
# would trust them. Deliberately NOT parsed into datetimes: the point is to
# report what the page shows, and turning "31 december 2029" into a timestamp
# here would hide the very ambiguity we are measuring.
_DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iso", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("numeric", re.compile(r"\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b")),
    ("fr_long", re.compile(
        r"\b\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|"
        r"septembre|octobre|novembre|décembre)\s+\d{4}\b", re.IGNORECASE)),
    ("nl_long", re.compile(
        r"\b\d{1,2}\s+(?:januari|februari|maart|april|mei|juni|juli|augustus|"
        r"september|oktober|november|december)\s+\d{4}\b", re.IGNORECASE)),
    ("bare_year", re.compile(r"\b(?:19|20)\d{2}\b")),
)


def date_forensics(source) -> dict:
    """Where, if anywhere, this source carries a date.

    Each location is reported on its own. Collapsing them would lose the finding
    the measurement exists to produce: which of them is ever populated.
    """
    text = f"{source.title or ''}\n{source.summary or ''}"
    found: dict[str, list[str]] = {}
    for label, pattern in _DATE_PATTERNS:
        hits = pattern.findall(text)
        if hits:
            # Order-preserving dedupe; the first occurrences are what a reader
            # meets first, and there is no value in a hundred repetitions.
            seen: list[str] = []
            for hit in hits:
                if hit not in seen:
                    seen.append(hit)
            found[label] = seen[:5]

    freshness = assess_freshness(text, published_at=source.published_at,
                                 retrieved_at=source.retrieved_at)
    return {
        # The provider's own field. Null on every official page of the live run.
        "provider_published_at": (source.published_at.isoformat()
                                  if source.published_at else None),
        "provider_metadata_keys": sorted(source.metadata or {}),
        "dates_in_text": found,
        "any_date_in_text": bool(found),
        **freshness.as_dict(),
    }


def registry_for_probe(profile: VerticalProfile, *,
                       include_pending: bool) -> AuthorityRegistry:
    return build_registry(profile, include_pending=include_pending)


def domains_for(registry: AuthorityRegistry, category: ClaimCategory,
                *, explicit: list[str] | None = None) -> list[str]:
    if explicit:
        return [d.strip().lower() for d in explicit if d and d.strip()]
    entries = registry.for_category(category)
    return [e.domain for e in entries] or registry.domains


def summarize(rows: list[dict]) -> dict:
    """The counts that decide both questions."""
    total = len(rows)
    return {
        "sources": total,
        "with_provider_date": sum(1 for r in rows
                                  if r["dates"]["provider_published_at"]),
        "with_date_in_text": sum(1 for r in rows if r["dates"]["any_date_in_text"]),
        "by_text_date_kind": {
            label: sum(1 for r in rows if label in r["dates"]["dates_in_text"])
            for label, _ in _DATE_PATTERNS
        },
        "by_freshness_status": {
            status: sum(1 for r in rows
                        if r["dates"].get("freshness_status") == status)
            for status in sorted({r["dates"].get("freshness_status")
                                  for r in rows} - {None})
        },
        "by_domain": {
            domain: sum(1 for r in rows if r["domain"] == domain)
            for domain in sorted({r["domain"] for r in rows})
        },
    }
