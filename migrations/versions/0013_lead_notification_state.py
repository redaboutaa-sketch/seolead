"""Record the operator notification on the lead row itself.

« Aucun lead ne doit rester oublié » needs a queryable state, not a grep of
container logs. Two nullable columns on `captured_lead`:

- `notification_state` — SENT (the SMTP relay accepted the message — not a
  claim that anyone read it), FAILED, NO_TRANSPORT (SMTP unconfigured),
  NO_DESTINATION (no lead_destination_email in the site config). NULL for
  rows that predate this column: they made no record, and backfilling a
  state nobody observed would be invention.
- `notified_at` — when the state was recorded.

`seolead leads report` reads these to surface every lead whose notification
did not go out.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_lead_notification_state"
down_revision: Union[str, None] = "0012_contract_promise_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("captured_lead",
                  sa.Column("notification_state", sa.String(32), nullable=True))
    op.add_column("captured_lead",
                  sa.Column("notified_at", sa.DateTime(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("captured_lead", "notified_at")
    op.drop_column("captured_lead", "notification_state")
