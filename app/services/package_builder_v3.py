"""ResearchPackage V3 — claim-level evidence assembly.

The change from V2 is where "a fact" comes from. V2 took a provider's excerpt and
treated it as one fact; V3 runs the full chain:

    source → passages → atomic claims → evidence mapping → requirements → status

and the writer receives *claims with verdicts*, never raw excerpts.

The four dimensions stay independent throughout. A claim can be SUPPORTED by an
undated page (freshness only binds where the claim's category says it does), and a
dated page can support nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums import ClaimCategory, EvidenceStatus, ObservationStatus
from app.schemas.research import ResearchProviderResult
from app.schemas.serp import KeywordMetric, SerpSnapshot
from app.services import claim_policy, evidence_model
from app.services import source_quality as quality_module
from app.services.claim_extraction import extract_claim_set
from app.services.claim_policy import ClaimRisk
from app.services.evidence_model import EvaluatedClaim, EvidenceStatus as ES
from app.services.passage_extraction import extract_passages
from app.services.relevance import (RelevanceDecision, RelevanceStatus,
                                    RelevanceThresholds, score_source)
from app.services.authority_registry import AuthorityRegistry, build_registry
from app.services.freshness import FreshnessStatus, assess as assess_freshness
from app.services.region import Region, detect_region, region_for_market
from app.services.research_planner import plan_authoritative_research
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile

PACKAGE_VERSION = 4


def build_package_v3(
    *,
    query: str,
    market: str,
    language: str,
    intent,
    profile: VerticalProfile,
    serp: SerpSnapshot | None,
    serp_analysis: dict | None,
    keyword_metrics: list[KeywordMetric],
    research_results: list[ResearchProviderResult],
    relevance_decisions: dict[str, RelevanceDecision] | None = None,
    thresholds: RelevanceThresholds | None = None,
    registry: AuthorityRegistry | None = None,
    authoritative_run: dict | None = None,
    previous_package_version: int | None = None,
) -> dict:
    thresholds = thresholds or RelevanceThresholds()
    supplied = relevance_decisions or {}
    registry = registry if registry is not None else build_registry(profile)
    default_region = region_for_market(market)

    sources_by_ref: dict[str, dict] = {}
    passages_by_ref: dict[str, list[str]] = {}
    all_sources: list[dict] = []
    eligible: list[dict] = []
    rejected: list[dict] = []
    passage_stats: list[dict] = []

    # ── Sources, relevance gate, passages ────────────────────────────────────
    for result in research_results:
        for index, source in enumerate(result.sources):
            ref = source.candidate_id or f"{result.provider}-{index:03d}"

            decision = supplied.get(ref) or score_source(
                query=query, profile=profile, title=source.title,
                body=source.summary, url=source.url, thresholds=thresholds)

            quality = quality_module.classify_domain(
                source.url, source_type=source.source_type)
            # OFFICIAL comes from the registry, never from which query returned
            # the page. A commercial installer is not in the registry and so can
            # never acquire OFFICIAL through this path.
            authority = registry.lookup(source.url)
            authority_type = None
            if authority is not None:
                quality = authority.authority_type.source_quality
                authority_type = authority.authority_type.value

            observation = (ObservationStatus.OBSERVED if source.published_at
                           else ObservationStatus.ESTIMATED)

            body_text = f"{source.title or ''}\n{source.summary or ''}"
            freshness = assess_freshness(body_text,
                                         published_at=source.published_at,
                                         retrieved_at=source.retrieved_at)
            # For a registered authority its own jurisdiction is definitive; a
            # Walloon portal does not become a Brussels source because a page
            # mentions Brussels. Text detection applies only to unregistered
            # sources, where there is nothing better to go on.
            if authority is not None and authority.region is not Region.UNKNOWN:
                region = authority.region
            else:
                region = detect_region(body_text).region

            # Two views of the same source: `internal` keeps live datetimes for
            # the evidence mapper, `entry` is the JSON-serialisable form that gets
            # persisted. Mixing them put raw datetimes into a JSONB column.
            entry = {
                "ref": ref,
                "provider": result.provider,
                "source_type": source.source_type,
                "state": source.state.value,
                "url": source.url,
                "title": source.title,
                "published_at": source.published_at.isoformat() if source.published_at else None,
                "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None,
                "source_quality": quality.value,
                "authority_type": authority_type,
                "region": region.value,
                # Kept as its own dimension. It says when, not whether.
                "observation_status": observation.value,
                **freshness.as_dict(),
                "relevance_status": decision.status.value,
                "relevance": decision.as_dict(),
            }
            all_sources.append(entry)

            if decision.status.is_eligible:
                sources_by_ref[ref] = {
                    **entry,
                    "published_at_dt": source.published_at,
                    "retrieved_at_dt": source.retrieved_at,
                    "region_enum": region,
                    "freshness_enum": freshness.status,
                }
                eligible.append(entry)
                # Passage extraction happens ONLY for eligible sources: a rejected
                # source must never contribute text to a claim.
                passage_set = extract_passages(source.summary or "", source_ref=ref)
                passages_by_ref[ref] = [p.text for p in passage_set.passages]
                passage_stats.append(passage_set.summary())
            else:
                rejected.append({**entry, "rejection_status": decision.status.value,
                                 "rejection_reason": decision.reason})

    # ── Atomic claims from eligible passages ─────────────────────────────────
    from app.services.passage_extraction import Passage

    all_passages: list[Passage] = []
    for ref, texts in passages_by_ref.items():
        all_passages.extend(Passage(text=t, offset=0, source_ref=ref)
                            for t in texts)
    claim_set = extract_claim_set(all_passages)

    # ── Evidence mapping and classification ──────────────────────────────────
    evaluated: list[EvaluatedClaim] = []
    for claim in claim_set.claims:
        # Category and region are computed once and handed to the matcher, so a
        # passage is judged against the claim's own scope rather than re-derived
        # per passage.
        requirements = claim_policy.requirements_for(claim.text, profile)
        claim_region = detect_region(claim.text, default=default_region).region
        candidates = evidence_model.build_candidates(
            claim, sources_by_ref, passages_by_ref, profile=profile,
            claim_category=requirements.category, claim_region=claim_region)
        evaluated.append(evidence_model.evaluate_claim(
            claim, candidates, profile, default_region=default_region))

    claims = [c.as_dict() for c in evaluated]
    supported = [c for c in evaluated if c.status is ES.SUPPORTED]
    partial = [c for c in evaluated if c.status is ES.PARTIALLY_SUPPORTED]
    conflicting = [c for c in evaluated if c.status is ES.CONFLICTING]
    unresolved_high = evidence_model.unresolved_high_risk(evaluated)

    # ── Targeted authoritative research plan ─────────────────────────────────
    plan = plan_authoritative_research(topic=query, market=market,
                                       unresolved=unresolved_high, profile=profile)

    # ── Unresolved narrative ─────────────────────────────────────────────────
    unresolved_notes: list[str] = []
    for result in research_results:
        unresolved_notes.extend(result.unresolved_data)

    if not supported:
        unresolved_notes.append(
            "No atomic claim reached SUPPORTED. Content must not be generated "
            "from model knowledge alone.")
    if rejected:
        unresolved_notes.append(
            f"{len(rejected)} retrieved source(s) were rejected as off-topic and "
            f"contributed no passages.")
    for claim in unresolved_high[:10]:
        unresolved_notes.append(
            f"{claim.requirements.category.value} claim unresolved "
            f"({claim.status.value}): {claim.claim.text[:120]} — {claim.reason[:140]}")
    for claim in conflicting[:5]:
        unresolved_notes.append(
            f"CONFLICTING evidence: {claim.claim.text[:120]} — {claim.reason[:140]}")
    if not plan.is_empty:
        unresolved_notes.append(
            f"{len(plan.queries)} targeted authoritative search(es) proposed to "
            f"resolve HIGH-risk gaps.")

    dropped_passages = sum(s["dropped"] for s in passage_stats)
    kept_passages = sum(s["kept"] for s in passage_stats)

    evidence_summary = evidence_model.summarize(evaluated)
    confidence_summary = {
        "sources_retrieved": len(all_sources),
        "sources_eligible": len(eligible),
        "sources_rejected": len(rejected),
        "passages_kept": kept_passages,
        "passages_dropped": dropped_passages,
        **evidence_summary,
        "sources_dated": sum(1 for s in eligible
                             if s["observation_status"] == ObservationStatus.OBSERVED.value),
        "sources_undated": sum(1 for s in eligible
                               if s["observation_status"] == ObservationStatus.ESTIMATED.value),
        "mean_relevance": _mean([s["relevance"]["score"] for s in all_sources]),
        "partial_observation": any(r.is_partial for r in research_results),
        "serp_available": serp is not None,
    }

    analysis = serp_analysis or {}
    qualities = [SourceQuality(s["source_quality"]) for s in eligible]

    return {
        "query": query,
        "market": market,
        "language": language,
        "intent": intent.value if hasattr(intent, "value") else str(intent),
        "summary": _summary(analysis, confidence_summary),

        # ── What the writer may use ──────────────────────────────────────────
        "claims": claims,
        "supported_claims": [c.as_dict() for c in supported],
        "partially_supported_claims": [c.as_dict() for c in partial],
        "conflicting_claims": [c.as_dict() for c in conflicting],

        # Retained for compatibility with V2 consumers. `facts` now carries
        # atomic claims rather than page excerpts.
        "facts": claims,

        "sources": all_sources,
        "eligible_evidence": eligible,
        "rejected_evidence": rejected,
        # Provenance split, so a reviewer can see at a glance what rests on a
        # regulator and what rests on an installer's marketing page.
        "official_evidence": [e for e in eligible
                              if e.get("source_quality") == SourceQuality.OFFICIAL.value],
        "commercial_evidence": [e for e in eligible
                                if e.get("source_quality") != SourceQuality.OFFICIAL.value],
        "authoritative_run": authoritative_run or {},
        "passage_extraction": passage_stats,
        "claim_extraction": claim_set.summary(),
        "authoritative_research_plan": plan.as_dict(),

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
        "claim_risk_summary": claim_policy.summarize(
            [c.requirements for c in evaluated]),
        "unresolved_questions": unresolved_notes,
        "confidence_summary": confidence_summary,
        "provider_provenance": {
            "package_version": PACKAGE_VERSION,
            "supersedes_package_version": previous_package_version,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "authority_registry": [e.as_dict() for e in registry.entries],
            "providers": [
                {"provider": r.provider, "status": r.status,
                 "engine_commit": r.engine_commit, "duration_ms": r.duration_ms,
                 "source_outcomes": [
                     {"source_type": o.source_type, "state": o.state.value,
                      "item_count": o.item_count} for o in r.source_outcomes],
                 "metadata": r.provider_metadata}
                for r in research_results
            ],
            "serp": {
                "provider": serp.provider,
                "retrieved_at": serp.retrieved_at.isoformat(),
                "location_code": serp.location_code,
                "language_code": serp.language_code, "device": serp.device,
                "organic_count": len(serp.organic),
                "provider_cost_usd": serp.provider_cost,
                "metadata": serp.provider_metadata,
            } if serp else None,
        },
    }


def writer_payload(package: dict, *, allow_partial: bool = False) -> dict:
    """Exactly what the writer is allowed to see.

    Never raw excerpts, never rejected sources, never a claim that failed its own
    category's bar. Partially supported claims travel in a separate list and are
    explicitly labelled, so they cannot be mistaken for established facts.
    """
    supported = package.get("supported_claims") or []
    partial = package.get("partially_supported_claims") or [] if allow_partial else []

    def strip(claim: dict) -> dict:
        return {
            "claim": claim["claim"],
            "category": claim["category"],
            "evidence_status": claim["evidence_status"],
            "sources": [
                {"url": e["url"], "quality": e["source_quality"],
                 "published_at": e["published_at"], "passage": e["passage"][:300]}
                for e in claim.get("evidence", []) if e.get("supports")
            ],
        }

    forbidden = [
        {"topic": c["topic"], "reason": "no supporting evidence of sufficient authority"}
        for c in _forbidden_topics(package)
    ]

    return {
        "supported_claims": [strip(c) for c in supported],
        "partially_supported_claims": [
            {**strip(c), "caveat": c.get("reason", "")} for c in partial
        ],
        "unresolved_facts": package.get("unresolved_questions") or [],
        "forbidden_claims": forbidden,
    }


def _forbidden_topics(package: dict) -> list[dict]:
    topics: dict[str, dict] = {}
    for claim in package.get("claims") or []:
        if claim["evidence_status"] == EvidenceStatus.SUPPORTED.value:
            continue
        if claim["claim_risk"] != ClaimRisk.HIGH:
            continue
        topics.setdefault(claim["category"], {"topic": claim["category"]})
    return list(topics.values())


def _mean(values: list[float]) -> float | None:
    numeric = [v for v in values if isinstance(v, (int, float))]
    return round(sum(numeric) / len(numeric), 3) if numeric else None


def _summary(analysis: dict, confidence: dict) -> str | None:
    parts: list[str] = []
    if analysis.get("dominant_framing"):
        parts.append(f"SERP framing is {analysis['dominant_framing']}")
    parts.append(
        f"{confidence['sources_eligible']}/{confidence['sources_retrieved']} sources "
        f"passed relevance")
    parts.append(
        f"{confidence.get('supported', 0)} of {confidence.get('claims_total', 0)} "
        f"atomic claims supported")
    return "; ".join(parts) if parts else None
