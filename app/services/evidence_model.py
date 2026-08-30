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
from app.services.claim_matching import (MatchResult, extract_concepts,
                                         match as claim_match)
from app.services.claim_policy import (ClaimRequirements, ClaimRisk,
                                       authority_is_sufficient, classify_category,
                                       requirements_for)
from app.services.intent import normalize_query
from app.services.relevance import RelevanceStatus
from app.services.conflict import ConflictKind, classify as classify_conflict
from app.services.freshness import FreshnessStatus
from app.services.region import Region, describe_mismatch, detect_region
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
    # ── Phase 3.2 ────────────────────────────────────────────────────────────
    region: Region = Region.UNKNOWN
    authority_type: str | None = None
    freshness_status: FreshnessStatus | None = None
    effective_from: str | None = None
    effective_until: str | None = None

    def __post_init__(self) -> None:
        """Derive freshness from the publication date when not stated.

        The authoritative path assesses freshness from the page text and passes a
        rich status. The ordinary web path only knows whether a date exists — and
        if that silently defaulted to UNDATED, every dated source would fail the
        freshness bar and every HIGH-risk claim would come back PARTIAL even when
        properly evidenced.
        """
        if self.freshness_status is None:
            self.freshness_status = (FreshnessStatus.DATED_CURRENT
                                     if self.published_at is not None
                                     else FreshnessStatus.UNDATED)

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
            "region": self.region.value,
            "authority_type": self.authority_type,
            "freshness_status": self.freshness_status.value,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
        }


@dataclass
class EvaluatedClaim:
    """An atomic claim with its evidence and its verdict."""

    claim: AtomicClaim
    requirements: ClaimRequirements
    evidence: list[EvidenceRef] = field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.UNSUPPORTED
    reason: str = ""
    _claim_region: Region = Region.UNKNOWN
    # Why the scope is what it is, when it was not read off the sentence.
    _scope_note: str | None = None
    _conflict_kind: ConflictKind | None = None
    _conflicts: list[dict] = field(default_factory=list)

    @property
    def corroborating_sources(self) -> int:
        return len({e.source_ref for e in self.evidence if e.supports})

    @property
    def best_quality(self) -> SourceQuality:
        supporting = [e.quality for e in self.evidence if e.supports]
        return max(supporting, key=lambda q: q.rank) if supporting else SourceQuality.UNKNOWN

    @property
    def has_dated_support(self) -> bool:
        """Whether supporting evidence can carry a claim about the present.

        `UNDATED_CURRENT` counts: an official portal describing a scheme in the
        present tense is meaningfully different from an undated blog post, and
        the mission asks for that distinction rather than a single date bit.
        """
        return any(e.supports and e.freshness_status.can_support_current_claim
                   for e in self.evidence)

    @property
    def claim_region(self) -> Region:
        return self._claim_region

    @property
    def conflict_kind(self) -> ConflictKind | None:
        return self._conflict_kind

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
            "region": self._claim_region.value,
            "regionally_determined": self.requirements.regionally_determined,
            "scope_note": self._scope_note,
            "conflict_kind": self._conflict_kind.value if self._conflict_kind else None,
            "conflicts": self._conflicts,
            "evidence": [e.as_dict() for e in self.evidence],
            # Kept so Phase 2/3 consumers that read `supported` keep working.
            "supported": self.status is EvidenceStatus.SUPPORTED,
        }


def passage_supports_claim(
    claim_text: str, passage: str, *,
    profile: VerticalProfile | None = None,
    claim_category: ClaimCategory | None = None,
    claim_region: Region | None = None,
    passage_region: Region | None = None,
) -> tuple[bool, bool | None]:
    """Does this passage materially state this claim?

    Delegates to the staged matcher when a vertical profile is available. The
    Phase 3.2 implementation accepted a two-content-word overlap and produced 163
    false conflicts from 23 sources; `claim_matching` requires the claim's
    semantic head, discriminative (not generic) terms, compatible region and
    category, and comparable numeric TYPES before any figure is compared.

    Returns (supports, agrees_numerically). `agrees_numerically` is None when the
    claim carries no comparable figure — a distinction that matters, because a
    passage silent about a number is not one that states a different number.
    """
    if profile is None:
        # Kept for callers with no vertical context. Same shape, coarser rule.
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
        return False, False

    result = match_passage(claim_text, passage, profile=profile,
                           claim_category=claim_category,
                           claim_region=claim_region,
                           passage_region=passage_region)
    return result.supports, result.agrees_numerically


