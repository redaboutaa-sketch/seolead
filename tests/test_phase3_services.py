"""Provider routing, source quality, claim risk, package V2, SERP analysis,
opportunity score, factual QA V2, cost control and freshness."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.core.enums import Observability, SearchIntent, SourceState
from app.providers.capabilities import (PROVIDER_CAPABILITIES, ProviderCapability,
                                        plan_providers)
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.schemas.serp import (KeywordMetric, OrganicResult, SerpQuestion,
                              SerpSnapshot)
from app.services import opportunity_score, serp_analysis
from app.services.claim_risk import (ClaimRisk, SupportStatus, assess,
                                     classify_claim, evidence_is_sufficient)
from app.services.factual_qa import extract_claims, run_factual_qa
from app.services.package_builder_v2 import build_package_v2
from app.services.provider_usage import (JobBudget, ProviderBudgetExceeded,
                                         UsageRecorder)
from app.services.research_cache import (ResearchKind, is_fresh, serp_cache_key)
from app.services.source_quality import SourceQuality, classify_domain

QUERY = "prix panneaux solaires Belgique"


def make_snapshot(organic=None, questions=None) -> SerpSnapshot:
    return SerpSnapshot(
        provider="dataforseo", query=QUERY, location_code=2056,
        location_name="Belgium", language_code="fr", device="desktop",
        retrieved_at=datetime.now(timezone.utc),
        organic=organic or [], questions=questions or [], total_items=10,
    )


# ─── Provider routing ────────────────────────────────────────────────────────

class TestProviderRouting:
    def test_capabilities_are_declared_per_provider(self):
        assert ProviderCapability.SERP in PROVIDER_CAPABILITIES["dataforseo"]
        assert ProviderCapability.WEB_RESEARCH in PROVIDER_CAPABILITIES["tavily"]
        assert ProviderCapability.RECENT_DISCUSSION in \
            PROVIDER_CAPABILITIES["last30days"]
        # DataForSEO is not a web-research provider, and Tavily is not a SERP one.
        assert ProviderCapability.WEB_RESEARCH not in PROVIDER_CAPABILITIES["dataforseo"]
        assert ProviderCapability.SERP not in PROVIDER_CAPABILITIES["tavily"]

    def test_solar_commercial_query_skips_community_research(self, solar_profile):
        """The Phase 2 lesson, encoded as policy."""
        plan = plan_providers(query=QUERY, intent=SearchIntent.COMMERCIAL,
                              profile=solar_profile)
        assert plan.serp is True
        assert plan.web_research is True
        assert plan.community is False
        assert "last30days" not in plan.selected()
        assert "does not enable community research" in plan.reasons["last30days"]

    def test_enabled_vertical_uses_community_for_informational_intent(
            self, generic_profile):
        plan = plan_providers(query="how do agents work",
                              intent=SearchIntent.INFORMATIONAL,
                              profile=generic_profile)
        assert plan.community is True
        assert "last30days" in plan.selected()

    def test_even_enabled_verticals_skip_community_for_commercial_intent(
            self, generic_profile):
        plan = plan_providers(query="price of the service",
                              intent=SearchIntent.COMMERCIAL,
                              profile=generic_profile)
        assert plan.community is False
        assert "purchase-stage facts" in plan.reasons["last30days"]

    def test_operator_can_force_community_on(self, solar_profile):
        plan = plan_providers(query=QUERY, intent=SearchIntent.COMMERCIAL,
                              profile=solar_profile, force_community=True)
        assert plan.community is True
        assert "forced on" in plan.reasons["last30days"]

    def test_keyword_metrics_follow_the_vertical(self, solar_profile,
                                                 generic_profile):
        assert plan_providers(query=QUERY, intent=SearchIntent.COMMERCIAL,
                              profile=solar_profile).keyword_metrics is True
        assert plan_providers(query="x", intent=SearchIntent.COMMERCIAL,
                              profile=generic_profile).keyword_metrics is False


# ─── Source quality ──────────────────────────────────────────────────────────

class TestSourceQuality:
    @pytest.mark.parametrize("url,expected", [
        ("https://energie.wallonie.be/prix", SourceQuality.OFFICIAL),
        ("https://economie.fgov.be/x", SourceQuality.OFFICIAL),
        ("https://ec.europa.eu/energy", SourceQuality.OFFICIAL),
        ("https://kuleuven.be/study", SourceQuality.INSTITUTIONAL),
        ("https://www.reddit.com/r/solar", SourceQuality.COMMUNITY),
        ("https://news.ycombinator.com/item", SourceQuality.COMMUNITY),
        ("https://solar-energie-expert.be/guide", SourceQuality.SPECIALIST),
        ("https://random-installer.be/devis", SourceQuality.COMMERCIAL),
    ])
    def test_domain_classification(self, url, expected):
        assert classify_domain(url) is expected

    def test_ranking_is_not_authority(self):
        """A source's SERP position cannot influence its quality.

        Google ranks for usefulness and SEO, not for whether a claim is
        checkable. The guarantee is structural: `classify_domain` has no way to
        learn a rank, because it is never given one.
        """
        import inspect

        params = inspect.signature(classify_domain).parameters
        assert set(params) == {"url", "source_type"}

        # And a #1 commercial result still classifies below a #10 official one.
        top_commercial = classify_domain("https://random-installer.be/devis")
        low_official = classify_domain("https://energie.wallonie.be/prix")
        assert low_official.rank > top_commercial.rank

    def test_commercial_is_classified_not_rejected(self):
        assert classify_domain("https://installer.be/x") is SourceQuality.COMMERCIAL
        assert SourceQuality.COMMERCIAL.rank > SourceQuality.UNKNOWN.rank

    def test_community_channel_without_url(self):
        assert classify_domain(None, source_type="reddit") is SourceQuality.COMMUNITY

    def test_quality_ordering(self):
        assert (SourceQuality.OFFICIAL.rank > SourceQuality.INSTITUTIONAL.rank
                > SourceQuality.SPECIALIST.rank > SourceQuality.COMMERCIAL.rank
                > SourceQuality.COMMUNITY.rank > SourceQuality.UNKNOWN.rank)


# ─── Claim risk ──────────────────────────────────────────────────────────────

class TestClaimRisk:
    @pytest.mark.parametrize("claim", [
        "La prime régionale s'élève à 1 500 euros.",
        "La TVA applicable est de 6%.",
        "L'installation est obligatoire selon la réglementation.",
        "Le rendement est garanti sur 25 ans.",
        "Vous bénéficiez d'un subside de la Région.",
    ])
    def test_regulatory_and_financial_claims_are_high_risk(self, claim,
                                                            solar_profile):
        assert classify_claim(claim, solar_profile) is ClaimRisk.HIGH

    def test_quantified_ordinary_claim_is_medium(self, solar_profile):
        assert classify_claim(
            "Une installation typique produit 3 500 kWh par an.",
            solar_profile) is ClaimRisk.MEDIUM

    def test_unquantified_explanation_is_low(self, solar_profile):
        assert classify_claim(
            "Les panneaux sont généralement orientés vers le sud.",
            solar_profile) is ClaimRisk.LOW

    def test_high_risk_requires_institutional_or_better(self):
        assert evidence_is_sufficient(ClaimRisk.HIGH, SourceQuality.OFFICIAL)
        assert evidence_is_sufficient(ClaimRisk.HIGH, SourceQuality.INSTITUTIONAL)
        assert not evidence_is_sufficient(ClaimRisk.HIGH, SourceQuality.COMMERCIAL)
        assert not evidence_is_sufficient(ClaimRisk.HIGH, SourceQuality.COMMUNITY)

    def test_low_risk_accepts_any_relevant_source(self):
        assert evidence_is_sufficient(ClaimRisk.LOW, SourceQuality.COMMUNITY)

    def test_assess_explains_itself(self, solar_profile):
        risk, sufficient, reason = assess(
            "La prime est de 1 500 euros.", solar_profile, SourceQuality.COMMERCIAL)
        assert risk is ClaimRisk.HIGH
        assert sufficient is False
        assert "INSTITUTIONAL" in reason

    def test_claim_risk_vocabulary_is_per_vertical(self, generic_profile):
        """The generic vertical restricts 'warranty', not Belgian subsidies."""
        assert classify_claim("The warranty covers ten years.",
                              generic_profile) is ClaimRisk.HIGH


# ─── SERP analysis ───────────────────────────────────────────────────────────

class TestSerpAnalysis:
    def test_page_shapes_are_counted(self, solar_profile):
        snapshot = make_snapshot(organic=[
            OrganicResult(rank_group=1, domain="a.be", url="https://a.be/1",
                          title="Calculateur de prix pour panneaux solaires"),
            OrganicResult(rank_group=2, domain="b.be", url="https://b.be/2",
                          title="Comparatif des installateurs"),
            OrganicResult(rank_group=3, domain="c.com", url="https://c.com/3",
                          title="Guide: comment choisir ses panneaux"),
        ])
        analysis = serp_analysis.analyse_serp(snapshot, solar_profile)
        assert analysis["shape_counts"]["calculator"] == 1
        assert analysis["shape_counts"]["comparison"] == 1
        assert analysis["shape_counts"]["guide"] == 1
        assert analysis["shape_counts"]["belgian_domain"] == 2

    def test_content_gap_names_missing_shapes(self, solar_profile):
        snapshot = make_snapshot(organic=[
            OrganicResult(rank_group=1, domain="a.com", url="https://a.com/1",
                          title="Un article générique"),
        ])
        analysis = serp_analysis.analyse_serp(snapshot, solar_profile)
        gap = " ".join(analysis["content_gap"])
        assert "calculator" in gap.lower()
        assert "comparison" in gap.lower()
        assert "belgian" in gap.lower()

    def test_questions_are_carried_through(self, solar_profile):
        snapshot = make_snapshot(
            organic=[OrganicResult(rank_group=1, domain="a.be",
                                   url="https://a.be/1", title="Prix")],
            questions=[SerpQuestion(text="Combien coûte une installation ?",
                                    kind="PAA"),
                       SerpQuestion(text="prix panneaux 2026", kind="RELATED")])
        analysis = serp_analysis.analyse_serp(snapshot, solar_profile)
        assert analysis["questions"] == ["Combien coûte une installation ?"]
        assert analysis["related_searches"] == ["prix panneaux 2026"]

    def test_empty_serp_is_handled(self, solar_profile):
        analysis = serp_analysis.analyse_serp(make_snapshot(), solar_profile)
        assert analysis["organic_count"] == 0
        assert analysis["competitor_pages"] == []


# ─── Package V2 ──────────────────────────────────────────────────────────────

def _research_result(sources, facts) -> ResearchProviderResult:
    return ResearchProviderResult(
        provider="tavily", query=QUERY, market="BE", language="fr",
        status="SUCCEEDED", sources=sources, facts=facts,
        source_outcomes=[SourceOutcome(source_type="web", state=SourceState.OK,
                                       item_count=len(sources))])


class TestPackageV2:
    def test_irrelevant_source_never_becomes_eligible(self, solar_profile):
        """The Phase 2 regression, at the package level."""
        result = _research_result(
            sources=[
                NormalizedSource(source_type="web", state=SourceState.OK,
                                 url="https://marnetto.net/dml",
                                 title="The making of a mod for Grand Prix Circuit",
                                 summary="Racing game modification notes.",
                                 candidate_id="racing"),
                NormalizedSource(source_type="web", state=SourceState.OK,
                                 url="https://energie.wallonie.be/prix",
                                 title="Prix des panneaux solaires en Wallonie",
                                 summary=("Le prix d'une installation de panneaux "
                                          "solaires dépend de la puissance."),
                                 published_at=datetime.now(timezone.utc),
                                 candidate_id="solar"),
            ],
            facts=[
                NormalizedFact(fact="The track editor supports 20 circuits.",
                               observability=Observability.OBSERVED,
                               source_ref="racing"),
                NormalizedFact(fact=("Le prix d'une installation de panneaux "
                                     "solaires dépend de la puissance installée."),
                               observability=Observability.OBSERVED,
                               source_ref="solar"),
            ])

        package = build_package_v2(
            query=QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        eligible_refs = {e["ref"] for e in package["eligible_evidence"]}
        rejected_refs = {r["ref"] for r in package["rejected_evidence"]}
        assert "racing" in rejected_refs
        assert "solar" in eligible_refs
        # And the racing claim did not survive into the fact set at all.
        assert all(f["source_ref"] != "racing" for f in package["facts"])

    def test_rejected_evidence_is_kept_with_its_reason(self, solar_profile):
        result = _research_result(
            sources=[NormalizedSource(source_type="web", state=SourceState.OK,
                                      url="https://marnetto.net/dml",
                                      title="Grand Prix Circuit mod",
                                      summary="Racing.", candidate_id="racing")],
            facts=[])
        package = build_package_v2(
            query=QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        rejected = package["rejected_evidence"][0]
        assert rejected["rejection_status"] == "IRRELEVANT"
        assert "matched only" in rejected["rejection_reason"]

    def test_high_risk_claim_from_a_commercial_source_is_not_supported(
            self, solar_profile):
        result = _research_result(
            sources=[NormalizedSource(
                source_type="web", state=SourceState.OK,
                url="https://random-installer.be/primes",
                title="Primes pour panneaux solaires",
                summary="La prime régionale pour les panneaux solaires.",
                published_at=datetime.now(timezone.utc), candidate_id="s1")],
            facts=[NormalizedFact(
                fact="La prime régionale pour panneaux solaires est de 1 500 euros.",
                observability=Observability.OBSERVED, source_ref="s1")])

        package = build_package_v2(
            query=QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        fact = package["facts"][0]
        assert fact["claim_risk"] == ClaimRisk.HIGH.value
        assert fact["evidence_sufficient"] is False
        assert fact["supported"] is False
        assert any("HIGH-risk claim lacks sufficient evidence" in u
                   for u in package["unresolved_questions"])

    def test_high_risk_claim_from_an_official_source_is_supported(self,
                                                                   solar_profile):
        result = _research_result(
            sources=[NormalizedSource(
                source_type="web", state=SourceState.OK,
                url="https://energie.wallonie.be/primes",
                title="Primes photovoltaïques en Wallonie",
                summary="La prime régionale pour les panneaux solaires.",
                published_at=datetime.now(timezone.utc), candidate_id="s1")],
            facts=[NormalizedFact(
                fact=("La prime régionale pour les panneaux solaires est décrite "
                      "par le portail énergie."),
                observability=Observability.OBSERVED, source_ref="s1")])

        package = build_package_v2(
            query=QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        fact = package["facts"][0]
        assert fact["source_quality"] == SourceQuality.OFFICIAL.value
        assert fact["evidence_sufficient"] is True

    def test_confidence_summary_counts_the_gate(self, solar_profile):
        result = _research_result(
            sources=[
                NormalizedSource(source_type="web", state=SourceState.OK,
                                 url="https://a.be/1", title="Grand Prix mod",
                                 summary="Racing.", candidate_id="r1"),
                NormalizedSource(source_type="web", state=SourceState.OK,
                                 url="https://b.be/2",
                                 title="Prix des panneaux solaires",
                                 summary="Le prix des panneaux solaires varie.",
                                 candidate_id="r2"),
            ], facts=[])
        package = build_package_v2(
            query=QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        summary = package["confidence_summary"]
        assert summary["sources_retrieved"] == 2
        assert summary["sources_eligible"] == 1
        assert summary["sources_rejected"] == 1


# ─── Opportunity score ───────────────────────────────────────────────────────

class TestOpportunityScore:
    def test_unknown_inputs_are_excluded_not_zeroed(self, solar_profile):
        score = opportunity_score.compute(
            intent=SearchIntent.COMMERCIAL, profile=solar_profile,
            serp_analysis={"organic_count": 0}, keyword_metrics=[],
            eligible_evidence_count=0, topic_alignment=None)

        assert "search_demand" in score.missing_inputs
        assert score.confidence < 1.0
        for component in score.components:
            if component.code == "search_demand":
                assert component.value is None

    def test_confidence_rises_when_more_is_known(self, solar_profile):
        analysis = {"organic_count": 10, "distinct_domains": 9,
                    "content_gap": ["no calculator"], "serp_features": ["organic"]}
        metrics = [KeywordMetric(metric_type="search_volume", value=2400,
                                 observability=Observability.OBSERVED,
                                 provider="dataforseo"),
                   KeywordMetric(metric_type="competition_index", value=40,
                                 observability=Observability.OBSERVED,
                                 provider="dataforseo")]
        poor = opportunity_score.compute(
            intent=SearchIntent.COMMERCIAL, profile=solar_profile,
            serp_analysis={"organic_count": 0}, keyword_metrics=[],
            eligible_evidence_count=0)
        rich = opportunity_score.compute(
            intent=SearchIntent.COMMERCIAL, profile=solar_profile,
            serp_analysis=analysis, keyword_metrics=metrics,
            eligible_evidence_count=5, topic_alignment=0.8)

        assert rich.confidence > poor.confidence
        assert rich.overall is not None

    def test_commercial_intent_outranks_informational(self, solar_profile):
        analysis = {"organic_count": 10, "distinct_domains": 8,
                    "content_gap": [], "serp_features": []}
        commercial = opportunity_score.compute(
            intent=SearchIntent.COMMERCIAL, profile=solar_profile,
            serp_analysis=analysis, keyword_metrics=[], eligible_evidence_count=3,
            topic_alignment=0.8)
        informational = opportunity_score.compute(
            intent=SearchIntent.INFORMATIONAL, profile=solar_profile,
            serp_analysis=analysis, keyword_metrics=[], eligible_evidence_count=3,
            topic_alignment=0.8)
        assert commercial.overall > informational.overall

    def test_low_volume_high_intent_can_beat_high_volume_low_intent(self,
                                                                     solar_profile):
        """The mission's central scoring claim, made concrete."""
        analysis = {"organic_count": 10, "distinct_domains": 8,
                    "content_gap": [], "serp_features": []}
        niche = opportunity_score.compute(
            intent=SearchIntent.TRANSACTIONAL, profile=solar_profile,
            serp_analysis=analysis,
            keyword_metrics=[KeywordMetric(metric_type="search_volume", value=300,
                                           observability=Observability.OBSERVED,
                                           provider="dataforseo")],
            eligible_evidence_count=3, topic_alignment=0.9)
        broad = opportunity_score.compute(
            intent=SearchIntent.INFORMATIONAL, profile=solar_profile,
            serp_analysis=analysis,
            keyword_metrics=[KeywordMetric(metric_type="search_volume", value=10000,
                                           observability=Observability.OBSERVED,
                                           provider="dataforseo")],
            eligible_evidence_count=3, topic_alignment=0.9)
        assert niche.overall > broad.overall

    def test_score_is_labelled_a_heuristic(self, solar_profile):
        score = opportunity_score.compute(
            intent=SearchIntent.COMMERCIAL, profile=solar_profile,
            serp_analysis={"organic_count": 5, "distinct_domains": 5,
                           "content_gap": [], "serp_features": []},
            keyword_metrics=[], eligible_evidence_count=1)
        assert "not a prediction" in score.as_dict()["interpretation"]

    def test_score_stays_within_range(self, solar_profile):
        score = opportunity_score.compute(
            intent=SearchIntent.TRANSACTIONAL, profile=solar_profile,
            serp_analysis={"organic_count": 10, "distinct_domains": 10,
                           "content_gap": ["a", "b", "c", "d"],
                           "serp_features": []},
            keyword_metrics=[KeywordMetric(metric_type="search_volume",
                                           value=1_000_000,
                                           observability=Observability.OBSERVED,
                                           provider="dataforseo")],
            eligible_evidence_count=10, topic_alignment=1.0)
        assert 0 <= score.overall <= 100


