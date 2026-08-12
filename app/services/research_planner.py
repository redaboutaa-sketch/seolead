"""Targeted authoritative research for unresolved HIGH-risk claims.

The Phase 3 live run surfaced ten relevant Belgian sources and not one regulator
among them: SPECIALIST 5, COMMERCIAL 5, `has_official: false`. Every HIGH-risk
claim was therefore correctly refused — and would stay refused forever, because a
general web search does not surface `energie.wallonie.be` for a pricing query.

Refusing is right. Refusing *and never looking in the right place* is not. This
module turns an unresolved HIGH-risk claim into a second, narrow search restricted
to the domains the vertical names as authoritative.

Everything about it is configuration. `official_source_policy` in the vertical
profile supplies the domains, the query templates and the ceiling; nothing here
knows what a Belgian regulator is.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.enums import ClaimCategory
from app.services.evidence_model import EvaluatedClaim
from app.services.intent import normalize_query
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)

# A hard ceiling regardless of configuration: each query is a paid call, and an
# unresolved-claim list can be long.
_ABSOLUTE_MAX_QUERIES = 5


@dataclass(frozen=True)
class AuthoritativeQuery:
    """One narrow search, restricted to authoritative domains."""

    query: str
    category: ClaimCategory
    domains: list[str]
    reason: str

    def as_dict(self) -> dict:
        return {"query": self.query, "category": self.category.value,
                "domains": self.domains, "reason": self.reason}


@dataclass
class ResearchPlan:
    queries: list[AuthoritativeQuery] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.queries

    def as_dict(self) -> dict:
        return {"queries": [q.as_dict() for q in self.queries],
                "skipped_reason": self.skipped_reason}


def plan_authoritative_research(
    *,
    topic: str,
    market: str,
    unresolved: list[EvaluatedClaim],
    profile: VerticalProfile,
) -> ResearchPlan:
    """Build a bounded set of targeted queries for unresolved HIGH-risk claims.

    One query per claim *category*, not per claim: five unresolved subsidy claims
    are one gap in the evidence set, not five.
    """
    policy = profile.official_source_policy or {}
    plan = ResearchPlan()

    if not policy.get("enabled"):
        plan.skipped_reason = (
            f"vertical {profile.code} does not enable targeted authoritative "
            f"research")
        return plan

    domains = profile.official_domains()
    if not domains:
        plan.skipped_reason = (
            f"vertical {profile.code} enables targeted research but configures "
            f"no authoritative domains")
        return plan

    if not unresolved:
        plan.skipped_reason = "no unresolved HIGH-risk claims"
        return plan

    templates: dict = policy.get("query_templates") or {}
    max_queries = min(int(policy.get("max_queries", 2) or 2), _ABSOLUTE_MAX_QUERIES)

    seen: set[str] = set()
    by_category: dict[ClaimCategory, int] = {}
    for claim in unresolved:
        by_category[claim.requirements.category] = \
            by_category.get(claim.requirements.category, 0) + 1

    # Most-blocked category first: that is where the evidence set is weakest.
    for category, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        if len(plan.queries) >= max_queries:
            break
        template = templates.get(category.value)
        # A category may carry region-specific variants (`SUBSIDY_VLG`), because a
        # single national query can miss a region entirely — Phase 3.2's
        # tri-regional subsidy query returned no Flemish authority, so BE-VLG
        # claims had no official evidence at all.
        for suffix in ("_WAL", "_BRU", "_VLG"):
            variant = templates.get(f"{category.value}{suffix}")
            if not variant or len(plan.queries) >= max_queries:
                continue
            variant_key = normalize_query(variant)
            if variant_key in seen:
                continue
            seen.add(variant_key)
            plan.queries.append(AuthoritativeQuery(
                query=variant.strip(), category=category, domains=domains,
                reason=(f"regional variant for {suffix.lstrip('_')}: a national "
                        f"query does not reach this region's authorities")))
        if not template:
            # No template means the vertical has not said how to look for this
            # category. Guessing a query would spend money on a shape nobody
            # designed, so it is skipped rather than improvised.
            continue
        try:
            query = template.format(topic=topic, market=market,
                                    category=category.value)
        except (KeyError, IndexError):
            logger.warning("malformed query template for %s in vertical %s",
                           category.value, profile.code)
            continue

        key = normalize_query(query)
        if key in seen:
            continue
        seen.add(key)

        plan.queries.append(AuthoritativeQuery(
            query=query.strip(), category=category, domains=domains,
            reason=(f"{count} unresolved {category.value} claim(s) need a source "
                    f"meeting the {profile.code} authority bar"),
        ))

    if plan.is_empty:
        plan.skipped_reason = (
            "unresolved categories have no configured query template")
    return plan
