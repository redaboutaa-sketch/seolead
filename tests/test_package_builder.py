"""ResearchPackage assembly.

The package is where provenance is fixed for everything downstream. These tests
assert the accounting is honest: a partial observation is flagged as partial, an
unsupported fact is not marked supported, and a package with no evidence says so
instead of looking like a package with nothing to report.
"""
from __future__ import annotations

from app.core.enums import Observability, SearchIntent, SourceState
from app.providers.research.last30days_normalizer import normalize
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.services.package_builder import build_package_payload


def test_confidence_summary_separates_the_four_outcome_classes(envelope, solar_profile):
    result = normalize(envelope, query="prix panneaux solaires Belgique",
                       market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)
    summary = package["confidence_summary"]

    # web and reddit both returned items; the count is of sources that
    # actually produced something, not of states that permit it.
    assert summary["source_types_with_items"] == 2
    assert summary["source_types_clean_empty"] == 1       # youtube
    assert summary["source_types_degraded"] == 6
    assert summary["source_types_unconfigured"] == 1      # polymarket
    assert summary["partial_observation"] is True


def test_facts_carry_their_observability_into_the_package(envelope, solar_profile):
    result = normalize(envelope, query="q", market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)

    by_ref = {f["source_ref"]: f for f in package["facts"]}
    assert by_ref["l30d-001"]["observability"] == Observability.OBSERVED.value
    assert by_ref["l30d-004"]["observability"] == Observability.UNKNOWN.value


def test_only_observed_facts_with_a_resolving_source_are_supported(envelope,
                                                                   solar_profile):
    result = normalize(envelope, query="q", market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)

    for fact in package["facts"]:
        if fact["supported"]:
            assert fact["observability"] == Observability.OBSERVED.value
            assert fact["source_ref"] is not None

    # The contradicted claim about a regional subsidy must never be supported.
    contradicted = next(f for f in package["facts"] if f["source_ref"] == "l30d-004")
    assert contradicted["supported"] is False


def test_dangling_source_reference_is_not_supported(solar_profile):
    """A fact pointing at a source that is not in the package cannot support
    anything, even if it claims to be OBSERVED."""
    result = ResearchProviderResult(
        provider="test", query="q", market="BE", language="fr", status="SUCCEEDED",
        sources=[NormalizedSource(source_type="web", state=SourceState.OK,
                                  url="https://example.invalid/a", candidate_id="real")],
        facts=[NormalizedFact(fact="An orphaned claim.",
                              observability=Observability.OBSERVED,
                              source_ref="does-not-exist")],
        source_outcomes=[SourceOutcome(source_type="web", state=SourceState.OK,
                                       item_count=1)],
    )
    package = build_package_payload(result, intent=SearchIntent.INFORMATIONAL,
                                    profile=solar_profile)
    assert package["facts"][0]["supported"] is False
    assert package["facts"][0]["source_ref"] is None


def test_empty_research_says_so_explicitly(solar_profile):
    result = ResearchProviderResult(
        provider="test", query="q", market="BE", language="fr", status="SUCCEEDED",
        source_outcomes=[SourceOutcome(source_type="web",
                                       state=SourceState.NO_RESULTS)],
    )
    package = build_package_payload(result, intent=SearchIntent.INFORMATIONAL,
                                    profile=solar_profile)
    joined = " ".join(package["unresolved_questions"])
    assert "No supported facts" in joined
    assert "model knowledge alone" in joined


def test_unresolved_list_names_degraded_and_unconfigured_sources(envelope,
                                                                 solar_profile):
    result = normalize(envelope, query="q", market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)
    joined = " ".join(package["unresolved_questions"])
    assert "not evidence of absence" in joined
    assert "was not configured" in joined


def test_provenance_records_the_engine_build(envelope, solar_profile):
    result = normalize(envelope, query="q", market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)
    provenance = package["provider_provenance"]
    assert provenance["engine_commit"] == "52f53312ff2f272e16bbc1785e1c04f9d9c19b31"
    assert provenance["provider"] == "last30days"
    assert len(provenance["source_outcomes"]) == 10


def test_published_at_stays_absent_when_unknown(envelope, solar_profile):
    result = normalize(envelope, query="q", market="BE", language="fr")
    package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                    profile=solar_profile)
    undated = next(s for s in package["sources"] if s["ref"] == "l30d-005")
    assert undated["published_at"] is None
