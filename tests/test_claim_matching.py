"""Claim ↔ passage matching precision — Phase 3.3.

Tests A–H are the false-support patterns the mission names. Each one was either
observed in the Phase 3.2 live run or is a pattern that run made possible.
"""
from __future__ import annotations

import pytest

from app.core.enums import ClaimCategory
from app.services.claim_matching import (MatchReason, NumericType,
                                         extract_concepts, extract_numerics,
                                         match)
from app.services.evidence_model import match_passage, passage_supports_claim
from app.services.region import Region


def _match(claim: str, passage: str, profile, **kwargs):
    return match_passage(claim, passage, profile=profile, **kwargs)


# ─── The eight named regressions ─────────────────────────────────────────────

class TestNamedRegressions:
    def test_A_generic_solar_overlap_is_not_support(self, solar_profile):
        """The exact Phase 3.2 pairing that produced false conflicts.

        Shared words: `photovoltaique`, `installation`. Both generic in this
        vertical; one statement is about a grid tariff, the other about a price.
        """
        result = _match(
            "Le tarif prosumer dépend de la puissance de l'onduleur installé.",
            "Le prix d'une installation photovoltaïque est de 5 000 € en moyenne.",
            solar_profile)
        assert result.supports is False
        assert result.agrees_numerically is None, \
            "an unrelated passage must not register a numeric disagreement"
        assert MatchReason.HEAD_CONCEPT_ABSENT in result.reasons

    def test_B_shared_prix_with_a_racing_page_is_not_support(self, solar_profile):
        """Preserves the racing-game protection at the matching layer too."""
        result = _match(
            "Le prix moyen d'installation photovoltaïque est de 5 000 €.",
            "Le Grand Prix Circuit est un jeu de course automobile classique.",
            solar_profile)
        assert result.supports is False
        assert result.agrees_numerically is None

    def test_C_money_and_duration_are_not_comparable(self, solar_profile):
        """€5 000 and 5 ans share digits and nothing else."""
        result = _match(
            "Le coût d'une installation de 5 kWc est de 5 000 €.",
            "La durée de retour sur investissement est de 5 ans pour 5 kWc.",
            solar_profile)
        assert result.supports is False
        assert result.agrees_numerically is not True
        if result.agrees_numerically is False:
            pytest.fail("a type mismatch must not be recorded as a disagreement")

    def test_D_a_walloon_passage_does_not_support_a_brussels_claim(self,
                                                                    solar_profile):
        result = _match(
            "À Bruxelles, la prime régionale à l'installation est accordée.",
            "En Wallonie, la prime régionale à l'installation est accordée.",
            solar_profile, claim_region=Region.BE_BRU,
            passage_region=Region.BE_WAL)
        assert result.supports is False
        assert MatchReason.REGION_MISMATCH in result.reasons

    def test_E_a_brussels_official_passage_supports_a_brussels_claim(self,
                                                                      solar_profile):
        result = _match(
            "À Bruxelles, la prime à l'installation photovoltaïque est accordée "
            "aux particuliers.",
            "La prime à l'installation est accordée aux particuliers en Région "
            "de Bruxelles-Capitale pour le photovoltaïque.",
            solar_profile, claim_region=Region.BE_BRU,
            passage_region=Region.BE_BRU)
        assert result.supports is True
        assert MatchReason.MATCHED_HEAD_CONCEPT in result.reasons

    def test_F_a_walloon_grid_passage_supports_a_walloon_grid_claim(self,
                                                                     solar_profile):
        result = _match(
            "En Wallonie, le tarif prosumer s'applique aux propriétaires "
            "d'installations photovoltaïques.",
            "Le tarif prosumer s'applique en Wallonie aux propriétaires "
            "d'installations photovoltaïques raccordées au réseau.",
            solar_profile, claim_region=Region.BE_WAL,
            passage_region=Region.BE_WAL)
        assert result.supports is True

    def test_G_a_vendor_price_does_not_support_a_market_average(self,
                                                                solar_profile):
        market = _match(
            "Le prix moyen d'une installation en Belgique est de 4 400 €.",
            "Nos tarifs pour une installation de 5 kWc sont de 4 400 €.",
            solar_profile, claim_category=ClaimCategory.MARKET_PRICE)
        vendor = _match(
            "Nos tarifs pour une installation de 5 kWc sont de 4 400 €.",
            "Nos tarifs pour une installation de 5 kWc sont de 4 400 €.",
            solar_profile, claim_category=ClaimCategory.VENDOR_PRICE)
        assert vendor.supports is True
        assert market.supports is False, \
            "a vendor's own price cannot establish a market average"
        assert MatchReason.CATEGORY_MISMATCH in market.reasons

    def test_H_same_topic_different_predicate_is_not_support(self, solar_profile):
        """Both are about batteries; they assert different things."""
        result = _match(
            "La batterie domestique réduit le temps de retour sur investissement.",
            "La batterie domestique augmente le taux d'autoconsommation du foyer.",
            solar_profile)
        assert result.supports is False


