"""Publication, leads, attribution and first-party events.

The publication boundary is the point of this module. `PublishedContent` is a
**snapshot**, not a view onto `ContentDraft`: it stores the sanitized, structured
body that was approved, so a later edit to the draft — or a change in how drafts
are rendered — cannot silently alter a page a human signed off on. The site reads
only from here and never touches the research tables.

`CapturedLead` and `LeadAttribution` are split because they answer different
questions and have different lifetimes. The lead is the person's submitted data,
and it leaves this system once the Prospect 360 boundary opens. The attribution is
how they arrived, and it stays for analysis whatever happens to the lead. Keeping
them in one row would mean either exporting marketing telemetry with the contact
details or losing the funnel record when the lead is archived.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (Boolean, CheckConstraint, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (ConsentChannel, ConsentPurpose, ConversionType,
                            LeadState, PublicationState, SiteEventType)
from app.db.base import (Base, JSONType, TZDateTime, UUIDType, created_column,
                         pk_column, updated_column)

_PUBLICATION_STATES = ", ".join(f"'{s.value}'" for s in PublicationState)
_LEAD_STATES = ", ".join(f"'{s.value}'" for s in LeadState)
_EVENT_TYPES = ", ".join(f"'{t.value}'" for t in SiteEventType)
_CONVERSION_TYPES = ", ".join(f"'{t.value}'" for t in ConversionType)
_CONSENT_PURPOSES = ", ".join(f"'{p.value}'" for p in ConsentPurpose)
_CONSENT_CHANNELS = ", ".join(f"'{c.value}'" for c in ConsentChannel)


class PublishedContent(Base):
    """One approved content snapshot, addressable by (site, locale, slug).

    `version` increments per slug rather than being global, so a page's history
    reads as its own sequence. Only one row per (site, locale, slug) may be live
    at a time — enforced by a partial unique index in the migration rather than a
    table constraint, because "live" is a state, not a column value combination
    SQLite can express.
    """

    __tablename__ = "published_content"
    __table_args__ = (
        CheckConstraint(f"state IN ({_PUBLICATION_STATES})", name="ck_pub_state"),
        UniqueConstraint("site_id", "locale", "slug", "version",
                         name="uq_pub_slug_version"),
        Index("ix_pub_lookup", "site_id", "locale", "slug", "state"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    # Nullable: a hand-authored page (legal notice, contact) has no draft behind
    # it, and refusing to model that would push those pages outside the gate.
    content_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("content_draft.id", ondelete="SET NULL"), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    search_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PublicationState.DRAFT.value)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    meta_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The sanitized structured body: a list of typed sections, never raw HTML.
    sections: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Price answers with their basis and VAT status, kept structured so the site
    # renders them through one component instead of re-parsing prose.
    price_evidence: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                 default=dict)
    cta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Provenance: which QA reviews and approval let this snapshot exist. Recorded
    # so an audit does not have to reconstruct it from timestamps.
    qa_provenance: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                default=dict)
    canonical_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    noindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    staged_at: Mapped[object | None] = mapped_column(TZDateTime, nullable=True)
    published_at: Mapped[object | None] = mapped_column(TZDateTime, nullable=True)
    created_at = created_column()
    updated_at = updated_column()


class CapturedLead(Base):
    """A person who asked to be contacted. Local only in Phase 4."""

    __tablename__ = "captured_lead"
    __table_args__ = (
        CheckConstraint(f"state IN ({_LEAD_STATES})", name="ck_lead_state"),
        CheckConstraint(f"conversion_type IN ({_CONVERSION_TYPES})",
                        name="ck_lead_conversion"),
        Index("ix_lead_state", "state", "created_at"),
        Index("ix_lead_site", "site_id"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("site.id", ondelete="RESTRICT"), nullable=False)
    vertical_code: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False,
                                       default=LeadState.NEW.value)
    conversion_type: Mapped[str] = mapped_column(String(32), nullable=False)

    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False)

    # Vertical-specific qualification answers. Configuration-driven, so adding a
    # question to the Solar form is not a migration.
    qualification: Mapped[dict] = mapped_column(JSONType, nullable=False,
                                                default=dict)

    # Consent is recorded as an event, not a boolean: which text, at what moment,
    # from where. A bare `consented=true` cannot answer "to what?" a year later.
    consent_marketing: Mapped[bool] = mapped_column(Boolean, nullable=False,
                                                    default=False)
    consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    consent_timestamp: Mapped[object | None] = mapped_column(TZDateTime,
                                                             nullable=True)
    consent_source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    export_destination: Mapped[str] = mapped_column(String(64), nullable=False,
                                                    default="local")
    export_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    export_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    exported_at: Mapped[object | None] = mapped_column(TZDateTime, nullable=True)

    # ── Export identity (TR-SL-01) ──────────────────────────────────────────
    # Prospect 360 reads `(tenant, source_system, external_correlation_id)` as
    # the identity of a deposit. It must therefore be minted ONCE, persisted
    # BEFORE the first attempt, and never regenerated — not on timeout, not on
    # restart, not on a lost response. Regenerating it would turn a retry into a
    # second prospect, which is the exact failure exactly-once exists to stop.
    external_correlation_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True)

    # The canonical payload, frozen at the moment the identity is minted. A
    # retry replays THIS, never a payload rebuilt from a row that may have moved
    # since: same correlation with a different payload is a 409, not a replay.
    export_payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)

    # What Prospect 360 called the prospect. Written on 201 CREATED and on
    # 200 REPLAY alike — a replay returns the ORIGINAL id, which is what makes
    # the crash-after-success window recoverable.
    remote_prospect_id: Mapped[str | None] = mapped_column(String(64),
                                                           nullable=True)

    created_at = created_column()
    updated_at = updated_column()

    attribution: Mapped["LeadAttribution | None"] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False)
    consents: Mapped[list["LeadConsent"]] = relationship(
        back_populates="lead", cascade="all, delete-orphan")


class LeadConsent(Base):
    """One consent case, as an event: which text, what answer, at what moment.

    `CapturedLead` carries ONE version/timestamp pair, which was honest while the
    form had one required consent and one optional boolean. It cannot represent
    the target state — N independent cases (request follow-up per channel,
    marketing, partner transfer), each with its own text version — without either
    N column triplets or a blob. So each case becomes a row.

    `granted` False is a recorded refusal, not an absence: a case the visitor was
    shown and declined is a fact with legal weight, and it is what lets a later
    export say "marketing: not consented" instead of guessing. A case the form
    never offered has no row at all — absence of evidence stays distinguishable
    from evidence of refusal.

    The legacy columns on `CapturedLead` are untouched and stay authoritative for
    export contract v1, which is armed and immutable. This table is what contract
    v2 will read; until then it is local storage only.
    """

    __tablename__ = "lead_consent"
    __table_args__ = (
        CheckConstraint(f"purpose IN ({_CONSENT_PURPOSES})",
                        name="ck_consent_purpose"),
        CheckConstraint(f"channel IS NULL OR channel IN ({_CONSENT_CHANNELS})",
                        name="ck_consent_channel"),
        # One row per case and per lead: a second answer to the same checkbox in
        # the same submission would be a bug, not a new fact.
        UniqueConstraint("captured_lead_id", "consent_key",
                         name="uq_lead_consent_case"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    captured_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("captured_lead.id", ondelete="CASCADE"),
        nullable=False)

    # The form field key (`consent_processing`, `consent_marketing`, …). This is
    # the join back to the site configuration that defined the case.
    consent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    # NULL means the consent text names no channel. Never defaulted.
    channel: Mapped[str | None] = mapped_column(String(32), nullable=True)

    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The version of the text the visitor saw, resolved from the site config at
    # capture time. Required: a consent without its text version is the exact
    # "consented — to what?" failure the split model exists to prevent.
    text_version: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[object] = mapped_column(TZDateTime, nullable=False)
    # Where the case was answered — the page path, same semantics as
    # `CapturedLead.consent_source`.
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at = created_column()

    lead: Mapped[CapturedLead] = relationship(back_populates="consents")


class LeadAttribution(Base):
    """How this lead arrived. First-party, independent of any analytics vendor."""

    __tablename__ = "lead_attribution"
    __table_args__ = (
        UniqueConstraint("captured_lead_id", name="uq_attribution_lead"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    captured_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("captured_lead.id", ondelete="CASCADE"),
        nullable=False)

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    vertical_code: Mapped[str] = mapped_column(String(64), nullable=False)
    published_content_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType, ForeignKey("published_content.id", ondelete="SET NULL"),
        nullable=True)

    landing_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    search_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    keyword_cluster: Mapped[str | None] = mapped_column(String(255), nullable=True)

    channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    utm_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(255), nullable=True)

    cta: Mapped[str | None] = mapped_column(String(128), nullable=True)
    conversion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at = created_column()

    lead: Mapped[CapturedLead] = relationship(back_populates="attribution")


class SiteEvent(Base):
    """One funnel event. No cross-site identity, no behavioural profile.

    `session_id` is generated client-side per browsing session and is not a user
    identifier: it exists so a form abandonment can be told apart from six
    separate visitors, and it is not joined to anything outside this table.
    """

    __tablename__ = "site_event"
    __table_args__ = (
        CheckConstraint(f"event_type IN ({_EVENT_TYPES})", name="ck_event_type"),
        Index("ix_event_site_time", "site_id", "created_at"),
        Index("ix_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = pk_column()
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    page_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(8), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Bounded, non-personal detail: which CTA, which form step. Validated against
    # an allowlist before it reaches here.
    detail: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at = created_column()
