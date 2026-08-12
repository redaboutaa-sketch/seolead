"""Vertical / Site / SeedKeyword — the configuration spine.

`Vertical` carries no solar-specific column. Everything solar lives in the YAML
profile under `config/verticals/` and is joined at runtime by `code`. That is what
makes the pipeline reusable: adding AI_TRAINING_FR is a config file and a row, not
a code change.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import KeywordStatus, SiteStatus
from app.db.base import Base, UUIDType, created_column, pk_column, updated_column


class Vertical(Base):
    __tablename__ = "vertical"

    id: Mapped[uuid.UUID] = pk_column()
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    default_language: Mapped[str] = mapped_column(String(8), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = created_column()
    updated_at = updated_column()

    sites: Mapped[list["Site"]] = relationship(back_populates="vertical")


class Site(Base):
    """A site may exist without a domain — Phase 2 has no domain and needs none."""

    __tablename__ = "site"

    id: Mapped[uuid.UUID] = pk_column()
    vertical_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("vertical.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    default_language: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SiteStatus.PLANNED.value
    )
    created_at = created_column()
    updated_at = updated_column()

    vertical: Mapped[Vertical] = relationship(back_populates="sites")


class SeedKeyword(Base):
    """An operator-supplied search intent to research.

    `normalized_query` exists so that "Prix Panneaux Solaires  Belgique" and
    "prix panneaux solaires belgique" are the same seed. Without it, an operator
    retyping a query creates a duplicate keyword and a duplicate research spend.
    """

    __tablename__ = "seed_keyword"
    __table_args__ = (
        UniqueConstraint("vertical_id", "normalized_query", "language", "market",
                         name="uq_seed_keyword_scope"),
        Index("ix_seed_keyword_vertical", "vertical_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    vertical_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("vertical.id", ondelete="RESTRICT"), nullable=False
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=KeywordStatus.NEW.value
    )
    created_at = created_column()

    vertical: Mapped[Vertical] = relationship()
