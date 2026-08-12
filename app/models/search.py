"""SERP intelligence, keyword metrics, opportunity scores, provider usage."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Float, ForeignKey, Index,
                        Integer, String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (Base, JSONType, TZDateTime, UUIDType, created_column,
                         pk_column)


class SerpSnapshotRow(Base):
    """One SERP, at one moment, for one (query, location, language, device).

    Stored rather than derived so a brief remains explainable months later: the
    result page moves, and "what was Google showing when we decided this" is not
    answerable retrospectively.
    """

    __tablename__ = "serp_snapshot"
    __table_args__ = (
        Index("ix_serp_snapshot_keyword", "keyword_id"),
        Index("ix_serp_snapshot_lookup", "cache_key", "retrieved_at"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("seed_keyword.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    # Identifies an equivalent search for cache lookup.
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False)
    location_code: Mapped[int] = mapped_column(Integer, nullable=False)
    location_name: Mapped[str] = mapped_column(String(128), nullable=False)
    language_code: Mapped[str] = mapped_column(String(8), nullable=False)
    device: Mapped[str] = mapped_column(String(16), nullable=False)
    se_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    organic_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    provider_metadata: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                    default=dict)
    created_at = created_column()

    results: Mapped[list["SerpResultRow"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan")
    questions: Mapped[list["SerpQuestionRow"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan")


class SerpResultRow(Base):
    __tablename__ = "serp_result"
    __table_args__ = (Index("ix_serp_result_snapshot", "serp_snapshot_id"),)

    id: Mapped[uuid.UUID] = pk_column()
    serp_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("serp_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    rank_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_absolute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_type: Mapped[str] = mapped_column(String(64), nullable=False)
    is_organic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    breadcrumb: Mapped[str | None] = mapped_column(Text, nullable=True)
    shape: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = created_column()

    snapshot: Mapped[SerpSnapshotRow] = relationship(back_populates="results")


class SerpQuestionRow(Base):
    """People-Also-Ask entries and related searches."""

    __tablename__ = "serp_question"
    __table_args__ = (
        CheckConstraint("kind IN ('PAA', 'RELATED')", name="ck_serp_question_kind"),
        Index("ix_serp_question_snapshot", "serp_snapshot_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    serp_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("serp_snapshot.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rank_absolute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at = created_column()

    snapshot: Mapped[SerpSnapshotRow] = relationship(back_populates="questions")


class KeywordMetricRow(Base):
    """A metric with mandatory provenance.

    `observability` is a CHECK-constrained column for the same reason it is on
    evidence: a volume figure with no stated source is indistinguishable from an
    invented one, and the mission forbids inventing them.
    """

    __tablename__ = "keyword_metric"
    __table_args__ = (
        CheckConstraint("observability IN ('OBSERVED', 'ESTIMATED', 'UNKNOWN')",
                        name="ck_keyword_metric_observability"),
        Index("ix_keyword_metric_keyword", "keyword_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("seed_keyword.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    observability: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    metric_metadata: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                  default=dict)
    created_at = created_column()


class SeoOpportunity(Base):
    __tablename__ = "seo_opportunity"
    __table_args__ = (
        CheckConstraint("overall_score IS NULL OR "
                        "(overall_score >= 0 AND overall_score <= 100)",
                        name="ck_opportunity_score_range"),
        Index("ix_seo_opportunity_keyword", "keyword_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("seed_keyword.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_version: Mapped[str] = mapped_column(String(16), nullable=False)
    components: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Named, not silently zeroed. A score from three known inputs must be
    # distinguishable from one built on seven.
    missing_inputs: Mapped[list] = mapped_column(JSONType, nullable=False,
                                                 default=list)
    created_at = created_column()


class ProviderUsage(Base):
    """One paid (or potentially paid) provider call.

    `cost_usd` nullable and `cost_is_actual` separate: DataForSEO returns its own
    billing figure, Tavily and OpenAI do not. Recording 0.0 for the latter would
    claim a job was free when its cost is simply unknown.
    """

    __tablename__ = "provider_usage"
    __table_args__ = (Index("ix_provider_usage_correlation", "correlation_id"),)

    id: Mapped[uuid.UUID] = pk_column()
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_is_actual: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                 default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at = created_column()
