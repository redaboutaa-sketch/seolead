"""Provider capabilities and the routing policy.

Phase 2 had one research provider, so "the provider" and "research" meant the same
thing. Phase 3 has three with genuinely different jobs, and the lesson from the
Phase 2 live test is that treating them as interchangeable search APIs is how a
Hacker News post about a racing game ends up as evidence for a solar pricing query.

So downstream code asks for a *capability*, never for a provider by name, and the
policy that decides which providers run for a given query is deterministic and
readable. An LLM does not get to switch on a paid provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.enums import SearchIntent
from app.verticals.profile import VerticalProfile


class ProviderCapability(StrEnum):
    SERP = "SERP"
    KEYWORD_METRICS = "KEYWORD_METRICS"
    WEB_RESEARCH = "WEB_RESEARCH"
    CONTENT_EXTRACTION = "CONTENT_EXTRACTION"
    RECENT_DISCUSSION = "RECENT_DISCUSSION"
    COMMUNITY_SIGNAL = "COMMUNITY_SIGNAL"


# What each implementation actually provides. Declared once, here, rather than
# scattered across the call sites that would otherwise have to remember.
PROVIDER_CAPABILITIES: dict[str, frozenset[ProviderCapability]] = {
    "dataforseo": frozenset({ProviderCapability.SERP,
                             ProviderCapability.KEYWORD_METRICS}),
    "tavily": frozenset({ProviderCapability.WEB_RESEARCH,
                         ProviderCapability.CONTENT_EXTRACTION}),
    "last30days": frozenset({ProviderCapability.RECENT_DISCUSSION,
                             ProviderCapability.COMMUNITY_SIGNAL}),
}


@dataclass(frozen=True)
class ProviderPlan:
    """The deterministic decision about which providers run for one job."""

    serp: bool
    web_research: bool
    community: bool
    keyword_metrics: bool
    reasons: dict[str, str] = field(default_factory=dict)

    def selected(self) -> list[str]:
        chosen = []
        if self.serp:
            chosen.append("dataforseo")
        if self.web_research:
            chosen.append("tavily")
        if self.community:
            chosen.append("last30days")
        return chosen

    def as_dict(self) -> dict:
        return {
            "serp": self.serp, "web_research": self.web_research,
            "community": self.community, "keyword_metrics": self.keyword_metrics,
            "selected": self.selected(), "reasons": self.reasons,
        }


def plan_providers(
    *,
    query: str,
    intent: SearchIntent,
    profile: VerticalProfile,
    force_community: bool | None = None,
) -> ProviderPlan:
    """Decide which providers to call. Deterministic, and cheap to audit.

    The community provider is the one worth being careful about. Phase 2 measured
    that Last30Days returns tech-community discussion — genuinely useful when the
    audience *is* that community, and actively harmful for consumer commercial
    queries, where it supplied a racing-game post as the only "evidence". So it is
    opt-in per vertical, not on by default.
    """
    reasons: dict[str, str] = {}

    # SERP is the backbone: it is what tells us what the searcher actually sees,
    # and it is the only source of PAA and competitor structure.
    serp = True
    reasons["dataforseo"] = "SERP structure is required for every query"

    # Web research grounds the factual claims. Always wanted.
    web_research = True
    reasons["tavily"] = "web research supplies the source-backed evidence set"

    # Community signal: only where the vertical says its audience lives there.
    if force_community is not None:
        community = force_community
        reasons["last30days"] = (
            "explicitly forced on by the operator" if force_community
            else "explicitly forced off by the operator"
        )
    elif not profile.community_research_enabled:
        community = False
        reasons["last30days"] = (
            f"vertical {profile.code} does not enable community research "
            f"(its audience is not the technical community this provider indexes)"
        )
    elif intent in (SearchIntent.COMMERCIAL, SearchIntent.TRANSACTIONAL):
        # Even in an enabled vertical, a pricing query is not a discussion topic.
        community = False
        reasons["last30days"] = (
            f"{intent.value} intent — community discussion rarely carries "
            f"purchase-stage facts"
        )
    else:
        community = True
        reasons["last30days"] = (
            f"vertical enables community research and intent is {intent.value}"
        )

    keyword_metrics = profile.keyword_metrics_enabled
    reasons["keyword_metrics"] = (
        "enabled for this vertical" if keyword_metrics
        else "disabled for this vertical — metrics cost money per call"
    )

    return ProviderPlan(serp=serp, web_research=web_research, community=community,
                        keyword_metrics=keyword_metrics, reasons=reasons)
