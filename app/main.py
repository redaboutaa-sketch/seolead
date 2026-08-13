"""FastAPI application.

The OpenAPI schema is disabled. This service is internal-only and its routes are
approval and pipeline control; publishing a self-describing schema would be free
reconnaissance for anything that reached the network, and no browser client needs
it in Phase 2.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, internal, site
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_: FastAPI):
    if not settings.internal_api_protected:
        # Loud, and the internal router already fails closed with 503.
        logger.error(
            "SEOLEAD_INTERNAL_API_KEY is not set — every /internal route will "
            "refuse to serve until it is."
        )
    logger.info(
        "seolead started",
        extra={"status": "ok", "provider": settings.llm_provider},
    )
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="SEO Lead Factory",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(health.router)
app.include_router(internal.router)
app.include_router(site.router)
