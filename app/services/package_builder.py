"""ResearchProviderResult → ResearchPackage.

Fully deterministic, and deliberately so. This is the step where provenance is
fixed; if an LLM touched it, the guarantee that every fact in the package traces to
a retrieved source would rest on a model's good behaviour rather than on code.

The `confidence_summary` it produces is the honest accounting the whole pipeline
depends on: how many sources produced items, how many completed cleanly with
nothing, how many could not be observed, and how many were never configured. A
reader of the package can tell the difference without re-deriving it.
"""
from __future__ import annotations

from app.core.enums import Observability, SearchIntent
from app.schemas.research import ResearchProviderResult
from app.verticals.profile import VerticalProfile


def build_package_payload(
    result: ResearchProviderResult,
    *,
    intent: SearchIntent,
    profile: VerticalProfile,
) -> dict:
    """Assemble the sealed package body.

    Returns a plain dict rather than an ORM object so the builder stays pure and
    unit-testable without a database.
    """
    # Sources keyed by candidate_id so facts can point at them by reference.
    source_entries = []
    for index, source in enumerate(result.sources):
        source_entries.append({
            "ref": source.candidate_id or f"src-{index:03d}",
            "source_type": source.source_type,
            "state": source.state.value,
            "url": source.url,
            "title": source.title,
            # Stays absent when unknown. Never defaulted to a date.
            "published_at": source.published_at.isoformat() if source.published_at else None,
            "freshness_verdict": (
                source.freshness_verdict.value if source.freshness_verdict else None
            ),
            "confidence": source.confidence,
        })

    known_refs = {entry["ref"] for entry in source_entries}

    fact_entries = []
    for fact in result.facts:
        ref = fact.source_ref if fact.source_ref in known_refs else None
        fact_entries.append({
            "fact": fact.fact,
            "evidence_type": fact.evidence_type,
            "observability": fact.observability.value,
            "confidence": fact.confidence,
            "source_ref": ref,
            # A fact whose source reference does not resolve is not usable as
            # support, and the writer must be able to see that at a glance.
            "supported": ref is not None
            and fact.observability is Observability.OBSERVED,
        })

    observed = sum(1 for f in fact_entries if f["observability"] == Observability.OBSERVED.value)
    estimated = sum(1 for f in fact_entries if f["observability"] == Observability.ESTIMATED.value)
    unknown = sum(1 for f in fact_entries if f["observability"] == Observability.UNKNOWN.value)

    confidence_summary = {
        "facts_total": len(fact_entries),
        "facts_observed": observed,
        "facts_estimated": estimated,
        "facts_unknown": unknown,
        "facts_supported": sum(1 for f in fact_entries if f["supported"]),
        "sources_total": len(source_entries),
        # Counts sources that ACTUALLY returned an item, not sources whose state
        # permits items. A real run showed `reddit: partial` with zero items, which
        # the state-based count reported as a source "with items" — overstating
        # coverage in exactly the direction that matters.
        "source_types_with_items": sum(
            1 for o in result.source_outcomes if o.item_count > 0
        ),
        "source_types_returning_nothing_despite_ok_state": sum(
            1 for o in result.source_outcomes
            if o.state.produced_items and o.item_count == 0
        ),
        "source_types_clean_empty": len(result.clean_empty_sources),
        "source_types_degraded": len(result.degraded_sources),
        "source_types_unconfigured": len(result.unconfigured_sources),
        # The single most important flag in the package. True means: do not read
        # "no facts about X" as "X is not discussed".
        "partial_observation": result.is_partial,
    }

    unresolved = list(result.unresolved_data)
    if not fact_entries:
        unresolved.append(
            "No supported facts were retrieved for this query. Content must not be "
            "generated from model knowledge alone."
        )
    for claim in profile.restricted_claims:
        # Restricted topics start life unresolved. Only evidence removes them.
        if not any(claim.casefold() in f["fact"].casefold() for f in fact_entries):
            continue
        if not any(
            claim.casefold() in f["fact"].casefold() and f["supported"]
            for f in fact_entries
        ):
            unresolved.append(
                f"Topic '{claim}' appears in retrieved material but no supported, "
                f"dated source stands it up. It may not be asserted."
            )

    summary = None
    if result.user_questions:
        summary = "Themes observed: " + "; ".join(result.user_questions[:8])

    return {
        "query": result.query,
        "market": result.market,
        "language": result.language,
        "intent": intent.value,
        "summary": summary,
        "facts": fact_entries,
        "sources": source_entries,
        "user_questions": result.user_questions,
        "unresolved_questions": unresolved,
        "confidence_summary": confidence_summary,
        "provider_provenance": {
            "provider": result.provider,
            "status": result.status,
            "engine_commit": result.engine_commit,
            "engine_version": result.engine_version,
            "duration_ms": result.duration_ms,
            "source_outcomes": [
                {"source_type": o.source_type, "state": o.state.value,
                 "item_count": o.item_count}
                for o in result.source_outcomes
            ],
            "metadata": result.provider_metadata,
        },
    }
