"""Extend `ck_research_evidence_category` with FINANCING_PROMISE.

The lesson of 0009, applied instead of relearned: `ClaimCategory` gained a
value in code, and the CHECK constraint lives only in migrations — the test
schema is built by `create_all`, so no test can catch the drift, and the first
live claim classified FINANCING_PROMISE would have been refused by PostgreSQL
at persistence time. The category ships in the same change as its migration.

Why the category exists: measured on 2026-08-31, « Panneaux solaires gratuits :
vous ne payez rien » classified GENERAL / LOW / ANY. Financing-offer promises
now classify FINANCING_PROMISE / HIGH / OFFICIAL — unassertable from research
on purpose, because the only legitimate source of an offer is the validated
first-party offer registry.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_financing_promise_category"
down_revision: Union[str, None] = "0010_qa_review_revision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLAIM_CATEGORIES: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE",
    "TARIFF", "GRID_FEE", "MARKET_AVERAGE", "OBSERVED_PRICE_RANGE",
    "MARKET_PRICE", "VENDOR_PRICE", "PRODUCT_SPEC", "FINANCING_PROMISE",
    "GENERAL",
)

# 0009's list, restored exactly on downgrade.
CLAIM_CATEGORIES_0009: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE",
    "TARIFF", "GRID_FEE", "MARKET_AVERAGE", "OBSERVED_PRICE_RANGE",
    "MARKET_PRICE", "VENDOR_PRICE", "PRODUCT_SPEC", "GENERAL",
)

_NAME = "ck_research_evidence_category"
_TABLE = "research_evidence"


def _condition(values: Sequence[str]) -> str:
    joined = ", ".join(repr(v) for v in values)
    return f"claim_category IS NULL OR claim_category IN ({joined})"


def _replace(values: Sequence[str]) -> None:
    op.drop_constraint(_NAME, _TABLE, type_="check")
    op.create_check_constraint(_NAME, _TABLE, _condition(values))


def upgrade() -> None:
    _replace(CLAIM_CATEGORIES)


def downgrade() -> None:
    """Narrows back to 0009's values. Rows already classified FINANCING_PROMISE
    would violate the restored constraint, so PostgreSQL refuses rather than
    dropping them — reclassify or delete those rows first if this must proceed."""
    _replace(CLAIM_CATEGORIES_0009)
