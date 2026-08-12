"""Provider-neutral SERP types.

DataForSEO's response shape stops here. Everything downstream — SERP analysis, the
opportunity score, the brief — sees these types, so replacing the SERP provider is
one adapter.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import Observability


class SerpItemType(StrEnum):
    """The item types we model. Anything else is kept as OTHER with its raw type
    preserved in metadata — an unknown SERP feature is information, not an error."""

    ORGANIC = "organic"
    PAID = "paid"
    FEATURED_SNIPPET = "featured_snippet"
    PEOPLE_ALSO_ASK = "people_also_ask"
    RELATED_SEARCHES = "related_searches"
    LOCAL_PACK = "local_pack"
    VIDEO = "video"
    IMAGES = "images"
    SHOPPING = "shopping"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    OTHER = "other"


class OrganicResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rank_group: int | None = None
    rank_absolute: int | None = None
    domain: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    breadcrumb: str | None = None
    metadata: dict = Field(default_factory=dict)


class SerpFeature(BaseModel):
    model_config = ConfigDict(frozen=True)

    item_type: SerpItemType
    raw_type: str
    rank_absolute: int | None = None
    count: int = 1


class SerpQuestion(BaseModel):
    """A People-Also-Ask entry or a related search."""

    model_config = ConfigDict(frozen=True)

    text: str
    kind: str                       # "PAA" | "RELATED"
    rank_absolute: int | None = None


class KeywordMetric(BaseModel):
    """A metric, with provenance, or an explicit UNKNOWN.

    Never a bare number. Phase 1 and the mission both forbid fabricated volume
    data, and the only structural way to honour that is to make provenance part of
    the type rather than a column somebody may forget to fill.
    """

    model_config = ConfigDict(frozen=True)

    metric_type: str                # search_volume | cpc | competition_index | ...
    value: float | None = None
    value_text: str | None = None
    currency: str | None = None
    observability: Observability = Observability.UNKNOWN
    provider: str = ""
    retrieved_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class SerpSnapshot(BaseModel):
    """One SERP, at one moment, for one search context."""

    provider: str
    query: str
    location_code: int
    location_name: str
    language_code: str
    device: str
    se_domain: str | None = None
    retrieved_at: datetime
    total_items: int = 0
    organic: list[OrganicResult] = Field(default_factory=list)
    features: list[SerpFeature] = Field(default_factory=list)
    questions: list[SerpQuestion] = Field(default_factory=list)
    provider_cost: float | None = None
    provider_metadata: dict = Field(default_factory=dict)

    @property
    def paa(self) -> list[SerpQuestion]:
        return [q for q in self.questions if q.kind == "PAA"]

    @property
    def related(self) -> list[SerpQuestion]:
        return [q for q in self.questions if q.kind == "RELATED"]

    @property
    def feature_types(self) -> set[str]:
        return {f.item_type.value for f in self.features}
