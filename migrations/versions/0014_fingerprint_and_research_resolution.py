"""Two columns the tranche structurelle of 2026-09-03 needs.

`approval.render_fingerprint` — an approval names the render it approved.
The article 8a1f6e46 was approved on an intention (« rev 2 APPROVED ») and
published with a payback figure no source carried; the gate now refuses an
approval that does not name, by SHA-256 of the rendered content, exactly what
the owner read. Nullable: rows written before this column approved nothing
identifiable, and the gate treats them as such rather than inventing a
fingerprint after the fact.

`research_package.authoritative_research` — what the planner proposed and
what became of each proposal. The package f9534a41 proposed 5 targeted
authoritative searches to resolve HIGH-risk gaps; they were never run, and
nothing recorded that. The gate now refuses publication while a proposed
search is neither executed nor explicitly abandoned with a reason. Nullable:
packages built before this column carry their proposals only in a narrative
note, and the gate recomputes the plan from their facts.

`published_content.sources` — the sources behind the figures a page shows,
frozen with the page. The « méthode » block promised « chaque montant
affiché provient d'une source publiée » on pages that showed no source;
now the page lists them. Nullable: earlier snapshots listed none.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_fingerprint_resolution"
down_revision: Union[str, None] = "0013_lead_notification_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("approval",
                  sa.Column("render_fingerprint", sa.String(64), nullable=True))
    op.add_column("research_package",
                  sa.Column("authoritative_research", sa.JSON(), nullable=True))
    op.add_column("published_content",
                  sa.Column("sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("published_content", "sources")
    op.drop_column("research_package", "authoritative_research")
    op.drop_column("approval", "render_fingerprint")
