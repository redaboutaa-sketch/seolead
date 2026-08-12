"""Named regressions for every defect Phase 1 and Phase 2 discovered.

Each of these was a real fault that shipped or was caught in a live run. They are
collected here, named after the incident rather than the module, so that a future
change that reintroduces one fails against a test whose name says what broke.
Deeper coverage of each lives in the topic-specific suites.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.enums import Observability, SearchIntent, SourceState
from app.core.logging import JsonFormatter, redact
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.services.intent import classify_intent
from app.services.package_builder import build_package_payload
from app.services.package_builder_v2 import build_package_v2
from app.services.qa_service import run_deterministic_qa
from app.services.relevance import RelevanceStatus, score_source

SOLAR_QUERY = "prix panneaux solaires Belgique"


class TestRacingGameRegression:
    """Phase 2 live run, 2026-08-12.

    `prix panneaux solaires Belgique` returned exactly one "supported fact": a
    Hacker News post titled "The making of Don Matrelli's Legacy, a mod for Grand
    Prix Circuit (part I)". Nothing asked whether the source was about the query.
    """

    RACING_TITLE = ("The making of Don Matrelli's Legacy, a mod for Grand Prix "
                    "Circuit (part I)")

    def test_racing_source_is_irrelevant(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile, title=self.RACING_TITLE,
            body="Notes on building a modification for a classic racing game.",
            url="https://marnetto.net/2026/07/18/dml-making-of-1")
        assert decision.status is RelevanceStatus.IRRELEVANT

    def test_racing_source_cannot_become_eligible_evidence(self, solar_profile):
        result = ResearchProviderResult(
            provider="tavily", query=SOLAR_QUERY, market="BE", language="fr",
            status="SUCCEEDED",
            sources=[NormalizedSource(
                source_type="web", state=SourceState.OK,
                url="https://marnetto.net/dml", title=self.RACING_TITLE,
                summary="Racing game modification notes.",
                published_at=datetime.now(timezone.utc), candidate_id="racing")],
            facts=[NormalizedFact(fact="The track editor supports 20 circuits.",
                                  observability=Observability.OBSERVED,
                                  source_ref="racing")],
            source_outcomes=[SourceOutcome(source_type="web",
                                           state=SourceState.OK, item_count=1)])

        package = build_package_v2(
            query=SOLAR_QUERY, market="BE", language="fr",
            intent=SearchIntent.COMMERCIAL, profile=solar_profile, serp=None,
            serp_analysis=None, keyword_metrics=[], research_results=[result])

        assert package["eligible_evidence"] == []
        assert package["facts"] == []
        assert len(package["rejected_evidence"]) == 1

    def test_the_rejection_is_explainable(self, solar_profile):
        """An operator must be able to see why, not just that."""
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile, title=self.RACING_TITLE,
            body="Racing game modification notes.")
        assert "prix" in decision.reason
        assert decision.signals["topic_matched"] == []


class TestBelgiumIntentRegression:
    """Phase 2 build.

    "Belgique" sat in `local_terms`, so every Belgian query classified as LOCAL
    intent — routing the entire vertical to the wrong content type and the wrong
    call to action.
    """

    def test_market_name_alone_does_not_force_local_intent(self, solar_profile):
        assert classify_intent(SOLAR_QUERY, solar_profile) is SearchIntent.COMMERCIAL

    def test_an_actual_locality_still_does(self, solar_profile):
        assert classify_intent("prix panneaux solaires Liège",
                               solar_profile) is SearchIntent.LOCAL

    def test_market_terms_and_local_terms_are_disjoint(self, solar_profile):
        assert not (set(solar_profile.market_terms)
                    & set(solar_profile.local_terms))


class TestRestrictedClaimRegression:
    """Mission rule: subsidies, taxes, ROI, savings and regulations may never be
    asserted without a dated, sufficiently authoritative source."""

    def test_unverified_subsidy_figure_is_blocked(self, solar_profile):
        body = ("# Prix\n\n## Coûts\n\n" + "Texte explicatif sur l'installation. " * 40
                + "\n\n## Primes\n\nLa prime régionale couvre 1 750 euros du montant.")
        verdict = run_deterministic_qa(
            {"title": "Prix", "meta_title": "Prix", "meta_description": "Prix",
             "body": body},
            {"primary_query": SOLAR_QUERY, "required_facts": [{"fact": "x"}],
             "required_sources": [{"ref": "s1", "url": "https://x.be"}],
             "cautionary_claims": [{"topic": "prime",
                                    "has_supported_evidence": False}],
             "cta_strategy": {"code": "quote_request"}},
            {"facts": [], "sources": []}, solar_profile)
        codes = {f["code"] for f in verdict["blocking_issues"]}
        assert codes & {"RESTRICTED_CLAIM_QUANTIFIED", "UNSUPPORTED_NUMERIC_CLAIM"}

    def test_every_restricted_topic_reaches_the_brief_as_cautionary(self,
                                                                     solar_profile):
        from app.services.brief_service import build_brief_payload

        package = {"query": SOLAR_QUERY, "market": "BE", "language": "fr",
                   "intent": "COMMERCIAL", "facts": [], "sources": [],
                   "user_questions": [], "unresolved_questions": [],
                   "confidence_summary": {}}
        brief = build_brief_payload(package, profile=solar_profile,
                                    query=SOLAR_QUERY)
        topics = {c["topic"] for c in brief["cautionary_claims"]}
        assert set(solar_profile.restricted_claims) <= topics
        assert all(c["has_supported_evidence"] is False
                   for c in brief["cautionary_claims"])


class TestSourceAccountingRegression:
    """Phase 2 live run.

    `source_types_with_items` counted states that PERMIT items rather than
    sources that RETURNED them, so `reddit: partial` with zero items read as
    coverage — overstating in the direction that matters.
    """

    def test_partial_state_with_no_items_is_not_counted_as_coverage(self,
                                                                     solar_profile):
        result = ResearchProviderResult(
            provider="last30days", query=SOLAR_QUERY, market="BE", language="fr",
            status="PARTIAL",
            source_outcomes=[
                SourceOutcome(source_type="reddit", state=SourceState.PARTIAL,
                              item_count=0),
                SourceOutcome(source_type="web", state=SourceState.OK,
                              item_count=3),
            ])
        package = build_package_payload(result, intent=SearchIntent.COMMERCIAL,
                                        profile=solar_profile)
        summary = package["confidence_summary"]
        assert summary["source_types_with_items"] == 1
        assert summary["source_types_returning_nothing_despite_ok_state"] == 1


class TestSecretRedactionRegression:
    """Phase 2 build.

    The redactor matched `api_key=value` but not `"api_key": "value"` — the
    JSON shape this application actually logs. It would have passed every
    hand-written test and redacted nothing in production.
    """

    def test_json_shaped_secret_is_redacted(self):
        assert "REDACTED" in redact('{"api_key": "sk-abcdefghijklmnop"}')
        assert "REDACTED" in redact('{"secret": "abcdef123456"}')
        assert "REDACTED" in redact('"password": "hunter2hunter2"')

    def test_json_log_record_is_redacted_end_to_end(self):
        import logging

        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="", lineno=0,
            msg='provider rejected {"api_key": "sk-abcdefghijklmnop"}',
            args=(), exc_info=None)
        output = JsonFormatter().format(record)
        assert "sk-abcdefghijklmnop" not in output


class TestStemmerRegression:
    """Phase 3 build.

    `panneaux` stemmed to `panneal` because the French `-aux → -al` rule
    (cheval/chevaux) fired before the `-eaux → -eau` case (panneau/panneaux).
    `panneau` is a topic token for the pilot query, so the bug silently disabled
    the relevance gate's central check.
    """

    def test_panneaux_stems_to_panneau(self):
        from app.services.relevance import tokenize
        assert "panneau" in tokenize("panneaux")

    def test_chevaux_still_stems_to_cheval(self):
        from app.services.relevance import tokenize
        assert "cheval" in tokenize("chevaux")

    def test_the_pilot_query_matches_a_singular_title(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Le panneau solaire en Belgique",
            body="Un panneau solaire produit de l'électricité; le prix varie.")
        assert decision.status is RelevanceStatus.RELEVANT
