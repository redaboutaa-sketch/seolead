"""SEO Opportunity Score v1.

A prioritisation heuristic. **Not a prediction**, and the output says so.

Three rules keep it honest:

1. **Unknown never becomes zero.** A missing input is dropped from the weighted
   average and named in `missing_inputs`, so a score built from three known
   components is visibly different from one built from seven. A component silently
   scored 0 would drag the total down and look like evidence of a bad opportunity.

2. **Components are stored separately.** An operator who disagrees can see which
   part they disagree with.

3. **`confidence` is the share of weight actually measured**, so a high score with
   low confidence reads as "promising, poorly evidenced" rather than as a fact.

The weights are a starting position, not a finding. Phase 7 is meant to replace
them with weights learned from real Prospect 360 conversion data; until then they
encode the mission's stated preference for business value over raw traffic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import SearchIntent
from app.schemas.serp import KeywordMetric
from app.verticals.profile import VerticalProfile

SCORE_VERSION = "v1"

# Deliberately favours intent and business fit over volume. A keyword with 300
# highly qualified searches should outrank an informational one with 10,000.
WEIGHTS: dict[str, float] = {
    "commercial_intent": 0.25,
    "business_relevance": 0.20,
    "conversion_potential": 0.15,
    "content_gap": 0.15,
    "serp_opportunity": 0.10,
    "search_demand": 0.10,
    "competition": 0.05,
}


@dataclass
class Component:
    code: str
    value: float | None          # 0..100, or None when unknown
    weight: float
    rationale: str

    @property
    def known(self) -> bool:
        return self.value is not None

    def as_dict(self) -> dict:
        return {"code": self.code, "value": self.value, "weight": self.weight,
                "known": self.known, "rationale": self.rationale}


@dataclass
class OpportunityScore:
    overall: int | None
    confidence: float
    components: list[Component] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    version: str = SCORE_VERSION

    def as_dict(self) -> dict:
        return {
            "overall_score": self.overall,
            "confidence": round(self.confidence, 3),
            "version": self.version,
            "components": [c.as_dict() for c in self.components],
            "missing_inputs": self.missing_inputs,
            "known_component_count": sum(1 for c in self.components if c.known),
            "total_component_count": len(self.components),
            "interpretation": (
                "Prioritisation heuristic, not a prediction. Confidence is the "
                "share of scoring weight actually measured; the rest is unknown "
                "and was excluded rather than assumed."
            ),
        }


_INTENT_SCORES = {
    SearchIntent.TRANSACTIONAL: 100.0,
    SearchIntent.COMMERCIAL: 85.0,
    SearchIntent.LOCAL: 70.0,
    SearchIntent.NAVIGATIONAL: 25.0,
    SearchIntent.INFORMATIONAL: 40.0,
}


def _metric(metrics: list[KeywordMetric], metric_type: str) -> KeywordMetric | None:
    for metric in metrics:
        if metric.metric_type == metric_type and (
            metric.value is not None or metric.value_text is not None
        ):
            return metric
    return None


def compute(
    *,
    intent: SearchIntent,
    profile: VerticalProfile,
    serp_analysis: dict,
    keyword_metrics: list[KeywordMetric],
    eligible_evidence_count: int,
    topic_alignment: float | None = None,
) -> OpportunityScore:
    components: list[Component] = []
    missing: list[str] = []

    # ── Commercial intent ────────────────────────────────────────────────────
    components.append(Component(
        "commercial_intent", _INTENT_SCORES.get(intent, 40.0),
        WEIGHTS["commercial_intent"],
        f"Search intent classified {intent.value}.",
    ))

    # ── Business relevance ───────────────────────────────────────────────────
    if topic_alignment is not None:
        components.append(Component(
            "business_relevance", round(topic_alignment * 100, 1),
            WEIGHTS["business_relevance"],
            "Mean relevance of retrieved sources to the query.",
        ))
    else:
        components.append(Component("business_relevance", None,
                                    WEIGHTS["business_relevance"],
                                    "No relevance signal available."))
        missing.append("business_relevance")

    # ── Conversion potential ─────────────────────────────────────────────────
    # Derived from whether the vertical has a CTA matching this intent — a query
    # we cannot convert is not an opportunity however well it ranks.
    matching_ctas = [c for c in profile.cta_options if intent.value in c.intents]
    if profile.cta_options:
        value = 90.0 if matching_ctas else 40.0
        components.append(Component(
            "conversion_potential", value, WEIGHTS["conversion_potential"],
            (f"{len(matching_ctas)} CTA(s) configured for {intent.value} intent."
             if matching_ctas else
             f"No CTA configured for {intent.value} intent in this vertical."),
        ))
    else:
        components.append(Component("conversion_potential", None,
                                    WEIGHTS["conversion_potential"],
                                    "Vertical defines no CTA options."))
        missing.append("conversion_potential")

    # ── Content gap ──────────────────────────────────────────────────────────
    organic_count = serp_analysis.get("organic_count", 0)
    if organic_count:
        gaps = serp_analysis.get("content_gap") or []
        # Four gap checks are performed; each unfilled shape is an opening.
        value = min(100.0, 25.0 * len(gaps))
        components.append(Component(
            "content_gap", value, WEIGHTS["content_gap"],
            f"{len(gaps)} unfilled page shape(s) in the top results: "
            f"{'; '.join(gaps) if gaps else 'none'}.",
        ))
    else:
        components.append(Component("content_gap", None, WEIGHTS["content_gap"],
                                    "No SERP results to analyse."))
        missing.append("content_gap")

    # ── SERP opportunity ─────────────────────────────────────────────────────
    if organic_count:
        distinct = serp_analysis.get("distinct_domains", organic_count)
        # A page held by few domains is harder to enter than a fragmented one.
        fragmentation = distinct / organic_count if organic_count else 0.0
        features = serp_analysis.get("serp_features") or []
        # Feature-heavy SERPs push organic results down.
        feature_penalty = min(30.0, 6.0 * len(features))
        value = max(0.0, min(100.0, fragmentation * 100 - feature_penalty))
        components.append(Component(
            "serp_opportunity", round(value, 1), WEIGHTS["serp_opportunity"],
            f"{distinct} distinct domains across {organic_count} results; "
            f"{len(features)} SERP feature(s) competing for attention.",
        ))
    else:
        components.append(Component("serp_opportunity", None,
                                    WEIGHTS["serp_opportunity"],
                                    "No SERP results to analyse."))
        missing.append("serp_opportunity")

    # ── Search demand ────────────────────────────────────────────────────────
    volume = _metric(keyword_metrics, "search_volume")
    if volume and volume.value is not None:
        # Log-shaped: 10 → ~20, 100 → ~40, 1 000 → ~60, 10 000 → ~80.
        import math
        value = min(100.0, 20.0 * math.log10(max(volume.value, 1.0) + 1))
        components.append(Component(
            "search_demand", round(value, 1), WEIGHTS["search_demand"],
            f"{int(volume.value)} monthly searches reported by {volume.provider}.",
        ))
    else:
        components.append(Component("search_demand", None, WEIGHTS["search_demand"],
                                    "No search-volume metric available — UNKNOWN, "
                                    "not zero."))
        missing.append("search_demand")

    # ── Competition ──────────────────────────────────────────────────────────
    competition = _metric(keyword_metrics, "competition_index")
    if competition and competition.value is not None:
        components.append(Component(
            "competition", round(max(0.0, 100.0 - competition.value), 1),
            WEIGHTS["competition"],
            f"Competition index {competition.value} reported by "
            f"{competition.provider}; scored inversely.",
        ))
    else:
        components.append(Component("competition", None, WEIGHTS["competition"],
                                    "No competition metric available."))
        missing.append("competition")

    # ── Weighted mean over KNOWN components only ─────────────────────────────
    known = [c for c in components if c.known]
    known_weight = sum(c.weight for c in known)
    total_weight = sum(c.weight for c in components)

    if known_weight <= 0:
        return OpportunityScore(overall=None, confidence=0.0, components=components,
                                missing_inputs=missing)

    weighted = sum((c.value or 0.0) * c.weight for c in known) / known_weight
    confidence = known_weight / total_weight if total_weight else 0.0

    if eligible_evidence_count == 0:
        # Not a scoring penalty — a statement. A keyword we cannot research is not
        # actionable, whatever the SERP suggests.
        missing.append("eligible_evidence")

    return OpportunityScore(overall=int(round(weighted)), confidence=confidence,
                            components=components, missing_inputs=missing)
