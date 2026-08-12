"""API dependencies: authentication and provider wiring.

The internal API is not routed through Traefik and publishes no public port, but
network isolation alone is not an authentication model — anything that lands on
the Docker network would otherwise be able to approve content. A shared key is
required, and the service refuses to start an unprotected mutating API rather than
running open and hoping the network holds.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.registry import get_llm_provider
from app.providers.research.base import ResearchProvider
from app.providers.research.last30days import Last30DaysProvider


async def require_internal_key(
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.internal_api_protected:
        # Fail closed. An unset key must never mean "no check".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="internal API key is not configured; refusing to serve",
        )
    if not x_internal_key or not hmac.compare_digest(
        x_internal_key, settings.internal_api_key
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Unauthorized")


def get_research_provider(
    settings: Settings = Depends(get_settings),
) -> ResearchProvider:
    return Last30DaysProvider(settings)


def get_llm(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)
