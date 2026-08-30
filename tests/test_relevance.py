"""RelevanceGate.

The first test in this file is the reason Phase 3 exists. Everything else defends
the rule that makes it work.
"""
from __future__ import annotations

import pytest

from app.services.relevance import (RESEARCH_QUERY_KEY, RelevanceStatus,
                                    RelevanceThresholds,
                                    build_query_profile, query_that_fetched,
                                    score_claim, score_source,
                                    tokenize)

SOLAR_QUERY = "prix panneaux solaires Belgique"


class TestPhase2Regression:
    """The exact failure Phase 2 shipped."""

    def test_racing_game_source_is_irrelevant(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="The making of Don Matrelli's Legacy, a mod for Grand Prix Circuit (part I)",
            body=("A retrospective on building a modification for the classic "
                  "racing game Grand Prix Circuit, covering track editing and "
                  "sprite work."),
            url="https://marnetto.net/2026/07/18/dml-making-of-1",
        )
        assert decision.status is RelevanceStatus.IRRELEVANT
        assert decision.status.is_eligible is False

    def test_the_trap_is_the_word_prix(self, solar_profile):
        """"Grand Prix" shares a token with a price query.

        A gate scoring bare word overlap would give this source a third of the
        query and call it partially relevant. The rejection must come from the
        topic/modifier split, and the reason must say so.
        """
        profile = build_query_profile(SOLAR_QUERY, solar_profile)
        assert "prix" in profile.modifier_tokens
        assert "prix" not in profile.topic_tokens
        assert {"panneau", "solaire"} <= profile.topic_tokens

        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Grand Prix Circuit game modification",
            body="Racing game mod development notes.",
        )
        assert decision.status is RelevanceStatus.IRRELEVANT
        assert "matched only prix" in decision.reason

    def test_rejected_source_is_never_eligible_evidence(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Grand Prix Circuit mod", body="Racing.")
        claim = score_claim(query=SOLAR_QUERY, profile=solar_profile,
                            claim="The track editor supports 20 circuits.",
                            source_decision=decision)
        assert claim.status is RelevanceStatus.IRRELEVANT
        assert claim.signals.get("inherited") is True


class TestTopicMatching:
    def test_on_topic_source_is_relevant(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Prix des panneaux solaires en Belgique en 2026",
            body=("Le prix d'une installation de panneaux solaires dépend de la "
                  "puissance installée et du type de toiture."),
            url="https://example-energy.be/prix-panneaux-solaires",
        )
        assert decision.status is RelevanceStatus.RELEVANT
        assert decision.status.is_eligible is True

    def test_plural_matches_singular(self, solar_profile):
        """`panneaux`/`solaires` in the query must match `panneau`/`solaire`."""
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Le panneau solaire résidentiel",
            body="Un panneau solaire produit de l'électricité; le prix varie.",
        )
        assert decision.status is RelevanceStatus.RELEVANT

    def test_partial_topic_match_is_low_relevance(self, solar_profile):
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Guide de la toiture",
            body="La toiture d'une maison peut accueillir des panneaux divers.",
        )
        assert decision.status in (RelevanceStatus.LOW_RELEVANCE,
                                   RelevanceStatus.IRRELEVANT)
        assert decision.status.is_eligible is False

    def test_low_relevance_is_not_eligible(self):
        assert RelevanceStatus.LOW_RELEVANCE.is_eligible is False
        assert RelevanceStatus.UNKNOWN.is_eligible is False
        assert RelevanceStatus.RELEVANT.is_eligible is True

    def test_market_name_alone_does_not_make_a_source_relevant(self, solar_profile):
        """A page about Belgian waffles is not about Belgian solar panels."""
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Les gaufres de Belgique",
            body="La Belgique est connue pour ses gaufres et son chocolat.",
        )
        assert decision.status is RelevanceStatus.IRRELEVANT

    def test_domain_lifts_to_low_relevance_but_not_to_relevant(self, solar_profile):
        """A matching domain says what the SITE is about, not the page.

        `panneaux-solaires-belgique.be/tarifs` is genuinely on-topic, so it must
        not be hard-rejected — but a solar company's careers page is still not
        evidence about solar pricing, so the domain alone cannot make it eligible.
        """
        decision = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Nos tarifs", body="Devis sur mesure pour votre installation.",
            url="https://panneaux-solaires-belgique.be/tarifs",
        )
        assert decision.status is RelevanceStatus.LOW_RELEVANCE
        assert decision.status.is_eligible is False


