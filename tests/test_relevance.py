"""RelevanceGate.

The first test in this file is the reason Phase 3 exists. Everything else defends
the rule that makes it work.
"""
from __future__ import annotations

import pytest

from app.services.relevance import (RelevanceStatus, RelevanceThresholds,
                                    build_query_profile, score_claim, score_source,
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
