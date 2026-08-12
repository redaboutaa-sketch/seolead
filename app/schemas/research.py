"""Provider-neutral research types.

These are the only shapes the rest of the application sees. `Last30DaysProvider`
maps its wire format into these; a future SerpProvider or FirecrawlProvider maps
into the same ones. Anything genuinely provider-specific goes into
`provider_metadata`, namespaced, rather than growing a column nobody else can fill.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import FreshnessVerdict, Observability, SourceState


class NormalizedFact(BaseModel):
    """A claim, and how much we actually know about it.

    `observability` is required and has no default. A fact whose provenance nobody
    stated cannot be created by accident.
    """

    model_config = ConfigDict(frozen=True)

    fact: str
    evidence_type: str = "statement"
    observability: Observability
    confidence: float | None = None
    # Index into ResearchProviderResult.sources, keeping claim → source traceable.
    source_ref: str | None = None


class NormalizedSource(BaseModel):
    """One source outcome. May carry an item, or may carry only a state.

    A `rate-limited` source appears here with no url and no title. That row is the
    difference between "nobody discussed this" and "we could not look".
    """

    model_config = ConfigDict(frozen=True)

    source_type: str
    state: SourceState
    url: str | None = None
    title: str | None = None
    # Omitted upstream when unknown. Stays None — never back-filled with "today".
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    summary: str | None = None
    confidence: float | None = None
    freshness_verdict: FreshnessVerdict | None = None
    candidate_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class SourceOutcome(BaseModel):
    """Per-source-type outcome, independent of how many items it produced."""

    model_config = ConfigDict(frozen=True)

    source_type: str
    state: SourceState
    item_count: int = 0


class ResearchProviderResult(BaseModel):
    """What every ResearchProvider returns."""

    provider: str
    query: str
    market: str
    language: str
    status: str
    sources: list[NormalizedSource] = Field(default_factory=list)
    facts: list[NormalizedFact] = Field(default_factory=list)
    source_outcomes: list[SourceOutcome] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    unresolved_data: list[str] = Field(default_factory=list)
    provider_metadata: dict = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    engine_commit: str | None = None
    engine_version: str | None = None
    warnings: list[str] = Field(default_factory=list)

    # ── Honest aggregate accessors ───────────────────────────────────────────
    # These exist so that no caller has to re-derive the source-state semantics
    # and get them subtly wrong.

    @property
    def degraded_sources(self) -> list[SourceOutcome]:
        return [o for o in self.source_outcomes if o.state.is_degraded]

    @property
    def unconfigured_sources(self) -> list[SourceOutcome]:
        return [o for o in self.source_outcomes if not o.state.was_attempted]

    @property
    def clean_empty_sources(self) -> list[SourceOutcome]:
        return [o for o in self.source_outcomes if o.state.is_clean_empty]

    @property
    def is_partial(self) -> bool:
        """True when at least one source could not be observed.

        Callers must not read "no facts" as "nothing exists" while this is true.
        """
        return bool(self.degraded_sources)
