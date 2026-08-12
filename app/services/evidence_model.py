"""Claim-level evidence mapping and support classification.

This is the module that replaces Phase 3's single `supported` boolean. It answers
one question per claim — *does specific eligible material support this specific
proposition, to the standard this kind of claim demands?* — and it answers it
along four independent dimensions rather than collapsing them:

    relevance     is the source about the query?         (RelevanceGate)
    authority     is this source entitled to establish it? (SourceQuality)
    freshness     does this claim's truth depend on when?  (ObservationStatus)
    support       does a passage materially state it?      (EvidenceStatus)

The Phase 3 defect was coupling the fourth to the third: `supported` required
`OBSERVED`, Tavily never returns dates, so nothing could ever be supported. Here,
freshness only matters where the claim's own category says it does.

A claim may carry several evidence references, and one source may support several
claims. Both are needed: corroboration is how a market-wide average earns the
right to be stated, and a single good page usually supports many propositions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import (AuthorityRequirement, ClaimCategory, EvidenceStatus,
                            FreshnessRequirement, ObservationStatus)
from app.services.claim_extraction import AtomicClaim
from app.services.claim_policy import (ClaimRequirements, ClaimRisk,
                                       authority_is_sufficient, requirements_for)
from app.services.intent import normalize_query
from app.services.relevance import RelevanceStatus
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile

_NUMBER = re.compile(r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d+)")
# Overlap of distinctive words before a passage is considered to be about a claim.
_TOPIC_MATCH_MIN = 2


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _numbers(text: str) -> set[str]:
    found = {_digits(m.group(1)) for m in _NUMBER.finditer(text)}
    # Years are rarely the quantity under test and generate noise.
    return {n for n in found
            if n and not (len(n) == 4 and 1900 <= int(n) <= 2100)}


def _content_words(text: str) -> set[str]:
    return {w for w in normalize_query(text).split() if len(w) > 4}


@dataclass
class EvidenceRef:
    """One source's contribution to one claim."""

    source_ref: str
    passage: str
    url: str | None
    source_type: str
    quality: SourceQuality
    relevance: RelevanceStatus
    observation: ObservationStatus
    published_at: datetime | None
    retrieved_at: datetime | None
    provider: str
    supports: bool
    agrees_numerically: bool | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "source_ref": self.source_ref,
            "passage": self.passage[:600],
            "url": self.url,
            "source_type": self.source_type,
            "source_quality": self.quality.value,
            "relevance_status": self.relevance.value,
            "observation_status": self.observation.value,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "provider": self.provider,
            "supports": self.supports,
            "agrees_numerically": self.agrees_numerically,
            "note": self.note,
        }


@dataclass
class EvaluatedClaim:
    """An atomic claim with its evidence and its verdict."""

    claim: AtomicClaim
    requirements: ClaimRequirements
    evidence: list[EvidenceRef] = field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.UNSUPPORTED
    reason: str = ""

    @property
    def corroborating_sources(self) -> int:
        return len({e.source_ref for e in self.evidence if e.supports})

    @property
    def best_quality(self) -> SourceQuality:
        supporting = [e.quality for e in self.evidence if e.supports]
        return max(supporting, key=lambda q: q.rank) if supporting else SourceQuality.UNKNOWN

    @property
    def has_dated_support(self) -> bool:
        return any(e.supports and e.published_at is not None for e in self.evidence)

    def as_dict(self) -> dict:
        return {
            "claim": self.claim.text,
            "passage": self.claim.passage[:600],
            "source_ref": self.claim.source_ref,
            "extraction_method": self.claim.extraction_method,
            "quantified": self.claim.quantified,
            "category": self.requirements.category.value,
            "claim_risk": self.requirements.risk,
            "authority_requirement": self.requirements.authority.value,
            "freshness_requirement": self.requirements.freshness.value,
            "min_corroborating_sources": self.requirements.min_corroborating_sources,
            "evidence_status": self.status.value,
            "reason": self.reason,
            "corroborating_sources": self.corroborating_sources,
            "best_source_quality": self.best_quality.value,
            "has_dated_support": self.has_dated_support,
            "evidence": [e.as_dict() for e in self.evidence],
            # Kept so Phase 2/3 consumers that read `supported` keep working.
            "supported": self.status is EvidenceStatus.SUPPORTED,
        }


def passage_supports_claim(claim_text: str, passage: str) -> tuple[bool, bool | None]:
    """Does this passage materially state this claim?

    Returns (supports, agrees_numerically). `agrees_numerically` is None when the
    claim carries no figure — a distinction that matters, because a passage that
    is on-topic but silent about the number is not the same as one that states a
    different number.
    """
    claim_words = _content_words(claim_text)
    passage_words = _content_words(passage)
    if len(claim_words & passage_words) < _TOPIC_MATCH_MIN:
        return False, None

    claim_numbers = _numbers(claim_text)
    if not claim_numbers:
        return True, None

    passage_numbers = _numbers(passage)
    if claim_numbers & passage_numbers:
        return True, True
    # On-topic and quantified, but the figure is absent or different.
    return False, False


