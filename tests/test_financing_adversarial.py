"""The natural evasions of a writer or an LLM, tested before one finds them.

The first regex closed the audit's §2. These are the phrasings that say the
same thing without the flagged words — every one of them measured ESCAPING
(GENERAL/LOW or MARKET_PRICE) before this hardening, ten out of ten.

The stated limit, documented as such at the bottom: this is claim-NATURE
detection with lexical reach, not semantics. A paraphrase that avoids every
financial noun (« votre argent reste où il est ») will pass the classifier and
must be caught by the layers above it — the ledger (a financing claim has no
supporting source), the substance gate, and the human approval that remains
mandatory for everything.
"""
from __future__ import annotations

import pytest

from app.services.claim_policy import (ClaimRisk, is_financing_promise,
                                       is_unconditional_financing_promise,
                                       requirements_for)
from app.services.qa_service import _financing_findings


def lab(value):
    return getattr(value, "value", value)


EVASIONS = [
    "Votre installation ne vous coûte rien au départ.",
    "Aucune épargne nécessaire.",
    "Commencez sans sortir d'argent.",
    "Zéro investissement initial.",
    "Pas besoin d'économies pour démarrer.",
    "Vos panneaux se remboursent tout seuls.",
    "Votre facture finance votre installation.",
    "Les économies remboursent vos panneaux.",
    "Votre installation est payée par votre facture.",
    "Passez au solaire sans débourser un euro.",
]


class TestNaturalEvasions:
    @pytest.mark.parametrize("phrase", EVASIONS)
    def test_the_evasion_classifies_financing_promise_high(self, solar_profile,
                                                           phrase):
        requirements = requirements_for(phrase, solar_profile)
        assert lab(requirements.category) == "FINANCING_PROMISE", phrase
        assert lab(requirements.risk) == ClaimRisk.HIGH

    @pytest.mark.parametrize("phrase", EVASIONS)
    def test_and_its_unconditional_form_blocks_at_qa(self, phrase):
        codes = [f["code"] for f in _financing_findings(
            {"body": phrase, "title": "T", "meta_title": "T",
             "meta_description": "D"}, None)]
        assert "UNCONDITIONAL_FINANCING_PROMISE" in codes, phrase


class TestSurfaceVariants:
    """Same promise, different typography. `normalize_query` handles accents
    and whitespace; the regex handles both apostrophes — « s’autofinance »
    with the typographic one escaped the first version."""

    @pytest.mark.parametrize("phrase", [
        "SANS APPORT INITIAL",                                # casse
        "sans  apport   initial",                             # espaces multiples
        "sans apports",                                       # pluriel
        "Commencez sans sortir d’argent.",                    # apostrophe ’
        "L’installation s’autofinance.",                      # ’ des deux côtés
        "Pas  besoin  d’économies  pour  démarrer.",          # tout à la fois
        "Zéro    investissement    initial",
    ])
    def test_typography_does_not_launder_the_promise(self, solar_profile,
                                                     phrase):
        assert lab(requirements_for(phrase, solar_profile).category) == \
            "FINANCING_PROMISE"

    def test_an_interrogative_is_still_the_subject(self, solar_profile):
        """A question about the offer is a financing claim needing the registry
        — but « peut-on » carries a conditional marker, so it is not blocked as
        an unconditional promise. The distinction, on one sentence."""
        phrase = "Peut-on vraiment commencer sans rien payer ?"
        assert lab(requirements_for(phrase, solar_profile).category) == \
            "FINANCING_PROMISE"
        assert is_unconditional_financing_promise(phrase) is False

    def test_a_negation_that_promises_is_a_promise(self, solar_profile):
        """« ne vous coûte rien » is grammatical negation and commercial
        affirmation at once. The grammar does not decide."""
        assert is_unconditional_financing_promise(
            "Votre installation ne vous coûte rien au départ.") is True

    def test_the_conditional_form_stays_the_allowed_one(self):
        assert is_unconditional_financing_promise(
            "Selon votre situation, le projet peut être réalisé sans apport."
        ) is False


