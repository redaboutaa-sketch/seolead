"""The SearchIntelligenceProvider port."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.providers.search.location import SearchContext
from app.schemas.serp import KeywordMetric, SerpSnapshot


@runtime_checkable
class SearchIntelligenceProvider(Protocol):
    code: str

    @property
    def configured(self) -> bool:
        ...

    async def serp(self, *, query: str, context: SearchContext,
                   correlation_id: str, depth: int = 20) -> SerpSnapshot:
        ...

    async def keyword_metrics(self, *, keywords: list[str], context: SearchContext,
                              correlation_id: str) -> dict[str, list[KeywordMetric]]:
        """Returns metrics per keyword. A keyword absent from the result has
        UNKNOWN metrics — never a zero."""
        ...
