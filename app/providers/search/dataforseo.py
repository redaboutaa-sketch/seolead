"""DataForSEOProvider — Google SERP structure and keyword metrics.

Contract verified against the official v3 documentation during implementation:

    POST https://api.dataforseo.com/v3/serp/google/organic/live/advanced
    POST https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live
    Authorization: Basic base64(login:password)
    body: a JSON ARRAY containing exactly one task object

Credentials arrive from the environment only. `httpx` builds the Basic header from
`auth=(login, password)` so the credential is never assembled into a string this
code logs, and never appears in a URL.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.core.errors import (ProviderNotConfigured, ResearchContractError,
                             ResearchProviderError, ResearchTimeout,
                             ResearchUnavailable)
from app.providers.search.dataforseo_normalizer import (normalize_keyword_metrics,
                                                        normalize_serp)
from app.providers.search.location import SearchContext
from app.schemas.serp import KeywordMetric, SerpSnapshot
from app.services.provider_usage import UsageRecorder

logger = logging.getLogger(__name__)

SERP_PATH = "/v3/serp/google/organic/live/advanced"
KEYWORD_PATH = "/v3/keywords_data/google_ads/search_volume/live"


class DataForSEOProvider:
    code = "dataforseo"

    def __init__(self, settings: Settings, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 usage: UsageRecorder | None = None):
        self._login = settings.dataforseo_login.strip()
        self._password = settings.dataforseo_password.strip()
        self._base_url = settings.dataforseo_base_url.rstrip("/")
        self._timeout = settings.dataforseo_timeout_seconds
        self._transport = transport
        self._usage = usage or UsageRecorder()

    @property
    def configured(self) -> bool:
        return bool(self._login and self._password)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
            # httpx encodes Basic itself; the credential never becomes a string here.
            auth=(self._login, self._password),
            headers={"Content-Type": "application/json"},
        )

    async def _post(self, path: str, body: list[dict], *, operation: str,
                    correlation_id: str) -> dict:
        if not self.configured:
            raise ProviderNotConfigured("DataForSEO credentials are not configured")

        started = time.monotonic()
        try:
            async with self._client() as client:
                response = await client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise ResearchTimeout(type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise ResearchUnavailable(type(exc).__name__) from exc

        duration_ms = int((time.monotonic() - started) * 1000)

        if response.status_code == 401:
            # Not retryable, and the message must not echo the credential.
            raise ResearchProviderError("DataForSEO rejected the credentials (401)",
                                        retryable=False)
        if response.status_code == 402:
            raise ResearchProviderError(
                "DataForSEO reports insufficient funds (402)", retryable=False)
        if response.status_code == 429:
            raise ResearchUnavailable("DataForSEO rate limit (429)")
        if response.status_code >= 400:
            raise ResearchProviderError(
                f"DataForSEO returned {response.status_code}", retryable=False)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchContractError("DataForSEO response is not JSON") from exc

        # `cost` is DataForSEO's own billing figure in USD — real, not estimated.
        self._usage.record(
            provider=self.code, operation=operation, correlation_id=correlation_id,
            requests=1, cost_usd=_safe_float(payload.get("cost")),
            duration_ms=duration_ms, cost_is_actual=True,
        )
        return payload

    async def serp(self, *, query: str, context: SearchContext,
                   correlation_id: str, depth: int = 20) -> SerpSnapshot:
        body = [{
            "keyword": query[:700],
            "location_code": context.location_code,
            "language_code": context.language_code,
            "device": context.device,
            "os": context.os,
            "depth": max(10, min(depth, 200)),
            "se_domain": context.se_domain,
        }]
        logger.info("dataforseo serp request", extra={
            "correlation_id": correlation_id, "provider": self.code})

        payload = await self._post(SERP_PATH, body, operation="serp",
                                   correlation_id=correlation_id)
        snapshot = normalize_serp(payload, context=context, query=query)

        logger.info("dataforseo serp complete", extra={
            "correlation_id": correlation_id, "provider": self.code,
            "status": f"organic={len(snapshot.organic)} paa={len(snapshot.paa)}"})
        return snapshot

    async def keyword_metrics(self, *, keywords: list[str], context: SearchContext,
                              correlation_id: str) -> dict[str, list[KeywordMetric]]:
        if not keywords:
            return {}

        body = [{
            "keywords": [k[:80] for k in keywords[:1000]],
            "location_code": context.location_code,
            "language_code": context.language_code,
        }]
        payload = await self._post(KEYWORD_PATH, body, operation="keyword_metrics",
                                   correlation_id=correlation_id)
        raw = normalize_keyword_metrics(payload, provider=self.code)

        from app.core.enums import Observability

        out: dict[str, list[KeywordMetric]] = {}
        for keyword, metrics in raw.items():
            out[keyword] = [
                KeywordMetric(
                    metric_type=m["metric_type"], value=m["value"],
                    value_text=m["value_text"], currency=m["currency"],
                    # Reported by the provider from its own data: OBSERVED as a
                    # provider observation, which is not the same as a fact about
                    # the world. The metric carries who said it and when.
                    observability=Observability.OBSERVED,
                    provider=self.code,
                    retrieved_at=m["retrieved_at"] or datetime.now(timezone.utc),
                )
                for m in metrics
            ]
        return out

    async def health(self) -> dict:
        return {"configured": self.configured, "provider": self.code,
                "base_url": self._base_url}


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