class TestEveryFieldACrawlerReads:
    """The first version of the QA check only read the body. A promise in a
    heading survives (headings are stripped of `#`, not of text); a promise in
    the title or meta description is the promise at its most visible."""

    CLEAN_BODY = "Le projet est décrit lors de l'étude personnalisée."

    def test_a_heading_is_scanned_like_any_sentence(self):
        codes = [f["code"] for f in _financing_findings(
            {"body": "## Panneaux gratuits pour tous\n\n" + self.CLEAN_BODY,
             "title": "T", "meta_title": "T", "meta_description": "D"}, None)]
        assert "UNCONDITIONAL_FINANCING_PROMISE" in codes

    @pytest.mark.parametrize("field", ["title", "meta_title",
                                       "meta_description"])
    def test_title_and_metas_are_scanned_too(self, field):
        draft = {"body": self.CLEAN_BODY, "title": "Titre sobre",
                 "meta_title": "Titre sobre", "meta_description": "Description."}
        draft[field] = "Installation solaire gratuite, sans apport"
        codes = [f["code"] for f in _financing_findings(draft, None)]
        assert "UNCONDITIONAL_FINANCING_PROMISE" in codes, field

    def test_a_clean_draft_raises_nothing(self):
        assert _financing_findings(
            {"body": self.CLEAN_BODY, "title": "Titre sobre",
             "meta_title": "Titre sobre",
             "meta_description": "Une description factuelle."}, None) == []

    def test_the_finding_blocks_publication(self):
        # Un constat non bloquant serait un avertissement décoratif : la
        # promesse passerait la porte. Le drapeau est le mécanisme, pas le
        # message.
        findings = _financing_findings(
            {"body": "Vos panneaux se remboursent tout seuls.",
             "title": "T", "meta_title": "T", "meta_description": "D"}, None)
        assert findings and all(f["blocking"] is True for f in findings)


class TestTheEdgesStillHold:
    """The hardening must not have widened into the real corpus."""

    @pytest.mark.parametrize("text,expected", [
        ("On estime aujourd'hui sa rentabilisation en 5 à 7 ans, permettant "
         "de produire gratuitement de l'électricité pour le ménage.", "GENERAL"),
        ("Les panneaux réduisent votre facture d'électricité de 30 à 40 %.",
         "GENERAL"),
        ("Vous payez votre facture d'électricité chaque mois à votre "
         "fournisseur.", "GENERAL"),
        # « remboursé par la Région » : le motif financier exige économies ou
        # facture après l'article — la Région ne doit PAS matcher. Aucun terme
        # du lexique subside ne figure dans la phrase : GENERAL, mesuré.
        ("Le montant est remboursé par la Région wallonne sous conditions de "
         "revenus.", "GENERAL"),
        ("Sans subside, la rentabilité repose sur l'autoconsommation.",
         "SUBSIDY"),
        ("Le tarif de nuit est à 0,05 €/kWh chez certains fournisseurs.",
         "MARKET_PRICE"),
        ("Sans entretien particulier, les panneaux durent 25 ans.", "GENERAL"),
    ])
    def test_ordinary_prose_keeps_its_category(self, solar_profile, text,
                                               expected):
        assert lab(requirements_for(text, solar_profile).category) == expected

    @pytest.mark.parametrize("sentence", [
        # Chaque phrase ne porte qu'UN seul marqueur conditionnel — si ce
        # marqueur tombe du motif, la phrase redevient « inconditionnelle »
        # et le test meurt. Un marqueur par phrase, ou le test ne prouve rien.
        "Selon votre dossier, l'installation s'autofinance.",
        "Si votre toiture convient, l'installation s'autofinance.",
        "Dans certains cas, l'installation s'autofinance.",
        "Les économies peuvent couvrir la mensualité.",
    ])
    def test_one_conditional_marker_suffices_to_downgrade(self, sentence):
        assert is_financing_promise(sentence) is True, sentence
        assert is_unconditional_financing_promise(sentence) is False, sentence


class TestDocumentedLimits:
    """What this detection does NOT claim to do, pinned so nobody believes
    otherwise later. These phrasings pass the classifier by design limitation;
    they are caught upstream (no source can support them in the ledger) and
    downstream (human approval). If one of these starts mattering, the fix is
    a new measured pattern — not a claim that the filter was ever semantic."""

    @pytest.mark.parametrize("paraphrase", [
        "Votre argent reste où il est.",
        "Votre portefeuille ne s'en apercevra pas.",
        "Le soleil s'occupe du reste.",
    ])
    def test_known_semantic_escapes_are_known(self, solar_profile, paraphrase):
        assert lab(requirements_for(paraphrase, solar_profile).category) != \
            "FINANCING_PROMISE"
        assert is_financing_promise(paraphrase) is False
