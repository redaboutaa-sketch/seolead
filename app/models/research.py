"""Research persistence: run → sources → evidence → package.

The shape of these tables encodes one rule that matters more than the rest:
a `ResearchSource` row exists for every source that was *asked*, carrying its
outcome state, whether or not it produced anything. A source that was rate-limited
therefore leaves a visible trace instead of silently looking identical to a source
that genuinely found nothing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Float, ForeignKey, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import Observability, RunStatus, SourceState
from app.db.base import (Base, JSONType, TZDateTime, UUIDType, created_column,
                         pk_column)

_SOURCE_STATES = ", ".join(f"'{s.value}'" for s in SourceState)
_OBSERVABILITY = ", ".join(f"'{o.value}'" for o in Observability)
_RUN_STATUSES = ", ".join(f"'{s.value}'" for s in RunStatus)


class ResearchRun(Base):
    __tablename__ = "research_run"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_research_run_idempotency"),
        CheckConstraint(f"status IN ({_RUN_STATUSES})", name="ck_research_run_status"),
        Index("ix_research_run_keyword", "keyword_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("seed_keyword.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RunStatus.PENDING.value
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Engine identity. A package produced by a different engine build is not
    # comparable with one produced by this build, so the build is recorded.
    engine_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_metadata: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = created_column()

    sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ResearchSource(Base):
    """One retrieved item, or one source-level outcome with no item.

    `url` and `published_at` are nullable on purpose. Upstream omits unknown
    fields rather than emitting null, and inventing a plausible date here would
    turn a gap in knowledge into a fabricated fact three steps downstream.
    """

    __tablename__ = "research_source"
    __table_args__ = (
        CheckConstraint(f"status IN ({_SOURCE_STATES})", name="ck_research_source_state"),
        Index("ix_research_source_run", "research_run_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("research_run.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    freshness_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Which provider supplied this. V1 had one; V2 has three with different jobs.
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ── Relevance gate (Phase 3) ─────────────────────────────────────────────
    # A rejected source is KEPT, with its reason. "Why was this thrown away" is
    # the question an operator actually asks, and Phase 2 could not answer it.
    relevance_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Provider-specific extras live here, namespaced, rather than leaking into
    # first-class columns that only one provider could ever populate.
    source_metadata: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = created_column()

    run: Mapped[ResearchRun] = relationship(back_populates="sources")
    evidence: Mapped[list["ResearchEvidence"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        CheckConstraint(f"observability IN ({_OBSERVABILITY})",
                        name="ck_research_evidence_observability"),
        Index("ix_research_evidence_source", "research_source_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    research_source_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("research_source.id", ondelete="CASCADE"), nullable=False
    )
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    observability: Mapped[str] = mapped_column(String(16), nullable=False)
    # ── Claim risk (Phase 3) ─────────────────────────────────────────────────
    # How bad it would be if this claim were wrong, and whether the evidence
    # behind it clears the bar that risk level demands.
    claim_risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    support_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    evidence_sufficient: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at = created_column()

    source: Mapped[ResearchSource] = relationship(back_populates="evidence")


class ResearchPackage(Base):
    """The sealed, normalized artefact the writer consumes.

    Denormalised into JSONB deliberately: once a brief is built from a package,
    the package must not change underneath it. Copying the facts in at seal time
    is what makes a draft traceable to the evidence that actually existed when it
    was written.
    """

    __tablename__ = "research_package"
    __table_args__ = (Index("ix_research_package_keyword", "keyword_id"),)

    id: Mapped[uuid.UUID] = pk_column()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("seed_keyword.id", ondelete="CASCADE"), nullable=False
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("research_run.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ── V2 (Phase 3) ─────────────────────────────────────────────────────────
    # `package_version` is the SHAPE of the package (1 or 2); `version` above is
    # the revision number for one keyword. Conflating them would make "which
    # builder produced this" unanswerable.
    package_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    serp_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("serp_snapshot.id", ondelete="SET NULL"), nullable=True
    )
    seo_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("seo_opportunity.id", ondelete="SET NULL"), nullable=True
    )
    eligible_evidence: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    rejected_evidence: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    competitor_pages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    serp_observations: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    serp_features: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    content_gap: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    related_searches: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    keyword_metrics: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    source_quality_summary: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    claim_risk_summary: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    facts: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    sources: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    user_questions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    unresolved_questions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    confidence_summary: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    provider_provenance: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = created_column()
