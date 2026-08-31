"""Extend `ck_research_evidence_category` with CONTRACT_PROMISE.

Same discipline as 0011: the enum gains a value in code, the CHECK lives only
in migrations, and the two ship in the same change so the first live claim
classified CONTRACT_PROMISE is not refused by PostgreSQL at persistence time.

Why the category exists: measured on 2026-08-31 for the SG Solution model,
« Le tarif est garanti à 0,27 €/kWh pendant 25 ans » classified
MARKET_PRICE / MEDIUM and « Votre facture ne pourra plus augmenter »
GENERAL / LOW. Contract-terms promises now classify CONTRACT_PROMISE / HIGH /
OFFICIAL — unassertable from research on purpose: the only path onto a page
is the offer registry with contract evidence and a legal verdict on wording.
The category is deliberately NOT a financing category: the contract's legal
nature (credit, PPA, lease…) is unqualified and remains the lawyer's question.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_contract_promise_category"
down_revision: Union[str, None] = "0011_financing_promise_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLAIM_CATEGORIES: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE",
    "TARIFF", "GRID_FEE", "MARKET_AVERAGE", "OBSERVED_PRICE_RANGE",
    "MARKET_PRICE", "VENDOR_PRICE", "PRODUCT_SPEC", "FINANCING_PROMISE",
    "CONTRACT_PROMISE", "GENERAL",
)

# 0011's list, restored exactly on downgrade.
CLAIM_CATEGORIES_0011: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE",
    "TARIFF", "GRID_FEE", "MARKET_AVERAGE", "OBSERVED_PRICE_RANGE",
    "MARKET_PRICE", "VENDOR_PRICE", "PRODUCT_SPEC", "FINANCING_PROMISE",
    "GENERAL",
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
    """Narrows back to 0011's values. Rows already classified CONTRACT_PROMISE
    would violate the restored constraint, so PostgreSQL refuses rather than
    dropping them — reclassify or delete those rows first if this must
    proceed."""
    _replace(CLAIM_CATEGORIES_0011)
