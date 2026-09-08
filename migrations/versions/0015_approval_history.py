"""`approval.history` — re-approving a page must not erase who approved it.

The gate of 2026-09-03 refuses to publish a draft whose approval names no
render fingerprint, and tells the operator to re-approve with one. On
2026-09-08 that instruction turned out to be unreachable: `APPROVED` was a
fully terminal approval state, so a page approved before the fingerprint rule
existed — `/prix-panneaux-solaires-belgique`, approved and published during the
soft launch — could never be republished, and its `noindex` could never be
lifted.

Re-approval is now legal, and it overwrites the decision fields in place
because the table holds exactly one row per draft (`uq_approval_draft`, the
guard that stops a rejection being overwritten by an inserted approval). This
column keeps what the overwrite would otherwise destroy: one entry per
superseded decision, appended in order, each carrying the state, the actor,
the instant, the note and the render fingerprint it named.

Not nullable, default empty list: an approval that has never been superseded
has an empty history, which is a fact, not a gap.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_approval_history"
down_revision: Union[str, None] = "0014_fingerprint_resolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("approval",
                  sa.Column("history", sa.JSON(), nullable=False,
                            server_default="[]"))


def downgrade() -> None:
    op.drop_column("approval", "history")
