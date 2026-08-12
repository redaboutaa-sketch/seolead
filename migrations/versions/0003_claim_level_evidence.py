"""Phase 3.1 — claim-level evidence model.

Additive. `research_evidence` becomes a row per **atomic claim** rather than per
page excerpt, and `evidence_passage` carries the many-to-many link between a claim
and the passages supporting it.

Every new column is nullable, so Phase 2 and Phase 3 rows remain valid and
readable. A V2 evidence row simply has no `claim_category` and no
`evidence_status`, which is how a reader tells which model produced it.

The one structural point worth stating: `evidence_status` is a **separate column**
from `observability`. Phase 3 coupled factual support to publication metadata —
`supported` required `OBSERVED`, Tavily returns no dates, and the web-research path
therefore produced zero usable evidence for any query. Two columns, two questions.

Revision ID: 0003_claims
Revises: 0002_search
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_claims"
down_revision: Union[str, None] = "0002_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVIDENCE_STATUSES = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED",
                     "CONFLICTING")
CLAIM_CATEGORIES = ("SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
                    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE", "MARKET_PRICE",
                    "VENDOR_PRICE", "PRODUCT_SPEC", "GENERAL")
AUTHORITY = ("OFFICIAL", "INSTITUTIONAL", "SPECIALIST", "ANY")
FRESHNESS = ("REQUIRED", "PREFERRED", "NOT_REQUIRED")


def _in(column: str, values: Sequence[str]) -> str:
    joined = ", ".join(repr(v) for v in values)
    return f"{column} IS NULL OR {column} IN ({joined})"


def upgrade() -> None:
    # ── research_evidence becomes an atomic claim ────────────────────────────
    for column in (
        sa.Column("passage", sa.Text(), nullable=True),
        sa.Column("claim_category", sa.String(32), nullable=True),
        sa.Column("evidence_status", sa.String(24), nullable=True),
        sa.Column("authority_requirement", sa.String(16), nullable=True),
        sa.Column("freshness_requirement", sa.String(16), nullable=True),
        sa.Column("corroborating_sources", sa.Integer(), nullable=True),
        sa.Column("extraction_method", sa.String(32), nullable=True),
        sa.Column("evaluation_reason", sa.Text(), nullable=True),
    ):
        op.add_column("research_evidence", column)

    op.create_check_constraint(
        "ck_research_evidence_status", "research_evidence",
        _in("evidence_status", EVIDENCE_STATUSES))
    op.create_check_constraint(
        "ck_research_evidence_category", "research_evidence",
        _in("claim_category", CLAIM_CATEGORIES))
    op.create_check_constraint(
        "ck_research_evidence_authority", "research_evidence",
        _in("authority_requirement", AUTHORITY))
    op.create_check_constraint(
        "ck_research_evidence_freshness", "research_evidence",
        _in("freshness_requirement", FRESHNESS))

    # ── claim ↔ passage, many-to-many ───────────────────────────────────────
    op.create_table(
        "evidence_passage",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("research_evidence_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("research_evidence.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("research_source_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("research_source.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("passage", sa.Text(), nullable=False),
        sa.Column("supports", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        # Nullable on purpose: NULL means "the claim carries no figure", which is
        # a different fact from "states a different figure" — and that difference
        # is what makes CONFLICTING detectable at all.
        sa.Column("agrees_numerically", sa.Boolean(), nullable=True),
        sa.Column("observation_status", sa.String(16), nullable=True),
        sa.Column("source_quality", sa.String(16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "observation_status IS NULL OR observation_status IN "
            "('OBSERVED', 'ESTIMATED', 'UNKNOWN')",
            name="ck_evidence_passage_observation"),
    )
    op.create_index("ix_evidence_passage_evidence", "evidence_passage",
                    ["research_evidence_id"])
    op.create_index("ix_evidence_passage_source", "evidence_passage",
                    ["research_source_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_passage_source", table_name="evidence_passage")
    op.drop_index("ix_evidence_passage_evidence", table_name="evidence_passage")
    op.drop_table("evidence_passage")

    for name in ("ck_research_evidence_freshness", "ck_research_evidence_authority",
                 "ck_research_evidence_category", "ck_research_evidence_status"):
        op.drop_constraint(name, "research_evidence", type_="check")

    for name in ("evaluation_reason", "extraction_method", "corroborating_sources",
                 "freshness_requirement", "authority_requirement",
                 "evidence_status", "claim_category", "passage"):
        op.drop_column("research_evidence", name)