class TestClaimRelevance:
    def test_off_topic_claim_from_a_relevant_source_is_rejected(self, solar_profile):
        source = score_source(
            query=SOLAR_QUERY, profile=solar_profile,
            title="Prix des panneaux solaires en Belgique",
            body="Le prix d'une installation de panneaux solaires varie.")
        assert source.status is RelevanceStatus.RELEVANT

        claim = score_claim(
            query=SOLAR_QUERY, profile=solar_profile,
            claim="L'auteur a passé ses vacances en Italie l'été dernier.",
            source_decision=source)
        assert claim.status is not RelevanceStatus.RELEVANT

    def test_claim_cannot_outrank_a_weak_source(self, solar_profile):
        weak = score_source(query=SOLAR_QUERY, profile=solar_profile,
                            title="Toiture", body="Une toiture quelconque.")
        if weak.status is RelevanceStatus.LOW_RELEVANCE:
            claim = score_claim(
                query=SOLAR_QUERY, profile=solar_profile,
                claim="Le prix des panneaux solaires dépend de la puissance.",
                source_decision=weak)
            assert claim.status is RelevanceStatus.LOW_RELEVANCE


class TestThresholds:
    def test_thresholds_are_configurable(self, solar_profile):
        args = dict(query=SOLAR_QUERY, profile=solar_profile,
                    title="Panneaux solaires",
                    body="Un texte générique sur des panneaux.")
        strict = score_source(**args, thresholds=RelevanceThresholds(
            relevant_at=0.99, low_relevance_at=0.9, irrelevant_below=0.9))
        lenient = score_source(**args, thresholds=RelevanceThresholds(
            relevant_at=0.05, low_relevance_at=0.01, irrelevant_below=0.01))
        assert strict.status is not RelevanceStatus.RELEVANT
        assert lenient.status is RelevanceStatus.RELEVANT

    def test_query_with_no_topic_tokens_is_unknown(self, solar_profile):
        decision = score_source(query="prix Belgique", profile=solar_profile,
                                title="Something", body="Anything")
        assert decision.status is RelevanceStatus.UNKNOWN


class TestTokenizer:
    @pytest.mark.parametrize("text,expected", [
        ("panneaux", "panneau"),
        ("solaires", "solaire"),
        ("panels", "panel"),
        ("chevaux", "cheval"),
    ])
    def test_light_stemming(self, text, expected):
        assert expected in tokenize(text)

    def test_stopwords_and_short_tokens_are_dropped(self):
        tokens = tokenize("le prix de la maison et du jardin")
        assert "le" not in tokens and "de" not in tokens and "et" not in tokens
        assert "maison" in tokens

    def test_accents_are_folded(self):
        assert tokenize("rentabilité") == tokenize("rentabilite")


# ─── Which question a source is held to ──────────────────────────────────────

