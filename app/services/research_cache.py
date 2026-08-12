"""Research freshness policy.

Different research goes stale at different rates, so one TTL for everything would
be wrong in both directions — paying for a SERP that has not moved, or reusing a
week-old SERP as if it were today's.

| Research | Default TTL | Why |
|---|---|---|
| SERP | 24 h | Result pages move daily; a stale SERP misreads the competition |
| Web research | 168 h (7 d) | Explanatory pages change slowly |
| Community | 72 h | Discussion has a short half-life, and the window is already bounded |

A forced refresh always overrides. The cache is an economy, not a constraint.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from app.core.config import Settings


class ResearchKind(StrEnum):
    SERP = "SERP"
    WEB_RESEARCH = "WEB_RESEARCH"
    COMMUNITY = "COMMUNITY"
    KEYWORD_METRICS = "KEYWORD_METRICS"


def ttl_hours(kind: ResearchKind, settings: Settings) -> int:
    return {
        ResearchKind.SERP: settings.serp_ttl_hours,
        ResearchKind.WEB_RESEARCH: settings.web_research_ttl_hours,
        ResearchKind.COMMUNITY: settings.community_ttl_hours,
        # Volume figures are monthly averages; refreshing them daily buys nothing.
        ResearchKind.KEYWORD_METRICS: max(settings.web_research_ttl_hours, 168),
    }[kind]


def serp_cache_key(*, query: str, location_code: int, language_code: str,
                   device: str) -> str:
    """Identifies an equivalent search.

    Device is part of the key because mobile and desktop are different result
    pages, not variants of one — treating them as interchangeable would serve a
    desktop SERP as evidence about what a phone user sees.
    """
    from app.services.intent import normalize_query

    raw = f"{normalize_query(query)}|{location_code}|{language_code.lower()}|{device}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def is_fresh(retrieved_at: datetime | None, kind: ResearchKind,
             settings: Settings, *, now: datetime | None = None) -> bool:
    if retrieved_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    return (now - retrieved_at) < timedelta(hours=ttl_hours(kind, settings))


def freshness_policy(settings: Settings) -> dict:
    """The active policy, for the report and the operator."""
    return {
        kind.value: {
            "ttl_hours": ttl_hours(kind, settings),
            "forced_refresh_supported": True,
        }
        for kind in ResearchKind
    }
