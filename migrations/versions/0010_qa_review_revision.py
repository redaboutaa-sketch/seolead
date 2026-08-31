"""Versioned QA verdicts — a verdict is added, never corrected.

WHAT THIS EXISTS FOR
====================
On 2026-08-30 draft `8a1f6e46` was judged and refused: five blocking findings,
four of them `HIGH_RISK_CLAIM_ASSERTED`. The matcher that produced them was then
found to blame a sentence for the claim it merely resembled, and was fixed. The
same draft, the same research, the same words, now passes.

The row saying it failed is not thereby wrong. Under the matcher of that day it
did fail, and that is a fact with a date on it. Editing it in place would
destroy the only evidence that the matcher ever misattributed anything, and
would leave the trail asserting something that was never true — that this draft
always passed. So a re-judgement appends a row and the earlier ones stay
readable for good.

WHAT IT ADDS
============
    revision        which verdict of this layer this is. 1 for everything that
                    already exists; the publication gate reads the highest.
    engine_version  what judged it. Carries the matcher's margin, so a
                    re-judgement under a different setting is visibly a
                    different engine rather than an unexplained reversal.
    verdict_reason  why it was judged again. Empty on a verdict from a pipeline
                    run, which needs no reason beyond having been the first.

Additive in the strict sense: three nullable-or-defaulted columns on one table,
no constraint changed, no row rewritten. Every existing verdict keeps its
meaning and becomes revision 1 of its layer.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_qa_review_revision"
down_revision: Union[str, None] = "0009_claim_category_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "qa_review"


def upgrade() -> None:
    # `server_default` and not just a Python default: existing rows are
    # back-filled by the database, and `revision` can be NOT NULL from the
    # start rather than nullable-then-tightened in a second migration.
    op.add_column(_TABLE, sa.Column("revision", sa.Integer(), nullable=False,
                                    server_default="1"))
    op.add_column(_TABLE, sa.Column("engine_version", sa.String(64),
                                    nullable=True))
    op.add_column(_TABLE, sa.Column("verdict_reason", sa.Text(), nullable=True))
    # The gate asks one question of this table — the newest verdict for a
    # draft's layer — and asks it on every publication attempt.
    op.create_index("ix_qa_review_draft_layer_revision", _TABLE,
                    ["content_draft_id", "layer", "revision"])


def downgrade() -> None:
    """Drops the columns, and with them the ability to tell verdicts apart.

    Safe in the schema sense and lossy in the honest one: after this, a draft
    carrying two verdicts for one layer has no ordering between them, and
    `evaluate_gate` falls back to requiring ALL of them to pass — which means a
    superseded refusal governs publication again. That is the conservative
    direction, and it is why nothing is deleted here beyond the columns.
    """
    op.drop_index("ix_qa_review_draft_layer_revision", table_name=_TABLE)
    op.drop_column(_TABLE, "verdict_reason")
    op.drop_column(_TABLE, "engine_version")
    op.drop_column(_TABLE, "revision")
