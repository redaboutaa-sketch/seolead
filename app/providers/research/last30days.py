"""Last30DaysProvider — HTTP client for the SEO Lead Factory's own runner.

Talks to `seolead_last30days`, never to the ChainPilot instance. The runner has no
authentication by design (see docs/providers/LAST30DAYS.md); its only access
control is that it publishes no port and lives on an internal Docker network. That
is a property of the deployment, so this client must never be pointed at a URL
that leaves that network.
"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.core.errors import (ResearchContractError, ResearchProviderError,
                             ResearchTimeout, ResearchUnavailable)
from app.providers.research.last30days_normalizer import normalize
from app.schemas.research import ResearchProviderResult

logger = logging.getLogger(__name__)

# Sources worth querying for SEO research. Deliberately narrower than the runner's
# whitelist: polymarket and stocktwits are market-sentiment sources with nothing to
# say about consumer search intent, and asking for them would only produce noise
# and `skipped-unconfigured` rows.
DEFAULT_SEO_SOURCES = ("web", "reddit", "youtube", "hackernews")


def build_idempotency_key(query: str, market: str, language: str, day: str) -> str:
    """Same query, same market, same day → same key.

    Scoped to the day rather than forever: research goes stale, and an operator
    re-running next week legitimately wants fresh observations. Re-running twice
    in one afternoon does not.
    """
    raw = f"{query}|{market}|{language}|{day}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:64]


class Last30DaysProvider:
    code = "last30days"

    def __init__(self, settings: Settings, *,
                 transport: httpx.AsyncBaseTransport | None = None,
                 sources: tuple[str, ...] = DEFAULT_SEO_SOURCES):
        self._base_url = settings.last30days_url.rstrip("/")
        self._timeout = settings.last30days_timeout_seconds
        self._window_days = settings.last30days_window_days
        self._max_results = settings.last30days_max_results
        self._sources = sources
        self._transport = transport

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout or self._timeout,
            transport=self._transport,
        )

    async def health(self) -> dict:
        """Never raises — an unreachable runner is a fact to report, not an error."""
        try:
            async with self._client(timeout=10) as client:
                response = await client.get("/healthz")
                body = response.json() if response.status_code == 200 else {}
                return {
                    "reachable": response.status_code == 200,
                    "status_code": response.status_code,
                    "engine_commit": body.get("engine_commit"),
                    "engine_version": body.get("engine_version"),
                    "runner_version": body.get("runner_version"),
                }
        except httpx.HTTPError as exc:
            return {"reachable": False, "error": type(exc).__name__}

    async def research(
        self,
        *,
        query: str,
        market: str,
        language: str,
        correlation_id: str,
        idempotency_key: str | None = None,
    ) -> ResearchProviderResult:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = idempotency_key or build_idempotency_key(query, market, language, day)

        payload = {
            "topic": query,
            "sources": list(self._sources),
            "window_days": self._window_days,
            "verify_freshness": True,
            "max_results": self._max_results,
            "correlation_id": correlation_id,
        }
        headers = {
            "Idempotency-Key": key,
            "X-Correlation-Id": correlation_id,
            "X-Requested-By": "seolead",
            "Content-Type": "application/json",
        }

        started = datetime.now(timezone.utc)
        monotonic_start = time.monotonic()
        logger.info(
            "last30days research starting",
            extra={"correlation_id": correlation_id, "provider": self.code},
        )

        try:
            async with self._client() as client:
                response = await client.post("/v1/research", json=payload,
                                             headers=headers)
        except httpx.TimeoutException as exc:
            raise ResearchTimeout(type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise ResearchUnavailable(type(exc).__name__) from exc

        if response.status_code == 504:
            raise ResearchTimeout("runner reported engine timeout")
        if response.status_code == 503:
            raise ResearchUnavailable(_safe_detail(response))
        if response.status_code >= 400:
            raise ResearchProviderError(
                f"runner returned {response.status_code}: {_safe_detail(response)}"
            )

        try:
            envelope = response.json()
        except ValueError as exc:
            raise ResearchContractError("runner response is not JSON") from exc

        result = normalize(envelope, query=query, market=market, language=language)
        completed = datetime.now(timezone.utc)
        result.started_at = started
        result.completed_at = completed
        if result.duration_ms is None:
            result.duration_ms = int((time.monotonic() - monotonic_start) * 1000)

        logger.info(
            "last30days research complete",
            extra={
                "correlation_id": correlation_id, "provider": self.code,
                "status": result.status, "duration_ms": result.duration_ms,
            },
        )
        return result


def _safe_detail(response: httpx.Response) -> str:
    """Bounded, never interpreted. Runner error details can carry external text."""
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else body
    except ValueError:
        detail = response.text
    return str(detail)[:300]
