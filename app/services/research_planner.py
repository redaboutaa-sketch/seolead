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


# The categories that answer a price question. A price gap widens what the
# planner looks for; the tuple lives here so the gate and the pipeline agree.
PRICE_ANSWER_CATEGORIES = ("OBSERVED_PRICE_RANGE", "MARKET_AVERAGE",
                           "MARKET_PRICE", "VENDOR_PRICE")


def as_evaluated(claims: list[dict], profile: VerticalProfile, *,
                 price_gap: bool = False) -> list:
    """Rehydrate the package claims the planner should find better sources for.

    The planner reasons over `EvaluatedClaim` and the package carries dicts. It
    lives beside the planner (2026-09-03) because the publication gate now asks
    the same question the pipeline asks — « what did this package leave
    unresolved? » — and two copies of the answer would drift.
    """
    from app.core.enums import EvidenceStatus
    from app.services.claim_extraction import AtomicClaim
    from app.services.claim_policy import requirements_for
    from app.services.evidence_model import EvaluatedClaim

    out = []
    for claim in claims or []:
        wanted = (claim.get("claim_risk") == "HIGH"
                  or (price_gap
                      and claim.get("category") in PRICE_ANSWER_CATEGORIES))
        if not wanted:
            continue
        if claim.get("evidence_status") == EvidenceStatus.SUPPORTED.value:
            continue
        atomic = AtomicClaim(text=claim["claim"], passage=claim.get("passage", ""),
                             source_ref=claim.get("source_ref", ""), offset=0)
        evaluated = EvaluatedClaim(claim=atomic,
                                   requirements=requirements_for(claim["claim"],
                                                                 profile))
        evaluated.status = EvidenceStatus(claim["evidence_status"])
        out.append(evaluated)
    return out


# ── Resolution of a plan (2026-09-03) ───────────────────────────────────────
RESOLUTION_EXECUTED = "EXECUTED"
RESOLUTION_ABANDONED = "ABANDONED"


def record_resolution(package, plan: ResearchPlan, run: dict, *,
                      by: str) -> dict:
    """Append, for every query the run executed, an EXECUTED entry carrying
    what came back — accepted sources by name, tier, region and date, no
    URL — to `package.authoritative_research`. Returns the record."""
    from datetime import datetime, timezone

    record = dict(package.authoritative_research or {})
    resolution = list(record.get("resolution") or [])
    executed = {str(q.get("query")): q for q in run.get("queries_executed") or []}
    accepted_by_query: dict[str, list[dict]] = {}
    for source in run.get("accepted") or []:
        accepted_by_query.setdefault(str(source.get("query")), []).append({
            "name": source.get("name") or source.get("domain"),
            "tier": "OFFICIAL", "authority_type": source.get("authority_type"),
            "region": source.get("region"),
            "date": (str(source.get("effective_from")
                         or source.get("published_at") or "")[:10] or None),
            "freshness": source.get("status") or source.get("freshness_status"),
        })
    now = datetime.now(timezone.utc).isoformat()
    for planned in plan.queries:
        if planned.query not in executed:
            continue
        summary = executed[planned.query]
        resolution.append({
            "query": planned.query, "category": planned.category.value,
            "status": RESOLUTION_EXECUTED, "at": now, "by": by,
            "returned": summary.get("returned", 0),
            "accepted": summary.get("accepted", 0),
            "error": summary.get("error"),
            "sources": accepted_by_query.get(planned.query, []),
        })
    record["resolution"] = resolution
    record["plan"] = plan.as_dict()
    package.authoritative_research = record
    return record


def abandon_query(package, query: str, *, reason: str, by: str) -> dict:
    """Record that a proposed query will not be launched. The reason is
    mandatory and stored verbatim."""
    from datetime import datetime, timezone

    if not reason.strip():
        raise ValueError("an abandoned search needs a written reason")
    record = dict(package.authoritative_research or {})
    resolution = list(record.get("resolution") or [])
    resolution.append({
        "query": query, "status": RESOLUTION_ABANDONED,
        "reason": reason.strip(), "by": by,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    record["resolution"] = resolution
    package.authoritative_research = record
    return record


def unresolved_queries(plan: ResearchPlan, record: dict | None) -> list[dict]:
    """Planned queries that were neither executed nor abandoned with a reason.

    A query counts as resolved by its text: launched once is launched, even if
    the planner proposes it again because the gap it targeted survived.
    """
    resolved = {str(r.get("query")) for r in (record or {}).get("resolution", [])
                if r.get("status") in (RESOLUTION_EXECUTED, RESOLUTION_ABANDONED)
                and (r.get("status") != RESOLUTION_ABANDONED
                     or str(r.get("reason") or "").strip())}
    return [q.as_dict() for q in plan.queries if q.query not in resolved]
