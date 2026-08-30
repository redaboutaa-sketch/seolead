"""Executor for the authoritative research plan.

Phase 3.1 generated a plan and never ran it. That left every HIGH-risk claim
permanently unresolvable: a general web search does not surface a regulator for a
pricing query, so the evidence set could never contain the only kind of source
entitled to establish a subsidy or a grid rule.

This module runs the plan. Three properties make it safe to point at a paid API:

* **Domain enforcement is applied twice.** The provider is asked to restrict
  results, and every returned URL is then checked against the registry. A provider
  that ignores or partially honours the restriction cannot smuggle a commercial
  page into the authoritative pass.
* **Bounded.** One query per unresolved category, capped by the vertical's
  `max_queries` and the existing per-job provider ceiling.
* **Nothing is relabelled.** A page is OFFICIAL because its domain is in the
  configured registry, never because it was returned by an authoritative query.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.enums import ClaimCategory, ObservationStatus, SourceState
from app.core.errors import ResearchProviderError
from app.schemas.research import NormalizedSource, ResearchProviderResult, SourceOutcome
from app.services.authority_registry import AuthorityEntry, AuthorityRegistry
from app.services.freshness import assess as assess_freshness
from app.services.provider_usage import UsageRecorder
from app.services.relevance import RESEARCH_QUERY_KEY
from app.services.region import Region, detect_region
from app.services.research_planner import AuthoritativeQuery, ResearchPlan
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)


@dataclass
class AuthoritativeSource:
    """One official page, with its authority and freshness metadata."""

    source: NormalizedSource
    entry: AuthorityEntry
    region: Region
    freshness: dict
    query: str
    category: ClaimCategory

    def as_dict(self) -> dict:
        return {
            "url": self.source.url, "title": self.source.title,
            "domain": self.entry.domain, "name": self.entry.name,
            "authority_type": self.entry.authority_type.value,
            "region": self.region.value,
            "authority_region": self.entry.region.value,
            "query": self.query, "category": self.category.value,
            **self.freshness,
        }


@dataclass
class AuthoritativeRunResult:
    queries_executed: list[dict] = field(default_factory=list)
    accepted: list[AuthoritativeSource] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    domains_queried: list[str] = field(default_factory=list)

    @property
    def sources_returned(self) -> int:
        return sum(q.get("returned", 0) for q in self.queries_executed)

    def as_dict(self) -> dict:
        return {
            "queries_executed": self.queries_executed,
            "domains_queried": self.domains_queried,
            "sources_returned": self.sources_returned,
            "sources_accepted": len(self.accepted),
            "sources_rejected": len(self.rejected),
            "accepted": [s.as_dict() for s in self.accepted],
            "rejected": self.rejected,
            "errors": self.errors,
        }

    def to_provider_result(self, *, query: str, market: str,
                           language: str) -> ResearchProviderResult:
        """Fold accepted official pages into the standard provider shape.

        Returning the normal type means the rest of the pipeline — passages, atomic
        claims, evidence mapping — treats official evidence with exactly the same
        machinery as any other. There is no separate, less-tested path for the
        sources that matter most.
        """
        # Each page carries the question it was fetched to answer. Without this
        # the relevance gate downstream can only compare it to the article's own
        # query — a question these pages were never asked — and every one of them
        # is discarded for having no topical overlap with it.
        sources = [
            s.source.model_copy(update={"metadata": {
                **s.source.metadata,
                RESEARCH_QUERY_KEY: s.query,
                "research_category": s.category.value,
            }})
            for s in self.accepted
        ]
        state = SourceState.OK if sources else SourceState.NO_RESULTS
        unresolved: list[str] = []
        if not sources:
            unresolved.append(
                "Targeted authoritative research returned no page on a configured "
                "official domain; HIGH-risk claims remain unresolved.")
        return ResearchProviderResult(
            provider="tavily_authoritative", query=query, market=market,
            language=language, status="SUCCEEDED" if sources else "PARTIAL",
            sources=sources, facts=[],
            source_outcomes=[SourceOutcome(source_type="official",
                                           state=state, item_count=len(sources))],
            unresolved_data=unresolved,
            provider_metadata={"authoritative": {
                "queries": [q["query"] for q in self.queries_executed],
                "domains": self.domains_queried,
                "accepted": len(self.accepted), "rejected": len(self.rejected),
            }},
        )


async def execute_plan(
    plan: ResearchPlan,
    *,
    profile: VerticalProfile,
    registry: AuthorityRegistry,
    web_provider,
    market: str,
    language: str,
    correlation_id: str,
    usage: UsageRecorder | None = None,
) -> AuthoritativeRunResult:
    """Run each planned query against official domains only."""
    result = AuthoritativeRunResult()
    if plan.is_empty:
        return result

    usage = usage or UsageRecorder()

    for planned in plan.queries:
        entries = registry.for_category(planned.category)
        domains = [e.domain for e in entries] or registry.domains
        if not domains:
            result.errors.append({"query": planned.query,
                                  "error": "no configured official domain"})
            continue

        for domain in domains:
            if domain not in result.domains_queried:
                result.domains_queried.append(domain)

        try:
            usage.check_and_consume(getattr(web_provider, "code", "tavily"))
            provider_result = await _search(web_provider, planned, domains,
                                            market=market, language=language,
                                            correlation_id=correlation_id)
        except ResearchProviderError as exc:
            result.errors.append({"query": planned.query, "error": exc.code,
                                  "detail": exc.detail})
            result.queries_executed.append({
                "query": planned.query, "category": planned.category.value,
                "domains": len(domains), "returned": 0, "accepted": 0,
                "error": exc.code})
            continue

        accepted_here = 0
        for source in provider_result.sources:
            entry = registry.lookup(source.url)
            if entry is None:
                # Second enforcement. A provider that ignored the restriction, or
                # honoured it loosely, cannot get a commercial page relabelled.
                result.rejected.append({
                    "url": source.url, "title": source.title,
                    "query": planned.query,
                    "reason": "not on a configured official domain"})
                continue
            if not entry.speaks_for(planned.category):
                result.rejected.append({
                    "url": source.url, "title": source.title,
                    "query": planned.query,
                    "reason": (f"{entry.domain} is not configured as an authority "
                               f"for {planned.category.value}")})
                continue

            body = f"{source.title or ''}\n{source.summary or ''}"
            freshness = assess_freshness(body, published_at=source.published_at,
                                         retrieved_at=source.retrieved_at)
            # The authority's own jurisdiction wins. `energie.wallonie.be` is the
            # Walloon energy portal whatever a page happens to mention, and the
            # live run showed text detection tagging it BE-BRU because one page
            # referenced Brussels — which would let a Walloon source establish a
            # Brussels rule. Page text is only consulted when the authority has
            # no declared region.
            region = entry.region
            if region is Region.UNKNOWN:
                region = detect_region(body).region

            result.accepted.append(AuthoritativeSource(
                source=source, entry=entry, region=region,
                freshness=freshness.as_dict(), query=planned.query,
                category=planned.category))
            accepted_here += 1

        result.queries_executed.append({
            "query": planned.query, "category": planned.category.value,
            "domains": len(domains), "returned": len(provider_result.sources),
            "accepted": accepted_here,
            "duration_ms": provider_result.duration_ms})

        logger.info("authoritative query complete", extra={
            "correlation_id": correlation_id, "provider": "tavily_authoritative",
            "status": f"{planned.category.value} accepted={accepted_here}"})

    return result


async def _search(web_provider, planned: AuthoritativeQuery, domains: list[str],
                  *, market: str, language: str,
                  correlation_id: str) -> ResearchProviderResult:
    """Call the web provider with a domain restriction where it supports one."""
    if hasattr(web_provider, "research_restricted"):
        return await web_provider.research_restricted(
            query=planned.query, market=market, language=language,
            correlation_id=correlation_id, include_domains=domains)
    # A provider with no restriction support still works: the registry check
    # above discards everything off-domain. It costs a wasted call, not accuracy.
    return await web_provider.research(
        query=planned.query, market=market, language=language,
        correlation_id=correlation_id)