# ─── Numeric typing ──────────────────────────────────────────────────────────

class TestNumericTyping:
    @pytest.mark.parametrize("text,expected", [
        ("5 000 €", NumericType.MONEY),
        ("20 %", NumericType.PERCENT),
        ("5 ans", NumericType.DURATION),
        ("3 500 kWh", NumericType.ENERGY),
        ("5 kWc", NumericType.POWER),
        ("1,5 € par Wc", NumericType.RATE),
        ("en 2026", NumericType.YEAR),
        ("le 12/03/2026", NumericType.DATE),
    ])
    def test_quantities_are_typed(self, text, expected):
        entities = extract_numerics(text)
        assert entities, f"nothing extracted from {text!r}"
        assert expected in {e.type for e in entities}

    def test_a_rate_is_not_re_read_as_money(self):
        types = {e.type for e in extract_numerics("1,5 € par Wc installé")}
        assert NumericType.RATE in types
        assert NumericType.MONEY not in types

    def test_same_type_same_value_agrees(self, solar_profile):
        result = _match(
            "Le tarif prosumer coûte environ 100 € par an au ménage wallon.",
            "Le tarif prosumer représente environ 100 € par an pour un ménage "
            "wallon raccordé.",
            solar_profile)
        assert result.supports is True
        assert result.agrees_numerically is True

    def test_same_type_different_value_disagrees(self, solar_profile):
        result = _match(
            "Le tarif prosumer coûte environ 100 € par an au ménage wallon.",
            "Le tarif prosumer représente environ 250 € par an pour un ménage "
            "wallon raccordé.",
            solar_profile)
        assert result.supports is False
        assert result.agrees_numerically is False, \
            "a real disagreement must still be detected"
        assert MatchReason.NUMERIC_DISAGREES in result.reasons


# ─── Generic-token control ───────────────────────────────────────────────────

class TestGenericTokens:
    def test_generic_terms_alone_never_support(self, solar_profile):
        result = _match(
            "Le prix des panneaux solaires en Belgique varie beaucoup.",
            "L'installation photovoltaïque en Belgique concerne l'énergie solaire.",
            solar_profile)
        assert result.supports is False

    def test_generic_terms_are_identified_per_vertical(self, solar_profile,
                                                        generic_profile):
        solar = extract_concepts("Le prix des panneaux solaires", solar_profile)
        other = extract_concepts("Le prix des panneaux solaires", generic_profile)
        # Tokens are stemmed, so the configured `solaire` masks `solaires` too.
        assert "solaire" in solar.generic_terms
        # The generic test vertical configures no solar vocabulary, so the same
        # words remain discriminative there.
        assert "solaire" in other.topic_terms

    def test_discriminative_terms_still_carry_a_match(self, solar_profile):
        result = _match(
            "Le compteur bidirectionnel enregistre séparément les flux "
            "d'injection et de prélèvement.",
            "Le compteur bidirectionnel mesure séparément l'injection et le "
            "prélèvement sur le réseau.",
            solar_profile)
        assert result.supports is True


