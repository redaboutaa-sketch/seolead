"""Multi-vertical isolation.

The whole architecture rests on one claim: the pipeline has no vertical-specific
branching. These tests are the evidence. Every one runs the same code path over
two profiles that share no market, no language, no vocabulary and no restricted
claims, and asserts the behaviour differs *only* where the configuration differs.

If someone later writes `if vertical == "SOLAR_BE"` in a service, the generic
vertical stops producing coherent output and these fail.
"""
from __future__ import annotations

import pytest

from app.core.enums import ContentType, SearchIntent
from app.services.brief_service import build_brief_payload
from app.services.intent import classify_intent, select_content_type
from app.verticals.profile import available_profiles, load_profile


def _package(query: str, intent: SearchIntent, language: str, market: str) -> dict:
    return {
        "query": query, "market": market, "language": language,
        "intent": intent.value,
        "facts": [{"fact": "A retrieved and dated statement about the topic.",
                   "evidence_type": "reported", "observability": "OBSERVED",
                   "confidence": 0.9, "source_ref": "s1", "supported": True}],
        "sources": [{"ref": "s1", "source_type": "web", "state": "ok",
                     "url": "https://example.invalid/a", "title": "A source",
                     "published_at": "2026-08-01T00:00:00+00:00",
                     "freshness_verdict": "current", "confidence": 0.9}],
        "user_questions": ["A theme observed in the research"],
        "unresolved_questions": [],
        "confidence_summary": {"partial_observation": False},
    }


def test_both_profiles_load():
    assert set(available_profiles()) >= {"SOLAR_BE", "TEST_GENERIC"}


@pytest.mark.parametrize("code", ["SOLAR_BE", "TEST_GENERIC"])
def test_pipeline_stages_run_for_any_vertical(code):
    """The same functions produce a complete brief for either vertical."""
    profile = load_profile(code)
    query = "prix panneaux solaires Belgique" if code == "SOLAR_BE" else "price of a generic service"

    intent = classify_intent(query, profile)
    package = _package(query, intent, profile.default_language, profile.market)
    brief = build_brief_payload(package, profile=profile, query=query)

    assert brief["primary_query"] == query
    assert brief["content_type"] in {t.value for t in ContentType}
    assert brief["target_audience"] == profile.target_audience
    assert brief["objective"] == profile.business_objective
    assert brief["recommended_slug"]
    assert brief["outline"]
    assert brief["required_facts"], "supported facts must reach the brief"


def test_intent_vocabulary_comes_from_the_profile():
    """'prix' classifies commercially for solar; it is meaningless to the generic
    vertical, whose commercial vocabulary is English."""
    solar = load_profile("SOLAR_BE")
    generic = load_profile("TEST_GENERIC")

    assert classify_intent("prix panneaux solaires", solar) is SearchIntent.COMMERCIAL
    assert classify_intent("prix panneaux solaires", generic) is SearchIntent.INFORMATIONAL
    assert classify_intent("price of the service", generic) is SearchIntent.COMMERCIAL


def test_restricted_claims_are_per_vertical():
    """Solar restricts subsidies; the generic vertical has never heard of them."""
    solar = load_profile("SOLAR_BE")
    generic = load_profile("TEST_GENERIC")

    assert "prime" in solar.restricted_claims
    assert "prime" not in generic.restricted_claims
    assert "warranty" in generic.restricted_claims
    assert "warranty" not in solar.restricted_claims


def test_cautionary_claims_reflect_the_active_vertical():
    solar = load_profile("SOLAR_BE")
    generic = load_profile("TEST_GENERIC")

    solar_brief = build_brief_payload(
        _package("prix panneaux solaires Belgique", SearchIntent.COMMERCIAL, "fr", "BE"),
        profile=solar, query="prix panneaux solaires Belgique")
    generic_brief = build_brief_payload(
        _package("price of the service", SearchIntent.COMMERCIAL, "en", "FR"),
        profile=generic, query="price of the service")

    solar_topics = {c["topic"] for c in solar_brief["cautionary_claims"]}
    generic_topics = {c["topic"] for c in generic_brief["cautionary_claims"]}

    assert "certificat vert" in solar_topics
    assert solar_topics.isdisjoint(generic_topics)


def test_content_type_selection_respects_profile_preferences():
    """TEST_GENERIC does not offer LANDING_PAGE, so a commercial query cannot
    become one — the selector must fall back inside the profile's own list."""
    generic = load_profile("TEST_GENERIC")
    chosen = select_content_type("price of the service", SearchIntent.COMMERCIAL, generic)
    assert chosen in set(generic.selectable_content_types())
    assert chosen is not ContentType.LANDING_PAGE


def test_phase2_never_selects_an_unsupported_content_type():
    """A profile may name SIMULATOR; Phase 2 must still never emit one."""
    solar = load_profile("SOLAR_BE")
    solar.preferred_content_types.append(ContentType.SIMULATOR)
    try:
        assert ContentType.SIMULATOR not in solar.selectable_content_types()
        for query, intent in [("prix panneaux solaires", SearchIntent.COMMERCIAL),
                              ("comment installer", SearchIntent.INFORMATIONAL),
                              ("comparatif onduleurs", SearchIntent.COMMERCIAL)]:
            assert select_content_type(query, intent, solar) in {
                ContentType.ARTICLE, ContentType.GUIDE, ContentType.COMPARISON,
                ContentType.LANDING_PAGE,
            }
    finally:
        solar.preferred_content_types.remove(ContentType.SIMULATOR)
