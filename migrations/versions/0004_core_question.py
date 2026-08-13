"""Phase 3.4 — the core question a brief must answer.

Additive and nullable, so every Phase 3.3 brief remains readable: an older row
simply has no `core_question`, which is how a reader tells it predates the rule.

`core_answer_status` is stored next to the question rather than derived at read
time on purpose. "Was the core question answerable when this page was written?"
is a fact about that run's evidence, and re-deriving it later against a changed
evidence set would silently rewrite history.

Revision ID: 0004_core_q
Revises: 0003_claims
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_core_q"
down_revision: Union[str, None] = "0003_claims"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("content_brief",
                  sa.Column("core_question", sa.Text(), nullable=True))
    op.add_column("content_brief",
                  sa.Column("core_answer_status", sa.String(32), nullable=True))
    op.add_column("content_brief",
                  sa.Column("core_answer_evidence", sa.JSON(), nullable=False,
                            server_default="{}"))
    op.add_column("content_brief",
                  sa.Column("must_answer_directly", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("content_brief", "must_answer_directly")
    op.drop_column("content_brief", "core_answer_evidence")
    op.drop_column("content_brief", "core_answer_status")
    op.drop_column("content_brief", "core_question")