# ─── Concept extraction ──────────────────────────────────────────────────────

class TestConceptExtraction:
    def test_a_configured_concept_phrase_becomes_the_head(self, solar_profile):
        concepts = extract_concepts(
            "Le tarif prosumer dépend de la puissance installée.", solar_profile)
        assert concepts.head_phrase == "tarif prosumer"

    def test_the_most_specific_phrase_wins(self, solar_profile):
        concepts = extract_concepts(
            "Le retour sur investissement dépend du tarif prosumer appliqué.",
            solar_profile)
        assert concepts.head_phrase in ("retour sur investissement",
                                        "tarif prosumer")
        assert len(concepts.phrases) >= 2

    def test_a_claim_with_no_configured_phrase_still_gets_a_head(self,
                                                                 solar_profile):
        concepts = extract_concepts(
            "L'onduleur hybride pilote la charge de la batterie.", solar_profile)
        assert concepts.head_phrase

    def test_concepts_are_inspectable(self, solar_profile):
        payload = extract_concepts("Le tarif prosumer coûte 100 € par an.",
                                   solar_profile).as_dict()
        assert payload["head_phrase"] == "tarif prosumer"
        assert payload["numerics"]


# ─── Diagnostics ─────────────────────────────────────────────────────────────

class TestDiagnostics:
    def test_every_decision_carries_a_reason(self, solar_profile):
        cases = [
            ("Le tarif prosumer s'applique.", "Le prix moyen est de 5 000 €."),
            ("Le tarif prosumer coûte 100 € par an.",
             "Le tarif prosumer coûte 100 € par an en Wallonie."),
            ("Le coût est de 5 000 €.", "La durée est de 5 ans."),
        ]
        for claim, passage in cases:
            result = _match(claim, passage, solar_profile)
            assert result.reasons, f"no reason recorded for {claim!r}"
            assert result.detail

    def test_reasons_reach_the_evidence_ref_note(self, solar_profile):
        from app.services.claim_extraction import AtomicClaim
        from app.services.evidence_model import build_candidates

        claim = AtomicClaim(
            text="Le tarif prosumer coûte environ 100 € par an au ménage wallon.",
            passage="", source_ref="s1", offset=0)
        sources = {"s1": {"url": "https://cwape.be/x", "source_quality": "OFFICIAL",
                          "relevance_status": "RELEVANT", "source_type": "web",
                          "observation_status": "ESTIMATED", "provider": "tavily",
                          "region_enum": Region.BE_WAL}}
        passages = {"s1": ["Le tarif prosumer représente environ 100 € par an "
                           "pour un ménage wallon raccordé au réseau."]}
        candidates = build_candidates(claim, sources, passages,
                                      profile=solar_profile,
                                      claim_region=Region.BE_WAL)
        assert candidates
        assert candidates[0].note, "matching reasons must be persisted"

    def test_the_legacy_matcher_is_still_available_without_a_profile(self):
        """Callers with no vertical context keep working, coarser."""
        supports, agrees = passage_supports_claim(
            "Le prix dépend de la puissance installée.",
            "Le prix dépend directement de la puissance installée totale.")
        assert supports is True


# ─── Precision does not destroy recall entirely ──────────────────────────────

class TestRecallSanity:
    def test_a_genuine_restatement_is_still_matched(self, solar_profile):
        result = _match(
            "Le certificat vert est octroyé par kWh produit.",
            "Le certificat vert est octroyé pour chaque kWh produit par "
            "l'installation.",
            solar_profile)
        assert result.supports is True

    def test_an_official_paraphrase_is_matched(self, solar_profile):
        result = _match(
            "La prime à l'installation est plafonnée pour les particuliers.",
            "La prime à l'installation photovoltaïque est plafonnée pour les "
            "particuliers selon la puissance.",
            solar_profile)
        assert result.supports is True