# ─── Factual QA V2 ───────────────────────────────────────────────────────────

class TestFactualQAV2:
    def test_extracts_only_checkable_sentences(self):
        body = ("# Titre\n\nLes panneaux sont orientés vers le sud. "
                "Une installation coûte 8 500 € en moyenne. "
                "Le rendement atteint 20 %.")
        claims = extract_claims(body)
        assert len(claims) == 2
        assert all(any(c in claim for c in ("8 500", "20")) for claim in claims)

    def test_high_risk_unsupported_claim_blocks(self, solar_profile):
        draft = {"body": "# T\n\nLa prime régionale s'élève à 1 500 euros."}
        package = {"facts": [], "eligible_evidence": []}
        verdict = run_factual_qa(draft, package, solar_profile)
        assert verdict["status"] == "FAILED"
        assert verdict["blocking_issues"]

    def test_medium_risk_unsupported_claim_does_not_block(self, solar_profile):
        draft = {"body": "# T\n\nUne installation produit 3 500 kWh par an."}
        package = {
            "facts": [{"fact": "Une installation solaire produit de l'électricité.",
                       "supported": True, "source_quality": "SPECIALIST",
                       "source_ref": "s1"}],
            "eligible_evidence": [{"ref": "s1", "url": "https://x.be",
                                   "source_quality": "SPECIALIST"}],
        }
        verdict = run_factual_qa(draft, package, solar_profile)
        assert verdict["blocking_issues"] == []
        assert verdict["findings"]          # reported, not blocking

    def test_supported_claim_passes(self, solar_profile):
        draft = {"body": ("# T\n\nUne installation photovoltaïque résidentielle "
                          "coûte environ 8 500 euros selon la source.")}
        package = {
            "facts": [{"fact": ("Une installation photovoltaïque résidentielle "
                                "coûte environ 8 500 euros."),
                       "supported": True, "source_quality": "SPECIALIST",
                       "source_ref": "s1"}],
            "eligible_evidence": [{"ref": "s1", "url": "https://x.be",
                                   "source_quality": "SPECIALIST"}],
        }
        verdict = run_factual_qa(draft, package, solar_profile)
        assert verdict["status"] == "PASSED"
        assert verdict["claims"][0]["support_status"] == SupportStatus.SUPPORTED.value

    def test_conflicting_number_is_detected(self, solar_profile):
        """Evidence exists on the topic and states a different figure."""
        draft = {"body": ("# T\n\nUne installation photovoltaïque résidentielle "
                          "coûte environ 25 000 euros.")}
        package = {
            "facts": [{"fact": ("Une installation photovoltaïque résidentielle "
                                "coûte environ 8 500 euros."),
                       "supported": True, "source_quality": "SPECIALIST",
                       "source_ref": "s1"}],
            "eligible_evidence": [{"ref": "s1", "url": "https://x.be",
                                   "source_quality": "SPECIALIST"}],
        }
        verdict = run_factual_qa(draft, package, solar_profile)
        statuses = {c["support_status"] for c in verdict["claims"]}
        assert SupportStatus.CONFLICTING.value in statuses

    def test_claims_with_no_evidence_at_all_block(self, solar_profile):
        draft = {"body": "# T\n\nUne installation coûte 8 500 euros."}
        verdict = run_factual_qa(draft, {"facts": [], "eligible_evidence": []},
                                 solar_profile)
        assert any(f["code"] == "NO_ELIGIBLE_EVIDENCE"
                   for f in verdict["blocking_issues"])


