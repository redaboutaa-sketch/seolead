"""Brief → draft → QA → approval.

The approval table is separate from the draft rather than a column on it. That is
the structural expression of the rule in the mission: approval is a human act with
an actor and a timestamp, and it must be impossible to reach it by inference from a
QA result. A nullable `approved` boolean on `content_draft` would have made
"QA passed, so it is approved" a one-line mistake away.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (ApprovalState, ContentStatus, ContentType, QALayer,
                            QAStatus, QAType, SearchIntent)
from app.db.base import (Base, JSONType, TZDateTime, UUIDType, created_column,
                         pk_column)

_CONTENT_TYPES = ", ".join(f"'{c.value}'" for c in ContentType)
_INTENTS = ", ".join(f"'{i.value}'" for i in SearchIntent)
_APPROVAL_STATES = ", ".join(f"'{s.value}'" for s in ApprovalState)
_QA_STATUSES = ", ".join(f"'{s.value}'" for s in QAStatus)
_QA_TYPES = ", ".join(f"'{t.value}'" for t in QAType)
_QA_LAYERS = ", ".join(f"'{layer.value}'" for layer in QALayer)


class ContentBrief(Base):
    __tablename__ = "content_brief"
    __table_args__ = (
        CheckConstraint(f"content_type IN ({_CONTENT_TYPES})", name="ck_brief_type"),
        CheckConstraint(f"search_intent IN ({_INTENTS})", name="ck_brief_intent"),
        Index("ix_content_brief_package", "research_package_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    research_package_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("research_package.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_query: Mapped[str] = mapped_column(Text, nullable=False)
    search_intent: Mapped[str] = mapped_column(String(32), nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_title: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    outline: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    key_questions: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Facts the draft MUST carry, each already bound to a source.
    required_facts: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    required_sources: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Claims the writer may not make. Survives LLM synthesis by never being sent
    # as something the model can edit — it is re-applied at QA time.
    cautionary_claims: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    cta_strategy: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    internal_linking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_information: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # The one question the page exists to answer, and whether the evidence lets it.
    # Phase 3.4: a price page that states no price passed factual QA because it
    # asserted nothing checkable. Recorded here, that state is visible.
    core_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_answer_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # {"answers": [...], "observed_range": {...} | None}. The range is separate
    # because it is a different kind of statement: a sample the pipeline observed,
    # never a market average.
    core_answer_evidence: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                       default=dict)
    must_answer_directly: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                       default=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ContentStatus.BRIEF_CREATED.value
    )
    generated_by: Mapped[str] = mapped_column(String(32), nullable=False,
                                              default="deterministic")
    created_at = created_column()

    drafts: Mapped[list["ContentDraft"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan"
    )


class ContentDraft(Base):
    """Generated content. Never stores hidden model reasoning — only the output."""

    __tablename__ = "content_draft"
    __table_args__ = (Index("ix_content_draft_brief", "content_brief_id"),)

    id: Mapped[uuid.UUID] = pk_column()
    content_brief_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("content_brief.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ContentStatus.DRAFT_CREATED.value
    )
    # Cost accounting from the first draft: the project's KPI is profitable leads,
    # and a factory that cannot report its own cost cannot report profit.
    usage: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at = created_column()

    brief: Mapped[ContentBrief] = relationship(back_populates="drafts")
    qa_reviews: Mapped[list["QAReview"]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )
    approval: Mapped["Approval | None"] = relationship(
        back_populates="draft", cascade="all, delete-orphan", uselist=False
    )


class QAReview(Base):
    __tablename__ = "qa_review"
    __table_args__ = (
        CheckConstraint(f"status IN ({_QA_STATUSES})", name="ck_qa_status"),
        CheckConstraint(f"qa_type IN ({_QA_TYPES})", name="ck_qa_type"),
        CheckConstraint(f"layer IS NULL OR layer IN ({_QA_LAYERS})",
                        name="ck_qa_layer"),
        Index("ix_qa_review_draft", "content_draft_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    content_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("content_draft.id", ondelete="CASCADE"), nullable=False
    )
    qa_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Nullable: rows written before Phase 4 have no layer, and the gate falls
    # back to inspecting their finding codes rather than refusing to read them.
    layer: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    findings: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    blocking_issues: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at = created_column()

    draft: Mapped[ContentDraft] = relationship(back_populates="qa_reviews")


class Approval(Base):
    """Exactly one approval record per draft, and it starts PENDING.

    The unique constraint is the guard: a second row cannot be inserted to
    overwrite a rejection with an approval, so the decision has one history.
    """

    __tablename__ = "approval"
    __table_args__ = (
        UniqueConstraint("content_draft_id", name="uq_approval_draft"),
        CheckConstraint(f"state IN ({_APPROVAL_STATES})", name="ck_approval_state"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    content_draft_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("content_draft.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ApprovalState.PENDING.value
    )
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = created_column()

    draft: Mapped[ContentDraft] = relationship(back_populates="approval")
