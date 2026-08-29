"""Per-case consent storage — one row per checkbox, with its own text version.

`captured_lead` records consent as one version/timestamp pair plus one marketing
boolean. That was honest for a form with exactly two cases sharing one text
version, and it cannot hold the target state: N independent cases (request
follow-up per channel, marketing, partner transfer), each with its own state,
its own text version and its own instant.

This table is ADDITIVE. The legacy columns on `captured_lead` are not touched,
because export contract v1 is armed and immutable and reads them; a v2 contract
reads this table. Nothing is backfilled: a lead captured before this migration
answered the cases its form offered, and inventing per-case rows for it would
assert answers to questions that were never asked.

`granted` False is a stored refusal — a case shown and declined — and is
distinct from the absence of a row, which means the case was never offered.

Revision ID: 0008_lead_consent
Revises: 0007_lead_export
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_lead_consent"
down_revision: Union[str, None] = "0007_lead_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PURPOSES = "'PROCESSING', 'FOLLOWUP_CONTACT', 'MARKETING', 'PARTNER_TRANSFER'"
_CHANNELS = "'PHONE', 'WHATSAPP', 'EMAIL', 'SMS'"


def upgrade() -> None:
    op.create_table(
        "lead_consent",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("captured_lead_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("captured_lead.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("consent_key", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(32), nullable=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("text_version", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(f"purpose IN ({_PURPOSES})",
                           name="ck_consent_purpose"),
        sa.CheckConstraint(f"channel IS NULL OR channel IN ({_CHANNELS})",
                           name="ck_consent_channel"),
        sa.UniqueConstraint("captured_lead_id", "consent_key",
                            name="uq_lead_consent_case"),
    )
    # The read path is "every case for this lead"; the unique constraint above
    # already leads on `captured_lead_id`, so no separate index is needed.


def downgrade() -> None:
    op.drop_table("lead_consent")
