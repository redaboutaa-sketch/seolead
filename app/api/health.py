"""Health and readiness. Unauthenticated by necessity, so they reveal nothing.

`/health` answers "is the process alive". `/ready` answers "can it do its job",
which means the database answers and the research runner is reachable. The
distinction matters operationally: a service that reports ready without a runner
would lie to whatever is watching it.

Neither endpoint returns a credential, a URL containing one, or a provider key —
only booleans and version strings that the runner itself publishes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.providers.research.base import ResearchProvider
from app.api.deps import get_research_provider

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "service": "seolead", "env": settings.env}


@router.get("/ready")
async def ready(
    settings: Settings = Depends(get_settings),
    research: ResearchProvider = Depends(get_research_provider),
) -> JSONResponse:
    checks: dict[str, object] = {}

    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001 — readiness must not itself raise
        checks["database"] = {"ok": False, "error": type(exc).__name__}

    runner = await research.health()
    checks["research_provider"] = {
        "ok": bool(runner.get("reachable")),
        "engine_commit": runner.get("engine_commit"),
        "engine_version": runner.get("engine_version"),
    }

    # Not a readiness failure. The pipeline is designed to run without an LLM and
    # stop cleanly at LLM_NOT_CONFIGURED, so an absent key is a capability
    # statement rather than a fault.
    checks["llm"] = {"configured": settings.llm_configured}
    checks["internal_api"] = {"protected": settings.internal_api_protected}

    ready_now = bool(checks["database"]["ok"]) and bool(
        checks["research_provider"]["ok"]
    )
    return JSONResponse(
        status_code=200 if ready_now else 503,
        content={"ready": ready_now, "checks": checks},
    )