# ─── Cost control and freshness ──────────────────────────────────────────────

class TestCostControl:
    def test_budget_stops_a_runaway_loop(self):
        budget = JobBudget(default_max_calls=2)
        budget.consume("dataforseo")
        budget.consume("dataforseo")
        with pytest.raises(ProviderBudgetExceeded):
            budget.consume("dataforseo")

    def test_budget_is_per_provider(self):
        budget = JobBudget(max_calls_per_provider={"dataforseo": 1}, default_max_calls=5)
        budget.consume("dataforseo")
        with pytest.raises(ProviderBudgetExceeded):
            budget.consume("dataforseo")
        budget.consume("tavily")        # unaffected

    def test_unpriced_job_reports_unknown_cost_not_zero(self):
        usage = UsageRecorder()
        usage.record(provider="tavily", operation="search", correlation_id="c",
                     cost_usd=None)
        assert usage.total_cost_usd() is None
        assert usage.summary()["unpriced_events"] == 1

    def test_mixed_costs_sum_only_what_is_known(self):
        usage = UsageRecorder()
        usage.record(provider="dataforseo", operation="serp", correlation_id="c",
                     cost_usd=0.002, cost_is_actual=True)
        usage.record(provider="tavily", operation="search", correlation_id="c",
                     cost_usd=None)
        assert usage.total_cost_usd() == 0.002
        assert usage.summary()["priced_events"] == 1
        assert usage.summary()["unpriced_events"] == 1


