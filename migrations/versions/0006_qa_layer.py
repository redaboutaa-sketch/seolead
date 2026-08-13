"""Phase 4 — record WHAT a QA review examined, not only how it was made.

`qa_type` says deterministic or model-assisted. It does not say factual or SEO,
and the publication gate needs both to have passed. Phase 4 first inferred that
from finding codes and the inference failed exactly where it mattered: a review
that passes cleanly has no codes to infer from, so two clean reviews both looked
factual and the gate reported "no SEO QA review is recorded" for a draft that had
one.

Nullable, so every pre-Phase-4 row stays readable; the gate falls back to the old
code-based inference for rows that carry no layer.

Revision ID: 0006_qa_layer
Revises: 0005_site
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_qa_layer"
down_revision: Union[str, None] = "0005_site"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LAYERS = ("FACTUAL", "SEO", "ADVISORY")


def upgrade() -> None:
    op.add_column("qa_review", sa.Column("layer", sa.String(16), nullable=True))
    op.create_check_constraint(
        "ck_qa_layer", "qa_review",
        f"layer IS NULL OR layer IN ({', '.join(repr(v) for v in _LAYERS)})")
    # Backfill what can be known without guessing: an LLM-assisted review is
    # advisory by definition. Deterministic rows are left NULL rather than
    # assigned a layer nobody recorded.
    op.execute("UPDATE qa_review SET layer = 'ADVISORY' "
               "WHERE qa_type = 'LLM_ASSISTED'")


def downgrade() -> None:
    op.drop_constraint("ck_qa_layer", "qa_review", type_="check")
    op.drop_column("qa_review", "layer")
