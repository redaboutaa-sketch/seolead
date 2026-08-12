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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
