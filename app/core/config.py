"""Runtime configuration.

Every setting arrives from the environment. Nothing here carries a real default
for a credential: an unset key stays unset, and the code downstream is written to
treat "unset" as a first-class state rather than an error to paper over.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Application ──────────────────────────────────────────────────────────
    env: str = Field("dev", alias="SEOLEAD_ENV")
    log_level: str = Field("INFO", alias="SEOLEAD_LOG_LEVEL")
    internal_api_key: str = Field("", alias="SEOLEAD_INTERNAL_API_KEY")

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        "postgresql+asyncpg://seolead_app:unset@platform_postgres:5432/seolead",
        alias="SEOLEAD_DATABASE_URL",
    )

    # ── Last30Days ───────────────────────────────────────────────────────────
    last30days_url: str = Field(
        "http://seolead_last30days:8080", alias="SEOLEAD_LAST30DAYS_URL"
    )
    last30days_timeout_seconds: int = Field(
        600, alias="SEOLEAD_LAST30DAYS_TIMEOUT_SECONDS"
    )
    last30days_window_days: int = Field(30, alias="SEOLEAD_LAST30DAYS_WINDOW_DAYS")
    last30days_max_results: int = Field(100, alias="SEOLEAD_LAST30DAYS_MAX_RESULTS")

    # ── DataForSEO (search intelligence) ─────────────────────────────────────
    dataforseo_login: str = Field("", alias="DATAFORSEO_LOGIN")
    dataforseo_password: str = Field("", alias="DATAFORSEO_PASSWORD")
    dataforseo_base_url: str = Field("https://api.dataforseo.com",
                                     alias="DATAFORSEO_BASE_URL")
    dataforseo_timeout_seconds: int = Field(120, alias="DATAFORSEO_TIMEOUT_SECONDS")
    dataforseo_serp_depth: int = Field(20, alias="DATAFORSEO_SERP_DEPTH")

    # ── Tavily (web research) ────────────────────────────────────────────────
    tavily_api_key: str = Field("", alias="TAVILY_API_KEY")
    tavily_base_url: str = Field("https://api.tavily.com", alias="TAVILY_BASE_URL")
    tavily_timeout_seconds: int = Field(120, alias="TAVILY_TIMEOUT_SECONDS")
    tavily_max_results: int = Field(10, alias="TAVILY_MAX_RESULTS")
    tavily_search_depth: str = Field("advanced", alias="TAVILY_SEARCH_DEPTH")

    # ── Research freshness (TTL, in hours) ───────────────────────────────────
    serp_ttl_hours: int = Field(24, alias="SEOLEAD_SERP_TTL_HOURS")
    web_research_ttl_hours: int = Field(168, alias="SEOLEAD_WEB_RESEARCH_TTL_HOURS")
    community_ttl_hours: int = Field(72, alias="SEOLEAD_COMMUNITY_TTL_HOURS")

    # ── Per-job provider call ceilings ───────────────────────────────────────
    max_calls_per_provider: int = Field(3, alias="SEOLEAD_MAX_CALLS_PER_PROVIDER")

    # ── Relevance thresholds ─────────────────────────────────────────────────
    relevance_relevant_at: float = Field(0.55, alias="SEOLEAD_RELEVANCE_RELEVANT_AT")
    relevance_low_at: float = Field(0.30, alias="SEOLEAD_RELEVANCE_LOW_AT")
    relevance_semantic_enabled: bool = Field(
        True, alias="SEOLEAD_RELEVANCE_SEMANTIC_ENABLED")

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: str = Field("openai_compatible", alias="SEOLEAD_LLM_PROVIDER")
    llm_api_key: str = Field("", alias="SEOLEAD_LLM_API_KEY")
    llm_base_url: str = Field("https://api.openai.com/v1", alias="SEOLEAD_LLM_BASE_URL")
    llm_model: str = Field("gpt-4o-mini", alias="SEOLEAD_LLM_MODEL")
    llm_timeout_seconds: int = Field(120, alias="SEOLEAD_LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(2, alias="SEOLEAD_LLM_MAX_RETRIES")

    @property
    def llm_configured(self) -> bool:
        """Whether a real LLM call is possible.

        Checked before every generation step so the pipeline can stop with
        LLM_NOT_CONFIGURED instead of failing deep inside an HTTP client.
        """
        return bool(self.llm_api_key.strip())

    @property
    def internal_api_protected(self) -> bool:
        return bool(self.internal_api_key.strip())

    @property
    def dataforseo_configured(self) -> bool:
        return bool(self.dataforseo_login.strip() and self.dataforseo_password.strip())

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key.strip())

    def credential_report(self) -> dict[str, str]:
        """CONFIGURED / NOT_CONFIGURED per provider.

        Returns statuses only. No value, no prefix, no length — a report that
        leaks four characters of a key is still a leak.
        """
        return {
            "DATAFORSEO": "CONFIGURED" if self.dataforseo_configured else "NOT_CONFIGURED",
            "TAVILY": "CONFIGURED" if self.tavily_configured else "NOT_CONFIGURED",
            "OPENAI": "CONFIGURED" if self.llm_configured else "NOT_CONFIGURED",
            "INTERNAL_API": "CONFIGURED" if self.internal_api_protected else "NOT_CONFIGURED",
        }

    def relevance_thresholds(self):
        from app.services.relevance import RelevanceThresholds
        return RelevanceThresholds(
            relevant_at=self.relevance_relevant_at,
            low_relevance_at=self.relevance_low_at,
            irrelevant_below=self.relevance_low_at,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