def match_passage(
    claim_text: str, passage: str, *, profile: VerticalProfile,
    claim_category: ClaimCategory | None = None,
    claim_region: Region | None = None,
    passage_region: Region | None = None,
) -> MatchResult:
    """Full matcher result, including the reason codes."""
    claim_concepts = extract_concepts(claim_text, profile,
                                      category=claim_category,
                                      region=claim_region)
    passage_concepts = extract_concepts(
        passage, profile,
        category=classify_category(passage, profile) if profile else None,
        region=passage_region)
    return claim_match(claim_concepts, passage_concepts)


def evaluate_claim(
    claim: AtomicClaim,
    candidates: list[EvidenceRef],
    profile: VerticalProfile,
    *,
    default_region: Region = Region.UNKNOWN,
) -> EvaluatedClaim:
    """Classify one claim against its candidate evidence."""
    requirements = requirements_for(claim.text, profile)
    stated_region = detect_region(claim.text).region
    claim_region = (stated_region if stated_region is not Region.UNKNOWN
                    else default_region)
    evaluated = EvaluatedClaim(claim=claim, requirements=requirements,
                               evidence=candidates)

    supporting = [e for e in candidates if e.supports]

    # ── Scope a region-less claim to the evidence that carries it ────────────
    # Measured on 2026-08-30: twenty official sources asked the real payback
    # question, and not one states a payback for Belgium as a whole. The regions
    # set the terms — prosumer tariff, green certificates, premiums — and the
    # regions publish the figures. Belgian solar profitability is not a national
    # quantity, so synthesising one would fabricate a number nobody publishes.
    #
    # A sentence like "le retour sur investissement est de 8 ans" names no
    # region. The market default then stamped it BE, and the scope rule refused
    # every Walloon source that supported it — correctly, since a Walloon
    # payback is not a Belgian one. Seventeen ROI claims died that way, on an
    # article whose subject IS profitability.
    #
    # The scope rule does not move: regional evidence still cannot establish a
    # country-wide claim. What changes is what the claim IS. When the market
    # sets this category regionally and every supporting source sits in ONE
    # region, the honest reading is that the sentence states that region's
    # answer, not the country's. It becomes a regional claim, provable, and the
    # writer is told to say which region — see `brief_service`.
    #
    # Two or more regions among the supporting sources changes nothing: that is
    # not one claim in two places, it is two regional claims, and the article
    # must break them out rather than average them.
    scope_note: str | None = None
    if stated_region is Region.UNKNOWN and requirements.regionally_determined:
        evidence_regions = {e.region for e in supporting
                            if e.region.is_subnational}
        if len(evidence_regions) == 1:
            claim_region = evidence_regions.pop()
            scope_note = (
                f"Claim names no region and {requirements.category.value} is set "
                f"regionally in this market; scoped to {claim_region.value}, the "
                f"only region its evidence covers. It must be written as such.")

    evaluated._claim_region = claim_region
    evaluated._scope_note = scope_note
    disagreeing = [e for e in candidates
                   if not e.supports and e.agrees_numerically is False]

    # ── Classify disagreements before treating them as conflicts ─────────────
    # Phase 3.1 flagged 23 of 121 claims CONFLICTING, and most were not
    # disagreements: Wallonia vs Brussels premiums, or 2025 vs 2026 figures.
    # Only a genuine same-scope same-period disagreement blocks.
    true_conflicts = []
    for ref in disagreeing:
        assessment = classify_conflict(claim.text, ref.passage,
                                       claim_region=claim_region,
                                       other_region=ref.region)
        evaluated._conflicts.append({**assessment.as_dict(),
                                     "source_ref": ref.source_ref})
        if assessment.blocks:
            true_conflicts.append(ref)
            evaluated._conflict_kind = assessment.kind

    # ── Nothing states it ────────────────────────────────────────────────────
    if not supporting:
        if true_conflicts:
            evaluated.status = EvidenceStatus.CONFLICTING
            evaluated.reason = (
                f"{len(true_conflicts)} eligible source(s) state a different "
                f"figure for the same scope and period.")
        else:
            evaluated.status = EvidenceStatus.UNSUPPORTED
            reason = "No eligible passage materially states this claim."
            if disagreeing:
                kinds = {c["kind"] for c in evaluated._conflicts}
                reason += (f" {len(disagreeing)} source(s) differ, but only by "
                           f"{', '.join(sorted(kinds))}.")
            evaluated.reason = reason
        return evaluated

    # ── Genuine contradiction among supporters ───────────────────────────────
    if true_conflicts:
        evaluated.status = EvidenceStatus.CONFLICTING
        evaluated.reason = (
            f"{len(supporting)} source(s) support this figure and "
            f"{len(true_conflicts)} state a different one for the same scope "
            f"and period.")
        return evaluated

    # ── Regional scope ───────────────────────────────────────────────────────
    # A Walloon premium may not establish a Belgium-wide claim. Enforced for
    # HIGH-risk claims, where over-generalising is a false statement of law.
    if requirements.risk == ClaimRisk.HIGH and claim_region is not Region.UNKNOWN:
        in_scope = [e for e in supporting
                    if e.region is Region.UNKNOWN or e.region.covers(claim_region)]
        if not in_scope:
            mismatch = describe_mismatch(supporting[0].region, claim_region)
            evaluated.status = EvidenceStatus.UNSUPPORTED
            evaluated.reason = (
                f"Regional scope mismatch: {mismatch}. "
                f"{requirements.rationale}")
            return evaluated
        supporting = in_scope

    # ── Authority ────────────────────────────────────────────────────────────
    best = max((e.quality for e in supporting), key=lambda q: q.rank)
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
    if requirements.freshness is FreshnessRequirement.REQUIRED:
        usable = [e for e in supporting
                  if e.freshness_status.can_support_current_claim]
        if not usable:
            expired = [e for e in supporting
                       if e.freshness_status in (FreshnessStatus.HISTORICAL,
                                                 FreshnessStatus.DATED_EXPIRED)]
            evaluated.status = EvidenceStatus.PARTIALLY_SUPPORTED
            if expired:
                # An archived page describing a scheme that ended must never
                # establish a present-tense claim.
                evaluated.reason = (
                    f"Stated by a {best.value} source, but that source is "
                    f"{expired[0].freshness_status.value} and cannot establish a "
                    f"current {requirements.category.value} claim.")
            else:
                evaluated.reason = (
                    f"Stated by a {best.value} source, but "
                    f"{requirements.category.value} claims depend on when they "
                    f"were published and no supporting source is dated or "
                    f"presents as in force.")
            return evaluated

    evaluated.status = EvidenceStatus.SUPPORTED
    freshness = next((e.freshness_status.value for e in supporting
                      if e.freshness_status.can_support_current_claim),
                     FreshnessStatus.UNDATED.value)
    scope = (f", scoped {claim_region.value}" if claim_region is not Region.UNKNOWN
             else "")
    evaluated.reason = (
        f"Materially stated by {evaluated.corroborating_sources} {best.value} "
        f"source(s) ({freshness}{scope}); meets the "
        f"{requirements.category.value} bar.")
    return evaluated


def build_candidates(
    claim: AtomicClaim,
    sources_by_ref: dict[str, dict],
    passages_by_ref: dict[str, list[str]],
    *,
    profile: VerticalProfile | None = None,
    claim_category: ClaimCategory | None = None,
    claim_region: Region | None = None,
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

        source_region = source.get("region_enum", Region.UNKNOWN)
        best: tuple[bool, bool | None, str, list[str]] | None = None
        for passage in passages_by_ref.get(source_ref, []):
            if profile is not None:
                result = match_passage(
                    claim.text, passage, profile=profile,
                    claim_category=claim_category, claim_region=claim_region,
                    passage_region=source_region)
                supports, agrees = result.supports, result.agrees_numerically
                reasons = [r.value for r in result.reasons]
            else:
                supports, agrees = passage_supports_claim(claim.text, passage)
                reasons = []
            if best is None or (supports and not best[0]):
                best = (supports, agrees, passage, reasons)
            if supports:
                break
        if best is None:
            continue
        supports, agrees, passage, reasons = best
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
            note="; ".join(reasons),
            region=source_region,
            authority_type=source.get("authority_type"),
            freshness_status=source.get("freshness_enum"),
            effective_from=source.get("effective_from"),
            effective_until=source.get("effective_until"),
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