def evaluate_claim(
    claim: AtomicClaim,
    candidates: list[EvidenceRef],
    profile: VerticalProfile,
) -> EvaluatedClaim:
    """Classify one claim against its candidate evidence."""
    requirements = requirements_for(claim.text, profile)
    evaluated = EvaluatedClaim(claim=claim, requirements=requirements,
                               evidence=candidates)

    supporting = [e for e in candidates if e.supports]
    disagreeing = [e for e in candidates
                   if not e.supports and e.agrees_numerically is False]

    # ── Nothing states it ────────────────────────────────────────────────────
    if not supporting:
        if disagreeing:
            evaluated.status = EvidenceStatus.CONFLICTING
            evaluated.reason = (
                f"{len(disagreeing)} eligible source(s) discuss this and none "
                f"states the figure claimed.")
        else:
            evaluated.status = EvidenceStatus.UNSUPPORTED
            evaluated.reason = "No eligible passage materially states this claim."
        return evaluated

    # ── Contradiction among supporters ───────────────────────────────────────
    if supporting and disagreeing:
        evaluated.status = EvidenceStatus.CONFLICTING
        evaluated.reason = (
            f"{len(supporting)} source(s) support this figure and "
            f"{len(disagreeing)} state a different one.")
        return evaluated

    # ── Authority ────────────────────────────────────────────────────────────
    best = evaluated.best_quality
    if not authority_is_sufficient(requirements.authority, best):
        evaluated.status = EvidenceStatus.UNSUPPORTED
        evaluated.reason = (
            f"{requirements.category.value} claims require a "
            f"{requirements.authority.value} source; the best supporting source "
            f"is {best.value}. {requirements.rationale}")
        return evaluated

    # ── Corroboration ────────────────────────────────────────────────────────
    if evaluated.corroborating_sources < requirements.min_corroborating_sources:
        # An official source speaks for itself; a market average does not.
        if best is SourceQuality.OFFICIAL:
            pass
        else:
            evaluated.status = EvidenceStatus.PARTIALLY_SUPPORTED
            evaluated.reason = (
                f"{requirements.category.value} claims need "
                f"{requirements.min_corroborating_sources} independent sources; "
                f"{evaluated.corroborating_sources} found. "
                f"{requirements.rationale}")
            return evaluated

    # ── Freshness — only where the claim's category says it matters ──────────
    if requirements.freshness is FreshnessRequirement.REQUIRED and \
            not evaluated.has_dated_support:
        evaluated.status = EvidenceStatus.PARTIALLY_SUPPORTED
        evaluated.reason = (
            f"Stated by a {best.value} source, but {requirements.category.value} "
            f"claims depend on when they were published and no supporting source "
            f"carries a date.")
        return evaluated

    evaluated.status = EvidenceStatus.SUPPORTED
    dated = "dated" if evaluated.has_dated_support else "undated"
    evaluated.reason = (
        f"Materially stated by {evaluated.corroborating_sources} {best.value} "
        f"source(s) ({dated}); meets the {requirements.category.value} bar.")
    return evaluated


def build_candidates(
    claim: AtomicClaim,
    sources_by_ref: dict[str, dict],
    passages_by_ref: dict[str, list[str]],
) -> list[EvidenceRef]:
    """Find every eligible source whose passages bear on this claim.

    Only sources that passed the relevance gate are considered — a rejected source
    never becomes evidence, whatever its text says.
    """
    refs: list[EvidenceRef] = []
    for source_ref, source in sources_by_ref.items():
        relevance = RelevanceStatus(source.get("relevance_status",
                                               RelevanceStatus.UNKNOWN.value))
        if not relevance.is_eligible:
            continue

        best: tuple[bool, bool | None, str] | None = None
        for passage in passages_by_ref.get(source_ref, []):
            supports, agrees = passage_supports_claim(claim.text, passage)
            if best is None or (supports and not best[0]):
                best = (supports, agrees, passage)
            if supports:
                break
        if best is None:
            continue
        supports, agrees, passage = best
        if not supports and agrees is None:
            # Off-topic for this claim; not evidence either way.
            continue

        refs.append(EvidenceRef(
            source_ref=source_ref,
            passage=passage,
            url=source.get("url"),
            source_type=source.get("source_type", "web"),
            quality=SourceQuality(source.get("source_quality",
                                             SourceQuality.UNKNOWN.value)),
            relevance=relevance,
            observation=ObservationStatus(source.get("observation_status",
                                                     ObservationStatus.ESTIMATED.value)),
            published_at=source.get("published_at_dt"),
            retrieved_at=source.get("retrieved_at_dt"),
            provider=source.get("provider", ""),
            supports=supports,
            agrees_numerically=agrees,
        ))
    return refs


def summarize(claims: list[EvaluatedClaim]) -> dict:
    counts: dict[str, int] = {}
    for claim in claims:
        counts[claim.status.value] = counts.get(claim.status.value, 0) + 1

    high_risk = [c for c in claims if c.requirements.risk == ClaimRisk.HIGH]
    return {
        "claims_total": len(claims),
        "by_evidence_status": counts,
        "supported": counts.get(EvidenceStatus.SUPPORTED.value, 0),
        "partially_supported": counts.get(EvidenceStatus.PARTIALLY_SUPPORTED.value, 0),
        "unsupported": counts.get(EvidenceStatus.UNSUPPORTED.value, 0),
        "conflicting": counts.get(EvidenceStatus.CONFLICTING.value, 0),
        "high_risk_total": len(high_risk),
        "high_risk_supported": sum(1 for c in high_risk
                                   if c.status is EvidenceStatus.SUPPORTED),
        "high_risk_blocked": sum(1 for c in high_risk
                                 if c.status is not EvidenceStatus.SUPPORTED),
        "multi_source_claims": sum(1 for c in claims
                                   if c.corroborating_sources > 1),
    }


def unresolved_high_risk(claims: list[EvaluatedClaim]) -> list[EvaluatedClaim]:
    """HIGH-risk claims that could not be established — the research planner's
    input for a targeted authoritative search."""
    return [c for c in claims
            if c.requirements.risk == ClaimRisk.HIGH
            and c.status is not EvidenceStatus.SUPPORTED]
