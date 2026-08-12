"""The ResearchProvider port."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.research import ResearchProviderResult


@runtime_checkable
class ResearchProvider(Protocol):
    code: str

    async def research(
        self,
        *,
        query: str,
        market: str,
        language: str,
        correlation_id: str,
        idempotency_key: str | None = None,
    ) -> ResearchProviderResult:
        ...

    async def health(self) -> dict:
        """Never raises. An unreachable provider is information, not an exception."""
        ...