class TestDraftQualityRegressions:
    """Phase 3.3 live draft, 2026-08-12.

    Both QA layers passed with a perfect score on a draft that stated no price on
    a price query and linked to a commercial competitor. Passing factual QA means
    "asserted nothing false", which is not the same as "answered the question".
    """

    BODY = ("# Prix des panneaux solaires en Belgique\n\n"
            "## Comprendre le besoin\n\n"
            + "Une installation photovoltaique comprend plusieurs elements et "
              "services selon la configuration du batiment. " * 12
            + "\n\n## Prochaines etapes\n\nDemandez un devis personnalise pour "
              "obtenir une estimation adaptee a votre toiture.")

    def _brief(self, **over):
        brief = {"primary_query": "prix panneaux solaires Belgique",
                 "content_type": "LANDING_PAGE", "search_intent": "COMMERCIAL",
                 "target_audience": "a", "objective": "o",
                 "required_facts": [{"fact": "Une installation comprend "
                                             "plusieurs elements et services."}],
                 "required_sources": [{"ref": "s1", "url": "https://x.be"}],
                 "cautionary_claims": [], "cta_strategy": {"code": "quote_request"},
                 "missing_information": []}
        brief.update(over)
        return brief

    def _draft(self, body):
        return {"title": "Prix des panneaux solaires en Belgique",
                "meta_title": "Prix panneaux solaires Belgique",
                "meta_description": "Ce qui fait varier le prix d'une "
                                    "installation photovoltaique en Belgique.",
                "body": body}

    def test_an_outbound_link_in_the_body_blocks(self, solar_profile):
        from app.services.qa_service import run_seo_qa_v2

        body = self.BODY + ("\n\nVoir notre article sur les "
                            "[panneaux](https://concurrent.be/prix) !")
        verdict = run_seo_qa_v2(self._draft(body), self._brief(),
                                {"facts": [], "sources": []}, solar_profile)
        codes = {f["code"] for f in verdict["blocking_issues"]}
        assert "EXTERNAL_LINK_IN_BODY" in codes

    def test_a_commercial_page_with_no_figure_is_flagged(self, solar_profile):
        from app.services.qa_service import run_seo_qa_v2

        verdict = run_seo_qa_v2(self._draft(self.BODY), self._brief(),
                                {"facts": [], "sources": []}, solar_profile)
        codes = {f["code"] for f in verdict["findings"]}
        assert "NO_QUANTIFIED_ANSWER" in codes

    def test_the_no_figure_finding_is_advisory_not_blocking(self, solar_profile):
        """A page can be honest and still not answer the query — that is a
        usefulness problem for a reviewer, not grounds to refuse the draft."""
        from app.services.qa_service import run_seo_qa_v2

        verdict = run_seo_qa_v2(self._draft(self.BODY), self._brief(),
                                {"facts": [], "sources": []}, solar_profile)
        blocking = {f["code"] for f in verdict["blocking_issues"]}
        assert "NO_QUANTIFIED_ANSWER" not in blocking

    def test_a_quantified_commercial_page_is_not_flagged(self, solar_profile):
        from app.services.qa_service import run_seo_qa_v2

        body = self.BODY.replace("## Prochaines etapes",
                                 "Le cout observe se situe autour de 5 000 euros."
                                 "\n\n## Prochaines etapes")
        verdict = run_seo_qa_v2(self._draft(body), self._brief(),
                                {"facts": [{"fact": "environ 5 000 euros"}],
                                 "sources": []}, solar_profile)
        codes = {f["code"] for f in verdict["findings"]}
        assert "NO_QUANTIFIED_ANSWER" not in codes
