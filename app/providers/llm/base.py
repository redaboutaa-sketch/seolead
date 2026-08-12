"""The LLMProvider port.

`capability` is the routing key rather than a model name. Business code asks for
LONG_FORM_WRITING and never names a model, so swapping providers or tiers is a
configuration change. The shape is borrowed from the Hermes gateway pattern
verified during Phase 1 discovery — capability in, usage accounting out.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LLMCapability(StrEnum):
    RESEARCH_SYNTHESIS = "RESEARCH_SYNTHESIS"
    CONTENT_BRIEF = "CONTENT_BRIEF"
    LONG_FORM_WRITING = "LONG_FORM_WRITING"
    CLASSIFICATION = "CLASSIFICATION"
    SEO_QA = "SEO_QA"


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    # Populated when a price table is configured. Left at None rather than zero:
    # "we did not price this" and "this was free" are different facts.
    cost_cents: float | None = None


class LLMRequest(BaseModel):
    capability: LLMCapability
    prompt: str
    system: str | None = None
    correlation_id: str = ""
    response_format: str = "text"          # text | json
    temperature: float = 0.4
    max_tokens: int = 2048


class LLMResponse(BaseModel):
    content: str
    provider: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    code: str

    @property
    def configured(self) -> bool:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...
