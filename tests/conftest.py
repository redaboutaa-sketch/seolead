"""Shared fixtures.

Persistence tests run on in-memory SQLite against the same models production uses.
That is the point: the models must not depend on a PostgreSQL-only feature, and
running them on a second dialect is what proves it.

No test reaches the network, and no test needs a credential. The default suite
must pass on a machine with no API keys at all.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models import Vertical
from app.verticals.profile import load_profile

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def agent_report() -> dict:
    """A Last30Days agent report exercising all ten source states."""
    return json.loads((FIXTURE_DIR / "last30days_agent_report.json").read_text())


@pytest.fixture
def envelope(agent_report: dict) -> dict:
    """The runner's response envelope wrapping the engine report.

    Deep-copied: `agent_report` is session-scoped, and several tests mutate the
    report to exercise contract-drift paths. Without the copy those mutations
    would leak into every later test in the session, and the suite would pass or
    fail depending on ordering.
    """
    return {
        "run_id": "0" * 32,
        "correlation_id": "test-correlation",
        "engine_version": "1.4.2",
        "engine_commit": "52f53312ff2f272e16bbc1785e1c04f9d9c19b31",
        "runner_version": "1.0.0",
        "duration_ms": 4210,
        "warnings": [],
        "report": copy.deepcopy(agent_report),
        "idempotent_replay": False,
    }


@pytest.fixture
def solar_profile():
    return load_profile("SOLAR_BE")


@pytest.fixture
def generic_profile():
    """A second vertical sharing nothing with solar — the isolation control."""
    return load_profile("TEST_GENERIC")


@pytest.fixture
def settings_no_llm() -> Settings:
    return Settings(
        # Hermetic: never read the operator's real .env. Without this the suite
        # silently picks up live credentials, so `settings_no_llm` stops meaning
        # "nothing configured" the moment a key lands on the box — and a test
        # asserting unconfigured behaviour passes or fails by machine state.
        _env_file=None,
        SEOLEAD_INTERNAL_API_KEY="test-key-not-a-real-secret",
        SEOLEAD_LLM_API_KEY="",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def settings_with_llm() -> Settings:
    return Settings(
        # Hermetic: never read the operator's real .env. Without this the suite
        # silently picks up live credentials, so `settings_no_llm` stops meaning
        # "nothing configured" the moment a key lands on the box — and a test
        # asserting unconfigured behaviour passes or fails by machine state.
        _env_file=None,
        SEOLEAD_INTERNAL_API_KEY="test-key-not-a-real-secret",
        SEOLEAD_LLM_API_KEY="test-llm-key-not-a-real-secret",
        SEOLEAD_LLM_BASE_URL="https://llm.invalid/v1",
        SEOLEAD_LLM_MODEL="test-model",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def settings_dataforseo() -> Settings:
    return Settings(
        # Hermetic: never read the operator's real .env. Without this the suite
        # silently picks up live credentials, so `settings_no_llm` stops meaning
        # "nothing configured" the moment a key lands on the box — and a test
        # asserting unconfigured behaviour passes or fails by machine state.
        _env_file=None,
        SEOLEAD_INTERNAL_API_KEY="test-key-not-a-real-secret",
        DATAFORSEO_LOGIN="test-login",
        DATAFORSEO_PASSWORD="test-password-not-real",
        DATAFORSEO_BASE_URL="https://dataforseo.invalid",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def settings_tavily() -> Settings:
    return Settings(
        # Hermetic: never read the operator's real .env. Without this the suite
        # silently picks up live credentials, so `settings_no_llm` stops meaning
        # "nothing configured" the moment a key lands on the box — and a test
        # asserting unconfigured behaviour passes or fails by machine state.
        _env_file=None,
        SEOLEAD_INTERNAL_API_KEY="test-key-not-a-real-secret",
        TAVILY_API_KEY="test-tavily-key-not-real",
        TAVILY_BASE_URL="https://tavily.invalid",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def settings_all_providers() -> Settings:
    """Every provider configured. Still no network — transports are mocked."""
    return Settings(
        # Hermetic: never read the operator's real .env. Without this the suite
        # silently picks up live credentials, so `settings_no_llm` stops meaning
        # "nothing configured" the moment a key lands on the box — and a test
        # asserting unconfigured behaviour passes or fails by machine state.
        _env_file=None,
        SEOLEAD_INTERNAL_API_KEY="test-key-not-a-real-secret",
        DATAFORSEO_LOGIN="test-login",
        DATAFORSEO_PASSWORD="test-password-not-real",
        DATAFORSEO_BASE_URL="https://dataforseo.invalid",
        TAVILY_API_KEY="test-tavily-key-not-real",
        TAVILY_BASE_URL="https://tavily.invalid",
        SEOLEAD_LLM_API_KEY="test-llm-key-not-a-real-secret",
        SEOLEAD_LLM_BASE_URL="https://llm.invalid/v1",
        SEOLEAD_LLM_MODEL="test-model",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        yield db
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(session):
    """A session with SOLAR_BE and TEST_GENERIC registered."""
    for code in ("SOLAR_BE", "TEST_GENERIC"):
        profile = load_profile(code)
        session.add(Vertical(
            code=profile.code, name=profile.name, market=profile.market,
            default_language=profile.default_language, active=True,
        ))
    await session.commit()
    return session
