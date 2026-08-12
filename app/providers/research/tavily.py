"""TavilyResearchProvider — source-backed web research.

Contract verified against https://docs.tavily.com during implementation:

    POST https://api.tavily.com/search
    Authorization: Bearer tvly-...
    body:  {query, search_depth, topic, max_results, include_answer,
            include_raw_content, country, time_range, ...}
    response: {query, answer?, results[{title, url, content, score, raw_content?,
               favicon?, id}], response_time, request_id, usage?}

Two contract facts drive the mapping and both matter:

**`published_date` is not a standard field.** It appears for `topic="news"`. So a
general search returns sources with no date, and this adapter leaves
`published_at` as `None` rather than inventing one. Downstream, an undated source
becomes ESTIMATED rather than OBSERVED — we saw it, we cannot place it in time.

**`score` is relevance, not confidence.** Tavily's score says "this matched your
query well". It says nothing about whether the content is true. It is carried in
`metadata` and used by the relevance gate; it never becomes a factual confidence.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from app.core.config import Settings
from app.core.enums import Observability, SourceState
from app.core.errors import (ProviderNotConfigured, ResearchContractError,
                             ResearchProviderError, ResearchTimeout,
                             ResearchUnavailable)
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.services.provider_usage import UsageRecorder

logger = logging.getLogger(__name__)

SEARCH_PATH = "/search"

# Tavily accepts a two-letter country to boost local results. Its `country`
# parameter expects a country NAME in the documented examples; the mapping is kept
# here so the provider takes a market code like the rest of the system.
_COUNTRY_BY_MARKET = {
    "BE": "belgium", "FR": "france", "NL": "netherlands", "DE": "germany",
}


class TavilyResearchProvider:
    code = "tavily"

    def __init__(self, settings: Settings, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 usage: UsageRecorder | None = None):
        self._api_key = settings.tavily_api_key.strip()
        self._base_url = settings.tavily_base_url.rstrip("/")
        self._timeout = settings.tavily_timeout_seconds
        self._max_results = settings.tavily_max_results
        self._search_depth = settings.tavily_search_depth
        self._transport = transport
        self._usage = usage or UsageRecorder()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def health(self) -> dict:
        return {"configured": self.configured, "provider": self.code,
                "reachable": None}

    async def research_restricted(
        self, *, query: str, market: str, language: str, correlation_id: str,
        include_domains: list[str],
    ) -> ResearchProviderResult:
        """Search restricted to a domain allow-list.

        Tavily's contract documents `include_domains` (max 300). Used for the
        authoritative pass, where mixing commercial results into the same call
        would defeat the point. The caller re-checks every returned URL against
        the authority registry regardless — a provider that honours the
        restriction loosely must not be able to smuggle a page through.
        """
        return await self.research(
            query=query, market=market, language=language,
            correlation_id=correlation_id,
            include_domains=[d for d in include_domains if d][:300])

    async def research(
        self, *, query: str, market: str, language: str, correlation_id: str,
        idempotency_key: str | None = None,
        include_domains: list[str] | None = None,
    ) -> ResearchProviderResult:
        if not self.configured:
            raise ProviderNotConfigured("Tavily API key is not configured")

        body: dict[str, Any] = {
            "query": query,
            "search_depth": self._search_depth,
            "topic": "general",
            "max_results": max(1, min(self._max_results, 20)),
            "include_answer": False,       # we want sources, not a synthesised answer
            "include_raw_content": False,  # excerpts are enough and far cheaper
        }
        country = _COUNTRY_BY_MARKET.get(market.upper())
        if country:
            body["country"] = country
        if include_domains:
            body["include_domains"] = include_domains

        started_at = datetime.now(timezone.utc)
        monotonic = time.monotonic()
        logger.info("tavily search request", extra={
            "correlation_id": correlation_id, "provider": self.code})

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout,
                transport=self._transport,
                headers={"Authorization": f"Bearer {self._api_key}",
                         "Content-Type": "application/json"},
            ) as client:
                response = await client.post(SEARCH_PATH, json=body)
        except httpx.TimeoutException as exc:
            raise ResearchTimeout(type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise ResearchUnavailable(type(exc).__name__) from exc

        duration_ms = int((time.monotonic() - monotonic) * 1000)

        if response.status_code in (401, 403):
            raise ResearchProviderError("Tavily rejected the API key",
                                        retryable=False)
        if response.status_code == 429:
            raise ResearchUnavailable("Tavily rate limit (429)")
        if response.status_code >= 400:
            raise ResearchProviderError(f"Tavily returned {response.status_code}",
                                        retryable=False)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchContractError("Tavily response is not JSON") from exc

        result = normalize_tavily(payload, query=query, market=market,
                                  language=language)
        result.started_at = started_at
        result.completed_at = datetime.now(timezone.utc)
        result.duration_ms = duration_ms

        # Tavily bills in credits, not money, and does not return a monetary cost.
        # Recording `cost_usd=None` keeps "unknown" distinct from "free".
        self._usage.record(
            provider=self.code,
            operation="search_restricted" if include_domains else "search",
            correlation_id=correlation_id, requests=1,
            units=len(result.sources), cost_usd=None, cost_is_actual=False,
            duration_ms=duration_ms,
        )

        logger.info("tavily search complete", extra={
            "correlation_id": correlation_id, "provider": self.code,
            "duration_ms": duration_ms,
            "status": f"sources={len(result.sources)}"})
        return result


def normalize_tavily(payload: Mapping[str, Any], *, query: str, market: str,
                     language: str) -> ResearchProviderResult:
    """Map a Tavily search response into the provider-neutral result."""
    raw_results = payload.get("results")
    if raw_results is None:
        raise ResearchContractError("Tavily response has no results array")
    if not isinstance(raw_results, list):
        raise ResearchContractError("Tavily results is not an array")

    retrieved_at = datetime.now(timezone.utc)
    sources: list[NormalizedSource] = []
    facts: list[NormalizedFact] = []

    for index, entry in enumerate(raw_results):
        if not isinstance(entry, Mapping):
            continue
        url = _as_str(entry.get("url"))
        if not url:
            # A source we cannot cite is not usable evidence.
            continue

        title = _as_str(entry.get("title"))
        content = _as_str(entry.get("content"))
        score = _as_float(entry.get("score"))
        # Present only for topic="news"; absent on a general search.
        published_at = _parse_dt(entry.get("published_date"))
        ref = _as_str(entry.get("id")) or f"tavily-{index:03d}"

        sources.append(NormalizedSource(
            source_type="web",
            state=SourceState.OK,
            url=url,
            title=title,
            published_at=published_at,
            retrieved_at=retrieved_at,
            summary=content,
            # NOT a factual confidence — see the module docstring.
            confidence=None,
            candidate_id=ref,
            metadata={"tavily": {"relevance_score": score,
                                 "favicon": _as_str(entry.get("favicon"))}},
        ))

        if content:
            facts.append(NormalizedFact(
                fact=content,
                evidence_type="retrieved_excerpt",
                # Dated → OBSERVED; undated → ESTIMATED. Tavily's general search
                # supplies no date, so most Phase 3 web evidence lands ESTIMATED,
                # which is honest rather than pessimistic.
                observability=(Observability.OBSERVED if published_at
                               else Observability.ESTIMATED),
                confidence=None,
                source_ref=ref,
            ))

    state = SourceState.OK if sources else SourceState.NO_RESULTS
    outcomes = [SourceOutcome(source_type="web", state=state,
                              item_count=len(sources))]

    unresolved: list[str] = []
    if not sources:
        unresolved.append(
            "Tavily completed cleanly and returned no web sources for this query."
        )
    undated = sum(1 for s in sources if s.published_at is None)
    if undated:
        unresolved.append(
            f"{undated} of {len(sources)} web sources carry no publication date; "
            f"their claims cannot be placed in time and are marked ESTIMATED."
        )

    return ResearchProviderResult(
        provider="tavily",
        query=query,
        market=market,
        language=language,
        status="SUCCEEDED" if sources else "PARTIAL",
        sources=sources,
        facts=facts,
        source_outcomes=outcomes,
        user_questions=[],
        unresolved_data=unresolved,
        provider_metadata={"tavily": {
            "request_id": _as_str(payload.get("request_id")),
            "response_time": _as_float(payload.get("response_time")),
            "result_count": len(raw_results),
            "usage": payload.get("usage"),
        }},
    )


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    """Parse a date if present. Never substitute one if absent."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, f"{text}T00:00:00+00:00"):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    logger.warning("unparseable Tavily published_date discarded: %r", value[:40])
    return None
