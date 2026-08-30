"""Repair `ck_research_evidence_category` — four categories the code emits.

WHAT BROKE, AND WHERE IT HID
============================
Migration 0003 spelled the claim-category allowlist out as a literal tuple of
twelve values. Phases 3.2 and 3.3 then added `TARIFF` and `GRID_FEE`, and Phase
3.4 added `MARKET_AVERAGE` and `OBSERVED_PRICE_RANGE` — each to
`ClaimCategory`, none to this CHECK. The classifier has been able to produce
four values the database refuses ever since.

It stayed invisible for two independent reasons, and both are worth naming:

1. the four CHECKs of 0003 exist ONLY in the migration. `ResearchEvidence`
   declared just `observability`, and the test suite builds its schema with
   `Base.metadata.create_all` — so no test database ever had this constraint,
   and no test could have caught the drift;
2. the v2 pipeline could not reach evidence persistence in the deployed
   environment, because DataForSEO refused every SERP call with `40104`
   (account unverified). Verifying that account is what exposed this.

It surfaced as an `IntegrityError` mid-flush on a live run classifying
« Comptez entre 1€ et 1,2€ par watt crête installé. » as
`OBSERVED_PRICE_RANGE`.

THE LIST IS SPELLED OUT, DELIBERATELY
=====================================
This migration does not import `ClaimCategory`. A migration must mean the same
thing when replayed in a year as it did the day it was written, and one that
followed a live enum would silently change meaning under replay. The guard
against a third drift is a TEST comparing the enum to this literal — plus the
same constraints now declared on the model, so the test schema enforces what
PostgreSQL enforces.

Revision ID: 0009_claim_category_check
Revises: 0008_lead_consent
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009_claim_category_check"
down_revision: Union[str, None] = "0008_lead_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# `ClaimCategory` as of 2026-08-30, in declaration order. The four after
# ENERGY_PRICE are the ones 0003 never carried.
CLAIM_CATEGORIES: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE",
    "TARIFF", "GRID_FEE", "MARKET_AVERAGE", "OBSERVED_PRICE_RANGE",
    "MARKET_PRICE", "VENDOR_PRICE", "PRODUCT_SPEC", "GENERAL",
)

# 0003's list, kept so the downgrade restores exactly what was there — not an
# approximation of it.
CLAIM_CATEGORIES_0003: tuple[str, ...] = (
    "SUBSIDY", "TAX", "REGULATION", "GRID_RULE", "ELIGIBILITY",
    "GUARANTEED_SAVINGS", "ROI", "ENERGY_PRICE", "MARKET_PRICE",
    "VENDOR_PRICE", "PRODUCT_SPEC", "GENERAL",
)

_NAME = "ck_research_evidence_category"
_TABLE = "research_evidence"


def _condition(values: Sequence[str]) -> str:
    joined = ", ".join(repr(v) for v in values)
    return f"claim_category IS NULL OR claim_category IN ({joined})"


def _replace(values: Sequence[str]) -> None:
    # A CHECK cannot be altered in place; dropping and recreating is the only
    # route. Widening an allowlist can never invalidate a stored row, so no data
    # is at risk in the upgrade direction.
    op.drop_constraint(_NAME, _TABLE, type_="check")
    op.create_check_constraint(_NAME, _TABLE, _condition(values))


def upgrade() -> None:
    _replace(CLAIM_CATEGORIES)


def downgrade() -> None:
    """NARROWS the allowlist back to 0003's twelve values.

    Rows already written with one of the four restored categories would violate
    it, so PostgreSQL refuses the constraint rather than dropping the rows —
    which is the correct outcome: losing evidence to a downgrade would be worse
    than a failed downgrade. Delete or reclassify those rows first if this must
    proceed.
    """
    _replace(CLAIM_CATEGORIES_0003)