class TestFreshness:
    def test_serp_ttl_is_shorter_than_web_research(self, settings_no_llm):
        from app.services.research_cache import ttl_hours
        assert (ttl_hours(ResearchKind.SERP, settings_no_llm)
                < ttl_hours(ResearchKind.WEB_RESEARCH, settings_no_llm))

    def test_fresh_within_ttl(self, settings_no_llm):
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        assert is_fresh(recent, ResearchKind.SERP, settings_no_llm) is True

    def test_stale_beyond_ttl(self, settings_no_llm):
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        assert is_fresh(old, ResearchKind.SERP, settings_no_llm) is False

    def test_missing_timestamp_is_never_fresh(self, settings_no_llm):
        assert is_fresh(None, ResearchKind.SERP, settings_no_llm) is False

    def test_device_is_part_of_the_cache_key(self):
        """Mobile and desktop are different result pages, not variants."""
        desktop = serp_cache_key(query="q", location_code=2056,
                                 language_code="fr", device="desktop")
        mobile = serp_cache_key(query="q", location_code=2056,
                                language_code="fr", device="mobile")
        assert desktop != mobile

    def test_language_is_part_of_the_cache_key(self):
        assert serp_cache_key(query="q", location_code=2056, language_code="fr",
                              device="desktop") != \
            serp_cache_key(query="q", location_code=2056, language_code="nl",
                           device="desktop")

    def test_equivalent_queries_share_a_key(self):
        assert serp_cache_key(query="Prix  Panneaux", location_code=2056,
                              language_code="fr", device="desktop") == \
            serp_cache_key(query="prix panneaux", location_code=2056,
                           language_code="fr", device="desktop")


# ─── Credential reporting ────────────────────────────────────────────────────

class TestCredentialReport:
    def test_reports_status_only(self, settings_all_providers):
        report = settings_all_providers.credential_report()
        assert report == {"DATAFORSEO": "CONFIGURED", "TAVILY": "CONFIGURED",
                          "OPENAI": "CONFIGURED", "INTERNAL_API": "CONFIGURED",
                          # Phase 4: the staging preview token is the only secret
                          # that gates access to unpublished content.
                          "SITE_PREVIEW": "NOT_CONFIGURED",
                          # Lead notification transport — unset until the
                          # operator supplies SMTP credentials.
                          "SMTP": "NOT_CONFIGURED"}
        # No value, no prefix, no length may appear.
        joined = str(report)
        assert "test-tavily-key-not-real" not in joined
        assert "test-login" not in joined

    def test_missing_credentials_are_reported_not_guessed(self, settings_no_llm):
        report = settings_no_llm.credential_report()
        assert report["DATAFORSEO"] == "NOT_CONFIGURED"
        assert report["TAVILY"] == "NOT_CONFIGURED"
        assert report["OPENAI"] == "NOT_CONFIGURED"
