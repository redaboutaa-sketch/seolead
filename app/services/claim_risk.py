"""Claim risk — how much damage a wrong claim would do.

Not all sentences are equally dangerous. "Panels are usually mounted on the south
face" being slightly off is a quality problem. "The regional premium is €1,750"
being wrong is a legal and reputational one, and it is the sort of thing a
plausible-sounding model produces effortlessly.

So claims are classified by consequence, and the evidence bar rises with it:

    HIGH    → requires an OFFICIAL or INSTITUTIONAL source
    MEDIUM  → requires SPECIALIST or better
    LOW     → any relevant source

The HIGH categories are drawn from the vertical's `restricted_claims`, so this
carries no solar-specific knowledge: the AI Training vertical's funded-eligibility
rules get the same treatment from its own profile.
"""
from __future__ import annotations

import re
from enum import StrEnum

from app.services.intent import normalize_query
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile


class ClaimRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def minimum_source_quality(self) -> SourceQuality:
        return {
            ClaimRisk.HIGH: SourceQuality.INSTITUTIONAL,
            ClaimRisk.MEDIUM: SourceQuality.SPECIALIST,
            ClaimRisk.LOW: SourceQuality.COMMUNITY,
        }[self]


class SupportStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTING = "CONFLICTING"


# Cross-vertical high-risk vocabulary. Anything legal, fiscal or guaranteed.
_UNIVERSAL_HIGH_RISK = (
    "loi", "légal", "legal", "obligation", "obligatoire", "réglementation",
    "regulation", "wettelijk", "verplicht",
    "taxe", "impôt", "tva", "btw", "tax", "belasting",
    "garanti", "garantie", "guaranteed", "gegarandeerd",
    "subvention", "subside", "prime", "premie", "subsidie", "subsidy", "grant",
    "remboursement", "refund", "terugbetaling",
)

# Numbers with a unit or a currency: the shape of a claim worth checking.
_QUANTIFIED = re.compile(
    r"(?<![\w/])\d[\d\s.,]*\s*(?:%|€|\$|£|eur|euros?|kwh|kwc|kwp|wc|wp|m²|m2|ans?|jaar|years?)",
    re.IGNORECASE,
)


def classify_claim(claim: str, profile: VerticalProfile) -> ClaimRisk:
    """Classify one claim by consequence-if-wrong."""
    normalized = normalize_query(claim)

    for term in profile.restricted_claims:
        if normalize_query(term) in normalized:
            return ClaimRisk.HIGH
    for term in _UNIVERSAL_HIGH_RISK:
        if normalize_query(term) in normalized:
            return ClaimRisk.HIGH

    # A quantified claim with no restricted topic is still a number a reader may
    # act on — mid risk, needing a specialist source at least.
    if _QUANTIFIED.search(claim):
        return ClaimRisk.MEDIUM

    return ClaimRisk.LOW


def evidence_is_sufficient(risk: ClaimRisk, quality: SourceQuality) -> bool:
    return quality.rank >= risk.minimum_source_quality.rank


def assess(claim: str, profile: VerticalProfile,
           quality: SourceQuality) -> tuple[ClaimRisk, bool, str]:
    """Return (risk, sufficient, reason)."""
    risk = classify_claim(claim, profile)
    sufficient = evidence_is_sufficient(risk, quality)
    if sufficient:
        reason = (f"{risk.value}-risk claim supported by a {quality.value} source "
                  f"(minimum {risk.minimum_source_quality.value}).")
    else:
        reason = (f"{risk.value}-risk claim needs at least a "
                  f"{risk.minimum_source_quality.value} source; this one is "
                  f"{quality.value}.")
    return risk, sufficient, reason


def summarize(risks: list[ClaimRisk]) -> dict:
    counts: dict[str, int] = {}
    for risk in risks:
        counts[risk.value] = counts.get(risk.value, 0) + 1
    return {"counts": counts, "high_risk_count": counts.get(ClaimRisk.HIGH.value, 0)}