class TestSourceIsJudgedAgainstTheQueryThatFetchedIt:
    """The live run of 2026-08-30: 31 of 40 official pages discarded, wrongly.

    The targeted authoritative pass asks a regulator a question of its OWN —
    "premie zonnepanelen Vlaanderen voorwaarden officieel" — precisely because
    the article's query would never surface that page. The gate then scored the
    answer against the article's query and rejected it for having no topical
    overlap with a question nobody had put to it. Every vlaanderen.be and every
    creg.be result went out that way, and `high_risk_supported` was 0 of 57.

    The gate itself does not move. Only the pairing does.
    """

    ARTICLE_QUERY = "rentabilite panneaux solaires belgique"

    VLAANDEREN = {
        "title": "Premie zonnepanelen — Vlaanderen.be",
        "body": ("De Vlaamse overheid kent een premie toe voor de plaatsing van "
                 "zonnepanelen. De voorwaarden en bedragen vindt u hier."),
        "url": "https://www.vlaanderen.be/premie-zonnepanelen",
    }
    VLAANDEREN_QUERY = "premie zonnepanelen Vlaanderen voorwaarden officieel"

    CREG = {
        "title": "Tarifs de l'électricité pour les ménages — CREG",
        "body": ("La CREG publie l'évolution du prix de l'électricité et des "
                 "tarifs régulés pour les ménages belges."),
        "url": "https://www.creg.be/fr/tarifs-electricite-menages",
    }
    CREG_QUERY = "prix electricite tarif regule menages"

    def test_metadata_carries_the_query_that_fetched_the_source(self):
        assert query_that_fetched({RESEARCH_QUERY_KEY: "sa propre requête"},
                                  default="autre") == "sa propre requête"

    @pytest.mark.parametrize("metadata", [None, {}, {RESEARCH_QUERY_KEY: ""},
                                          {RESEARCH_QUERY_KEY: "   "},
                                          {RESEARCH_QUERY_KEY: 42}])
    def test_without_a_recorded_query_the_article_query_still_applies(self,
                                                                      metadata):
        """General web research is unchanged: it never records one."""
        assert query_that_fetched(metadata, default="requête d'article") == \
            "requête d'article"

    @pytest.mark.parametrize("source,targeted", [
        (VLAANDEREN, VLAANDEREN_QUERY),
        (CREG, CREG_QUERY),
    ])
    def test_an_official_page_was_discarded_by_the_wrong_question(
            self, source, targeted, solar_profile):
        """First half of the proof: this is what the live run did."""
        against_article = score_source(query=self.ARTICLE_QUERY,
                                       profile=solar_profile, **source)
        assert against_article.status is RelevanceStatus.IRRELEVANT

    @pytest.mark.parametrize("source,targeted", [
        (VLAANDEREN, VLAANDEREN_QUERY),
        (CREG, CREG_QUERY),
    ])
    def test_the_same_page_passes_against_the_question_it_answers(
            self, source, targeted, solar_profile):
        """Second half: the 31 discarded sources come back."""
        metadata = {RESEARCH_QUERY_KEY: targeted}
        decision = score_source(
            query=query_that_fetched(metadata, default=self.ARTICLE_QUERY),
            profile=solar_profile, **source)
        assert decision.status is RelevanceStatus.RELEVANT
        assert decision.status.is_eligible is True

    def test_an_off_topic_page_is_still_rejected_under_the_targeted_query(
            self, solar_profile):
        """The counter-proof. Re-pairing is not a hole.

        The Phase 2 failure re-run through the new path: a racing game answering
        a Flemish subsidy query is rejected by the same hard rule, for the same
        reason, with the targeted query named in it.
        """
        metadata = {RESEARCH_QUERY_KEY: self.VLAANDEREN_QUERY}
        decision = score_source(
            query=query_that_fetched(metadata, default=self.ARTICLE_QUERY),
            profile=solar_profile,
            title="Grand Prix Circuit — jeu de course automobile",
            body="Le meilleur jeu de course. Prix de lancement à 19,99 €.",
            url="https://exemple-jeux.be/grand-prix-circuit")
        assert decision.status is RelevanceStatus.IRRELEVANT
        assert decision.status.is_eligible is False

    def test_the_threshold_is_still_what_decides(self, solar_profile):
        """Mutation on the threshold, in the test itself.

        If re-pairing had quietly made the gate permissive, tightening the bar
        would change nothing. It changes everything: the same official page,
        against the same targeted query, falls out when the bar is raised and
        passes when it is lowered. The threshold still carries the decision.
        """
        args = dict(query=self.VLAANDEREN_QUERY, profile=solar_profile,
                    **self.VLAANDEREN)
        strict = score_source(**args, thresholds=RelevanceThresholds(
            relevant_at=0.99, low_relevance_at=0.9, irrelevant_below=0.9))
        default = score_source(**args, thresholds=RelevanceThresholds())
        assert strict.status is not RelevanceStatus.RELEVANT
        assert default.status is RelevanceStatus.RELEVANT

    def test_the_default_thresholds_have_not_moved(self):
        """Pinned, because the arbitrage was «corrige l'appariement, pas le seuil»."""
        thresholds = RelevanceThresholds()
        assert thresholds.relevant_at == 0.55
        assert thresholds.low_relevance_at == 0.30
        assert thresholds.irrelevant_below == 0.30
