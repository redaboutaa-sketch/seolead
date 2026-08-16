"""Export identity for captured leads — TR-SL-01.

Three columns, and each one exists to stop a specific failure.

`external_correlation_id` is the identity Prospect 360 reads, together with the
tenant and `source_system`. It is UNIQUE here because the whole exactly-once
story rests on it being minted once per lead: a duplicate would mean two local
leads claiming the same remote deposit.

`export_payload` freezes the canonical body at the moment that identity is
minted. Prospect 360 answers `200 REPLAY` to the same correlation with the same
fingerprint, and `409 CONFLICT` to the same correlation with a different one —
so a retry that rebuilt the body from a row edited since would be refused, and
rightly.

`remote_prospect_id` records what came back, on `201` and on `200` alike.

Nullable on purpose: leads captured before this migration have no export
identity, and inventing one for them retroactively would claim a deposit that
never happened. They acquire it when the exporter first considers them.

Revision ID: 0007_lead_export
Revises: 0006_qa_layer
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_lead_export"
down_revision: Union[str, None] = "0006_qa_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("captured_lead",
                  sa.Column("external_correlation_id", sa.String(128),
                            nullable=True))
    op.add_column("captured_lead",
                  sa.Column("export_payload", sa.JSON(), nullable=True))
    op.add_column("captured_lead",
                  sa.Column("remote_prospect_id", sa.String(64), nullable=True))
    # UNIQUE, not just indexed. Two leads sharing a correlation would make one
    # of them silently adopt the other's remote prospect on replay.
    op.create_unique_constraint("uq_lead_external_correlation", "captured_lead",
                                ["external_correlation_id"])


def downgrade() -> None:
    op.drop_constraint("uq_lead_external_correlation", "captured_lead",
                       type_="unique")
    op.drop_column("captured_lead", "remote_prospect_id")
    op.drop_column("captured_lead", "export_payload")
    op.drop_column("captured_lead", "external_correlation_id")
