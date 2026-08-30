"""ResearchPackage V2 — evidence assembly with a relevance gate.

V1 took whatever a provider returned and marked it supported. V2 makes every
source pass three independent checks before it can reach the writer:

    relevance   is this about the query?          → RelevanceGate
    quality     how much weight does it carry?    → SourceQuality
    risk        how bad if this claim is wrong?   → ClaimRisk

Only sources that pass relevance become **eligible evidence**. Everything else is
kept in `rejected_evidence` with its reason, because "why was this thrown away" is
the question an operator actually asks when relevance misbehaves — and Phase 2
had no answer to it.

Still fully deterministic. No model participates in deciding what counts as
evidence; the optional semantic review runs in the caller and only for the
ambiguous middle.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums import Observability, SearchIntent
from app.schemas.research import ResearchProviderResult
from app.schemas.serp import KeywordMetric, SerpSnapshot
from app.services import claim_risk as risk_module
from app.services import source_quality as quality_module
from app.services.claim_risk import ClaimRisk
from app.services.relevance import (RelevanceDecision, RelevanceStatus,
                                    RelevanceThresholds, query_that_fetched,
                                    score_claim, score_source)
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile

PACKAGE_VERSION = 2


def _source_entry(source, decision: RelevanceDecision, quality: SourceQuality,
                  provider: str, index: int) -> dict:
    return {
        "ref": source.candidate_id or f"{provider}-{index:03d}",
        "provider": provider,
        "source_type": source.source_type,
        "state": source.state.value,
        "url": source.url,
        "title": source.title,
        # Absent stays absent. Never back-filled.
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None,
        "freshness_verdict": (source.freshness_verdict.value
                              if source.freshness_verdict else None),
        "source_quality": quality.value,
        "relevance": decision.as_dict(),
    }


def build_package_v2(
    *,
    query: str,
    market: str,
    language: str,
    intent: SearchIntent,
    profile: VerticalProfile,
    serp: SerpSnapshot | None,
    serp_analysis: dict | None,
    keyword_metrics: list[KeywordMetric],
    research_results: list[ResearchProviderResult],
    relevance_decisions: dict[str, RelevanceDecision] | None = None,
    thresholds: RelevanceThresholds | None = None,
) -> dict:
    """Assemble the V2 package body.

    `relevance_decisions` lets the caller supply already-computed decisions (for
    instance after a semantic review). Anything absent is scored here.
    """
    thresholds = thresholds or RelevanceThresholds()
    supplied = relevance_decisions or {}

    eligible: list[dict] = []
    rejected: list[dict] = []
    all_sources: list[dict] = []
    facts: list[dict] = []
    qualities: list[SourceQuality] = []
    risks: list[ClaimRisk] = []
    relevance_scores: list[float] = []

    for result in research_results:
        provider = result.provider
        for index, source in enumerate(result.sources):
            ref = source.candidate_id or f"{provider}-{index:03d}"

            # A source is judged against the question it was fetched to answer.
            # For general web research that IS the article's query; for the
            # targeted authoritative pass it is the planner's own query, and
            # using the article's query there discarded every official page.
            decision = supplied.get(ref) or score_source(
                query=query_that_fetched(source.metadata, default=query),
                profile=profile, title=source.title,
                body=source.summary, url=source.url, thresholds=thresholds,
            )
            quality = quality_module.classify_domain(
                source.url, source_type=source.source_type)
            # A vertical may name domains it treats as authoritative regardless of
            # the generic classifier — regulators and grid operators for a market.
            if source.url and any(
                d.lower() in (source.url or "").lower()
                for d in profile.authoritative_domains
            ):
                quality = SourceQuality.OFFICIAL

            entry = _source_entry(source, decision, quality, provider, index)
            all_sources.append(entry)
            relevance_scores.append(decision.score)

            if decision.status.is_eligible:
                eligible.append(entry)
                qualities.append(quality)
            else:
                rejected.append({**entry, "rejection_reason": decision.reason,
                                 "rejection_status": decision.status.value})

        eligible_refs = {e["ref"] for e in eligible}
        quality_by_ref = {e["ref"]: SourceQuality(e["source_quality"])
                          for e in eligible}

        for fact in result.facts:
            ref = fact.source_ref
            if ref not in eligible_refs:
                # A claim from a rejected source is not evidence, whatever it says.
                continue

            source_decision = supplied.get(ref) or RelevanceDecision(
                status=RelevanceStatus.RELEVANT, score=1.0,
                reason="parent source eligible")
            claim_decision = score_claim(
                query=query, profile=profile, claim=fact.fact,
                source_decision=source_decision, thresholds=thresholds,
            )

            quality = quality_by_ref.get(ref, SourceQuality.UNKNOWN)
            risk, sufficient, risk_reason = risk_module.assess(
                fact.fact, profile, quality)
            risks.append(risk)

            # `supported` now needs four things to be true, not one.
            supported = (
                fact.observability is Observability.OBSERVED
                and claim_decision.status.is_eligible
                and sufficient
            )

            facts.append({
                "fact": fact.fact,
                "evidence_type": fact.evidence_type,
                "observability": fact.observability.value,
                "confidence": fact.confidence,
                "source_ref": ref,
                "provider": provider,
                "source_quality": quality.value,
                "claim_risk": risk.value,
                "evidence_sufficient": sufficient,
                "claim_relevance": claim_decision.as_dict(),
                "supported": supported,
                "notes": risk_reason,
            })

    # ── Unresolved ───────────────────────────────────────────────────────────
    unresolved: list[str] = []
    for result in research_results:
        unresolved.extend(result.unresolved_data)

    if not eligible:
        unresolved.append(
            "No source passed the relevance gate. Content must not be generated "
            "from model knowledge alone."
        )
    if rejected:
        unresolved.append(
            f"{len(rejected)} retrieved source(s) were rejected as off-topic and "
            f"are excluded from the evidence set."
        )

    high_risk_unsupported = [
        f for f in facts
        if f["claim_risk"] == ClaimRisk.HIGH.value and not f["supported"]
    ]
    for fact in high_risk_unsupported[:10]:
        unresolved.append(
            f"HIGH-risk claim lacks sufficient evidence and may not be asserted: "
            f"{fact['fact'][:140]}"
        )

    for claim in profile.restricted_claims:
        if not any(claim.casefold() in f["fact"].casefold() and f["supported"]
                   for f in facts):
            continue
        unresolved.append(
            f"Topic '{claim}' appears in retrieved material; verify the supporting "
            f"source before asserting anything quantitative."
        )

    # ── Summaries ────────────────────────────────────────────────────────────
    supported_facts = [f for f in facts if f["supported"]]
    mean_relevance = (sum(relevance_scores) / len(relevance_scores)
                      if relevance_scores else None)

    confidence_summary = {
        "sources_retrieved": len(all_sources),
        "sources_eligible": len(eligible),
        "sources_rejected": len(rejected),
        "facts_total": len(facts),
        "facts_supported": len(supported_facts),
        "facts_observed": sum(1 for f in facts
                              if f["observability"] == Observability.OBSERVED.value),
        "facts_estimated": sum(1 for f in facts
                               if f["observability"] == Observability.ESTIMATED.value),
        "facts_unknown": sum(1 for f in facts
                             if f["observability"] == Observability.UNKNOWN.value),
        "high_risk_claims": sum(1 for f in facts
                                if f["claim_risk"] == ClaimRisk.HIGH.value),
        "high_risk_unsupported": len(high_risk_unsupported),
        "mean_relevance": round(mean_relevance, 3) if mean_relevance is not None else None,
        "partial_observation": any(r.is_partial for r in research_results),
        "serp_available": serp is not None,
    }

    provenance = {
        "package_version": PACKAGE_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "providers": [
            {
                "provider": r.provider, "status": r.status,
                "engine_commit": r.engine_commit, "duration_ms": r.duration_ms,
                "source_outcomes": [
                    {"source_type": o.source_type, "state": o.state.value,
                     "item_count": o.item_count}
                    for o in r.source_outcomes
                ],
                "metadata": r.provider_metadata,
            }
            for r in research_results
        ],
        "serp": {
            "provider": serp.provider, "retrieved_at": serp.retrieved_at.isoformat(),
            "location_code": serp.location_code, "language_code": serp.language_code,
            "device": serp.device, "organic_count": len(serp.organic),
            "provider_cost_usd": serp.provider_cost,
            "metadata": serp.provider_metadata,
        } if serp else None,
    }

    analysis = serp_analysis or {}

    return {
        "query": query,
        "market": market,
        "language": language,
        "intent": intent.value,
        "summary": _summary(analysis, confidence_summary),
        "facts": facts,
        "sources": all_sources,
        "eligible_evidence": eligible,
        "rejected_evidence": rejected,
        "competitor_pages": analysis.get("competitor_pages", []),
        "serp_observations": analysis.get("observations", []),
        "serp_features": analysis.get("serp_features", []),
        "content_gap": analysis.get("content_gap", []),
        "user_questions": analysis.get("questions", []),
        "related_searches": analysis.get("related_searches", []),
        "keyword_metrics": [
            {"metric_type": m.metric_type, "value": m.value,
             "value_text": m.value_text, "currency": m.currency,
             "observability": m.observability.value, "provider": m.provider,
             "retrieved_at": m.retrieved_at.isoformat() if m.retrieved_at else None}
            for m in keyword_metrics
        ],
        "source_quality_summary": quality_module.summarize(qualities),
        "claim_risk_summary": risk_module.summarize(risks),
        "unresolved_questions": unresolved,
        "confidence_summary": confidence_summary,
        "provider_provenance": provenance,
    }


def _summary(analysis: dict, confidence: dict) -> str | None:
    parts: list[str] = []
    if analysis.get("dominant_framing"):
        parts.append(f"SERP framing is {analysis['dominant_framing']}")
    if analysis.get("organic_count"):
        parts.append(f"{analysis['organic_count']} organic results analysed")
    parts.append(
        f"{confidence['sources_eligible']} of {confidence['sources_retrieved']} "
        f"retrieved sources passed the relevance gate"
    )
    return "; ".join(parts) if parts else None
