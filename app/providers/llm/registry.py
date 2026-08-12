"""LLM provider selection.

Only two providers exist in Phase 2. `null` is not a fallback that invents
content — it is a provider that refuses, loudly, so that a missing credential
produces LLM_NOT_CONFIGURED instead of a plausible article nobody researched.

A `HermesGatewayProvider` would slot in here unchanged. Phase 1 verified the
existing Hermes gateway belongs to another product's stack and is read-only, so
it is deliberately not implemented — the seam exists, the coupling does not.
"""
from __future__ import annotations

from app.core.config import Settings
from app.core.errors import LLMNotConfigured
from app.providers.llm.base import LLMProvider, LLMRequest, LLMResponse
from app.providers.llm.openai_compatible import OpenAICompatibleProvider


class NullLLMProvider:
    """Refuses every call. Never fabricates."""

    code = "null"
    model = "none"

    @property
    def configured(self) -> bool:
        return False

    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMNotConfigured("no LLM provider is configured")


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible" and settings.llm_configured:
        return OpenAICompatibleProvider(settings)
    return NullLLMProvider()
