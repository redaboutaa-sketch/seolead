"""Phase 4 — publication boundary, leads, attribution, first-party events.

Purely additive: four new tables and no change to any existing one. The research
and content-workflow schema is untouched, so a rollback removes the site without
touching anything the factory depends on.

The partial unique index on published content is the important object here. It
permits many versions of a slug to exist while allowing only one to be PUBLISHED,
which is what makes "publish version 3" a safe operation rather than a race
between two live rows. SQLite (the test database) supports partial indexes too, so
the constraint is exercised by the suite rather than only in production.

Revision ID: 0005_site
Revises: 0004_core_q
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_site"
down_revision: Union[str, None] = "0004_core_q"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUBLICATION_STATES = ("DRAFT", "QA_FAILED", "PENDING_APPROVAL", "APPROVED",
                       "STAGED", "PUBLISHED", "ARCHIVED")
_LEAD_STATES = ("NEW", "PENDING_EXPORT", "EXPORTING", "EXPORTED",
                "EXPORT_FAILED", "REJECTED_SPAM", "ARCHIVED")
_EVENT_TYPES = ("PAGE_VIEW", "CTA_CLICK", "FORM_STARTED", "FORM_STEP_COMPLETED",
                "FORM_SUBMITTED", "LEAD_CREATED")
_CONVERSION_TYPES = ("ESTIMATE_REQUEST", "CALLBACK_REQUEST", "CONTACT",
                     "TOOL_COMPLETION")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "published_content",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("site_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("site.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_draft_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("content_draft.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("search_intent", sa.String(32), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("meta_title", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("price_evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cta", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("qa_provenance", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("canonical_path", sa.String(512), nullable=True),
        sa.Column("noindex", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("staged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(_in("state", _PUBLICATION_STATES), name="ck_pub_state"),
        sa.UniqueConstraint("site_id", "locale", "slug", "version",
                            name="uq_pub_slug_version"),
    )
    op.create_index("ix_pub_lookup", "published_content",
                    ["site_id", "locale", "slug", "state"])
    # At most one live row per address. Everything else may coexist.
    op.create_index("uq_pub_live", "published_content",
                    ["site_id", "locale", "slug"], unique=True,
                    postgresql_where=sa.text("state = 'PUBLISHED'"),
                    sqlite_where=sa.text("state = 'PUBLISHED'"))

    op.create_table(
        "captured_lead",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("site_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("site.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("vertical_code", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="NEW"),
        sa.Column("conversion_type", sa.String(32), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=True),
        sa.Column("last_name", sa.String(120), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("postcode", sa.String(16), nullable=True),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("qualification", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("consent_marketing", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("consent_version", sa.String(32), nullable=True),
        sa.Column("consent_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_source", sa.String(255), nullable=True),
        sa.Column("export_destination", sa.String(64), nullable=False,
                  server_default="local"),
        sa.Column("export_attempts", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("export_error", sa.Text(), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(_in("state", _LEAD_STATES), name="ck_lead_state"),
        sa.CheckConstraint(_in("conversion_type", _CONVERSION_TYPES),
                           name="ck_lead_conversion"),
    )
    op.create_index("ix_lead_state", "captured_lead", ["state", "created_at"])
    op.create_index("ix_lead_site", "captured_lead", ["site_id"])

    op.create_table(
        "lead_attribution",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("captured_lead_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("captured_lead.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("site_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("site.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vertical_code", sa.String(64), nullable=False),
        sa.Column("published_content_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("published_content.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("landing_path", sa.String(512), nullable=True),
        sa.Column("page_path", sa.String(512), nullable=True),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("search_intent", sa.String(32), nullable=True),
        sa.Column("keyword_cluster", sa.String(255), nullable=True),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("referrer", sa.String(1024), nullable=True),
        sa.Column("utm_source", sa.String(255), nullable=True),
        sa.Column("utm_medium", sa.String(255), nullable=True),
        sa.Column("utm_campaign", sa.String(255), nullable=True),
        sa.Column("utm_content", sa.String(255), nullable=True),
        sa.Column("utm_term", sa.String(255), nullable=True),
        sa.Column("cta", sa.String(128), nullable=True),
        sa.Column("conversion_type", sa.String(32), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("captured_lead_id", name="uq_attribution_lead"),
    )

    op.create_table(
        "site_event",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("site_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("site.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("page_path", sa.String(512), nullable=True),
        sa.Column("locale", sa.String(8), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(_in("event_type", _EVENT_TYPES), name="ck_event_type"),
    )
    op.create_index("ix_event_site_time", "site_event", ["site_id", "created_at"])
    op.create_index("ix_event_type", "site_event", ["event_type"])


def downgrade() -> None:
    op.drop_table("site_event")
    op.drop_table("lead_attribution")
    op.drop_table("captured_lead")
    op.drop_index("uq_pub_live", table_name="published_content")
    op.drop_table("published_content")
