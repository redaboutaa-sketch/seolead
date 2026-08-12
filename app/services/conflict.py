"""Conflict classification.

Phase 3.1's live run produced 23 CONFLICTING claims out of 121, and inspecting
them showed most were not disagreements at all. Two sources quoting different
premiums for Wallonia and Brussels agree perfectly — about different regions. A
2025 figure and a 2026 figure agree — about different years.

Collapsing all of that into "CONFLICTING" is safe in the sense that it blocks, and
useless in the sense that a reviewer cannot act on it. So a numeric disagreement is
now classified before it is treated as a conflict:

    TRUE_CONFLICT      same scope, same period — sources genuinely disagree
    REGIONAL_DIFFERENCE different regions — both may be right
    TIME_DIFFERENCE     different periods — both may be right
    SCOPE_DIFFERENCE    measuring different things (per kWc vs total)
    WORDING_VARIATION   same figure expressed differently

Only TRUE_CONFLICT blocks. The rest are recorded, and a difference that is merely
regional or temporal narrows the claim rather than refusing it.

Detection is not weakened: everything that used to be flagged is still flagged, and
now carries a reason.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.intent import normalize_query
from app.services.region import Region, detect_region


class ConflictKind(StrEnum):
    TRUE_CONFLICT = "TRUE_CONFLICT"
    REGIONAL_DIFFERENCE = "REGIONAL_DIFFERENCE"
    TIME_DIFFERENCE = "TIME_DIFFERENCE"
    SCOPE_DIFFERENCE = "SCOPE_DIFFERENCE"
    WORDING_VARIATION = "WORDING_VARIATION"

    @property
    def blocks(self) -> bool:
        """Only a genuine disagreement blocks.

        The others are real information — they say the claim needs narrowing, not
        that the evidence is untrustworthy.
        """
        return self is ConflictKind.TRUE_CONFLICT


_YEAR = re.compile(r"\b(20\d{2})\b")
# Units that mean the numbers are measuring different quantities.
_UNIT_PATTERNS: dict[str, re.Pattern[str]] = {
    "per_wp": re.compile(r"(?:par|/)\s*(?:watt[-\s]?cr[eê]te|wc|wp)\b", re.I),
    "per_kwc": re.compile(r"(?:par|/)\s*kwc\b", re.I),
    "per_kwh": re.compile(r"(?:par|/)\s*kwh\b", re.I),
    "per_m2": re.compile(r"(?:par|/)\s*m[²2]\b", re.I),
    "per_year": re.compile(r"(?:par|/)\s*an\b|/an\b", re.I),
    "percent": re.compile(r"%"),
    "total": re.compile(r"\b(?:au total|total|investissement|budget)\b", re.I),
}


@dataclass(frozen=True)
class ConflictAssessment:
    kind: ConflictKind
    reason: str
    claim_region: Region
    other_region: Region
    claim_years: list[int]
    other_years: list[int]
    claim_units: list[str]
    other_units: list[str]

    @property
    def blocks(self) -> bool:
        return self.kind.blocks

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value, "reason": self.reason, "blocks": self.blocks,
            "claim_region": self.claim_region.value,
            "other_region": self.other_region.value,
            "claim_years": self.claim_years, "other_years": self.other_years,
            "claim_units": self.claim_units, "other_units": self.other_units,
        }


def _units(text: str) -> list[str]:
    return sorted(name for name, pattern in _UNIT_PATTERNS.items()
                  if pattern.search(text))


def _years(text: str) -> list[int]:
    return sorted({int(y) for y in _YEAR.findall(text)})


def classify(claim_text: str, other_text: str, *,
             claim_region: Region | None = None,
             other_region: Region | None = None) -> ConflictAssessment:
    """Classify a numeric disagreement between a claim and a passage."""
    claim_region = claim_region or detect_region(claim_text).region
    other_region = other_region or detect_region(other_text).region

    claim_years = _years(claim_text)
    other_years = _years(other_text)
    claim_units = _units(claim_text)
    other_units = _units(other_text)

    def build(kind: ConflictKind, reason: str) -> ConflictAssessment:
        return ConflictAssessment(kind, reason, claim_region, other_region,
                                  claim_years, other_years, claim_units,
                                  other_units)

    # ── Different regions ────────────────────────────────────────────────────
    if (claim_region is not Region.UNKNOWN and other_region is not Region.UNKNOWN
            and claim_region is not other_region
            and not claim_region.covers(other_region)
            and not other_region.covers(claim_region)):
        return build(
            ConflictKind.REGIONAL_DIFFERENCE,
            f"Figures describe {claim_region.value} and {other_region.value}; "
            f"Belgian regions set their own rules, so both may be correct.")

    # ── Different measurement ────────────────────────────────────────────────
    if claim_units and other_units and not set(claim_units) & set(other_units):
        return build(
            ConflictKind.SCOPE_DIFFERENCE,
            f"Figures are measured differently ({', '.join(claim_units)} vs "
            f"{', '.join(other_units)}); they are not comparable.")

    # ── Different periods ────────────────────────────────────────────────────
    if claim_years and other_years and not set(claim_years) & set(other_years):
        return build(
            ConflictKind.TIME_DIFFERENCE,
            f"Figures describe different years ({claim_years} vs {other_years}); "
            f"a change over time is not a disagreement.")

    # ── Same figure, different words ─────────────────────────────────────────
    if normalize_query(claim_text) == normalize_query(other_text):
        return build(ConflictKind.WORDING_VARIATION,
                     "Texts are equivalent after normalisation.")

    return build(
        ConflictKind.TRUE_CONFLICT,
        "Same scope and period, and the sources state different figures.")


def summarize(assessments: list[ConflictAssessment]) -> dict:
    counts: dict[str, int] = {}
    for assessment in assessments:
        counts[assessment.kind.value] = counts.get(assessment.kind.value, 0) + 1
    return {
        "counts": counts,
        "blocking": sum(1 for a in assessments if a.blocks),
        "non_blocking": sum(1 for a in assessments if not a.blocks),
    }
