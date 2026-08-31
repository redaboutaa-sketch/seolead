"""Le corpus adversarial SG Solution — treize revendications, mesurées avant.

Avant ce durcissement (mesuré le 2026-08-31) : « Le tarif est garanti à
0,27 €/kWh pendant 25 ans » classait MARKET_PRICE/MEDIUM ; « Tout le monde
est accepté », « Votre facture ne pourra plus augmenter » et « Après 25 ans,
l'installation devient gratuitement votre propriété » classaient GENERAL/LOW ;
douze des treize passaient la QA sans un constat.

Trois familles ferment le trou : CONTRACT_PROMISE (les termes du contrat
promis comme certitudes — délibérément PAS une catégorie de financement, la
qualification juridique du contrat restant la question du juriste),
l'acheminement des promesses d'acceptation vers ELIGIBILITY, et l'extension
de la garde chiffres d'offre (surenchère « seulement », pourcentages à un
chiffre).
"""
from __future__ import annotations

import pytest

from app.services.claim_policy import (
    is_acceptance_promise, is_contract_promise,
    is_unconditional_acceptance_promise, is_unconditional_contract_promise,
    is_unconditional_outcome_promise, requirements_for)
from app.services.qa_service import _financing_findings


def lab(value):
    return getattr(value, "value", value)


def qa_codes(text, offer=None):
    return [f["code"] for f in _financing_findings(
        {"body": text, "title": "T", "meta_title": "T",
         "meta_description": "D"}, offer)]


# (revendication, catégorie attendue, code QA bloquant attendu)
SG_CORPUS = [
    ("Le tarif est garanti à 0,27 €/kWh pendant 25 ans.",
     "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
    ("Vous payez seulement 150 €.",
     "FINANCING_PROMISE", "OFFER_FACT_OVERCLAIM"),
    ("L'installation ne vous coûte que 150 €.",
     "FINANCING_PROMISE", "OFFER_FACT_OVERCLAIM"),
    ("Aucun crédit bancaire n'est nécessaire.",
     "FINANCING_PROMISE", "UNCONDITIONAL_FINANCING_PROMISE"),
    ("Votre banque vous refuse ? SG Solution vous accepte.",
     "ELIGIBILITY", "UNCONDITIONAL_ACCEPTANCE_PROMISE"),
    ("Même si vous n'êtes pas finançable, vous êtes accepté.",
     "ELIGIBILITY", "UNCONDITIONAL_ACCEPTANCE_PROMISE"),
    ("Tout le monde est accepté.",
     "ELIGIBILITY", "UNCONDITIONAL_ACCEPTANCE_PROMISE"),
    ("Votre facture ne pourra plus augmenter.",
     "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
    ("Vous êtes protégé de toutes les hausses pendant 25 ans.",
     "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
    ("Le prix de rachat baisse de 4 % tous les ans.",
     "CONTRACT_PROMISE", "UNREGISTERED_OFFER_FACT"),
    ("Après 25 ans, l'installation devient gratuitement votre propriété.",
     "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
    ("Les panneaux se paient tout seuls.",
     "FINANCING_PROMISE", "UNCONDITIONAL_FINANCING_PROMISE"),
    ("Vous économisez forcément par rapport au marché.",
     "GUARANTEED_SAVINGS", "UNCONDITIONAL_OUTCOME_PROMISE"),
]


class TestTheThirteenClaims:
    @pytest.mark.parametrize("claim,category,_", SG_CORPUS)
    def test_category_and_risk(self, solar_profile, claim, category, _):
        requirements = requirements_for(claim, solar_profile)
        assert lab(requirements.category) == category, claim
        assert lab(requirements.risk) == "HIGH", claim

    @pytest.mark.parametrize("claim,_,code", SG_CORPUS)
    def test_qa_blocks_without_a_registry(self, claim, _, code):
        assert code in qa_codes(claim, None), claim

    @pytest.mark.parametrize("claim,_,code", SG_CORPUS)
    def test_qa_findings_are_blocking(self, claim, _, code):
        findings = _financing_findings(
            {"body": claim, "title": "T", "meta_title": "T",
             "meta_description": "D"}, None)
        assert findings and all(f["blocking"] is True for f in findings), claim


class TestEachBranchEarnsItsPlace:
    """Une phrase par alternance qui n'était couverte que par une voisine —
    les quatre survivants du premier lot de mutants, chacun tué par la
    variante qui n'a que SA branche pour être attrapée."""

    @pytest.mark.parametrize("claim,category,code", [
        # `ne pourra plus` sans « augmenter » (S02)
        ("Votre facture ne pourra plus grimper.",
         "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
        # « prix de rachat » nu, sans verbe de baisse (S04)
        ("Le prix de rachat est communiqué chaque année.",
         "CONTRACT_PROMISE", "UNCONDITIONAL_CONTRACT_PROMISE"),
        # « vous êtes accepté » sans refus ni finançable autour (S07)
        ("Vous êtes accepté dès la signature.",
         "ELIGIBILITY", "UNCONDITIONAL_ACCEPTANCE_PROMISE"),
        # refus→accepté dans UNE seule phrase (S08)
        ("Les dossiers refusés par la banque sont acceptés.",
         "ELIGIBILITY", "UNCONDITIONAL_ACCEPTANCE_PROMISE"),
    ])
    def test_the_lone_branch_catches_it(self, solar_profile, claim, category,
                                        code):
        assert lab(requirements_for(claim, solar_profile).category) == category
        assert code in qa_codes(claim), claim


class TestTheHonestFormsPass:
    """La préqualification a droit à sa phrase ; la promesse, non."""

    @pytest.mark.parametrize("sentence", [
        "Selon l'analyse de votre dossier, votre demande peut être acceptée.",
        "Votre situation semble correspondre aux premiers critères, sous "
        "réserve de l'analyse de votre dossier par SG Solution.",
        "Selon le contrat proposé, le tarif peut être fixé pour la durée.",
        "Les conditions exactes vous sont présentées lors de l'étude.",
        "Selon votre consommation, les économies peuvent varier.",
    ])
    def test_conditional_forms_raise_nothing(self, sentence):
        assert qa_codes(sentence) == [], sentence

    def test_meme_si_is_not_a_condition(self):
        # « Même si » est une concession qui RENFORCE la promesse — elle a
        # chevauché l'exemption du « si » nu jusqu'à cette mesure.
        assert is_unconditional_acceptance_promise(
            "Même si vous n'êtes pas finançable, vous êtes accepté.") is True
        # Le vrai « si » conditionnel continue de fonctionner.
        assert is_unconditional_contract_promise(
            "Si le contrat le prévoit, le tarif est fixé pour la durée.") is False


class TestFactVersusMarketClaim:
    """0,27 €/kWh au registre n'autorise JAMAIS un comparatif marché."""

    PUBLISHABLE = {"version": "sg-v1", "status": "validated",
                   "publishable": True, "pending_legal_review": False,
                   "registered_numbers": {"027", "25", "150", "4"}}

    def test_a_registered_fact_stated_plainly_is_allowed(self):
        assert qa_codes("Les frais administratifs sont de 150 €, une seule "
                        "fois, à la signature.", self.PUBLISHABLE) == []

    def test_the_totality_framing_blocks_even_registered(self):
        assert "OFFER_FACT_OVERCLAIM" in qa_codes(
            "Vous payez seulement 150 €.", self.PUBLISHABLE)

    def test_guaranteed_wording_blocks_even_registered(self):
        # Le chiffre est au registre ; le mot « garanti » n'y est pas — sa
        # formulation appartient à la matrice juridique.
        assert "UNCONDITIONAL_CONTRACT_PROMISE" in qa_codes(
            "Le tarif est garanti pendant 25 ans.", self.PUBLISHABLE)

    def test_a_market_comparison_is_never_licensed_by_the_registry(self):
        assert "UNCONDITIONAL_OUTCOME_PROMISE" in qa_codes(
            "Vous économisez forcément par rapport au marché.",
            self.PUBLISHABLE)

    def test_a_market_sentence_stays_a_market_sentence(self):
        # Le garde-fou ne doit pas avaler les phrases de marché du corpus réel.
        assert qa_codes("Le tarif de nuit est à 0,05 €/kWh chez certains "
                        "fournisseurs.", self.PUBLISHABLE) == []


class TestTheEdgesStillHold:
    """Le durcissement ne doit pas s'être élargi dans la prose ordinaire."""

    @pytest.mark.parametrize("text,expected", [
        # La garantie PRODUIT du fabricant n'est pas une promesse de contrat :
        # elle mesure GENERAL (aucun terme du lexique produit dans la phrase),
        # et surtout PAS CONTRACT_PROMISE — c'est l'arête épinglée ici.
        ("Les panneaux bénéficient d'une garantie constructeur de 25 ans.",
         "GENERAL"),
        ("Vous payez votre facture d'électricité chaque mois à votre "
         "fournisseur.", "GENERAL"),
        ("Les prix de l'électricité ont augmenté en 2025.", "ENERGY_PRICE"),
        ("Sans entretien particulier, les panneaux durent 25 ans.", "GENERAL"),
    ])
    def test_ordinary_prose_keeps_its_category(self, solar_profile, text,
                                               expected):
        assert lab(requirements_for(text, solar_profile).category) == expected

    def test_a_product_warranty_is_not_a_contract_promise(self):
        assert is_contract_promise(
            "Les panneaux bénéficient d'une garantie constructeur de "
            "25 ans.") is False

    def test_accepting_an_argument_is_not_accepting_a_person(self):
        assert is_acceptance_promise(
            "Le gestionnaire de réseau accepte les demandes de raccordement "
            "en ligne.") is False

    def test_no_projection_is_ever_computed(self):
        # « 4 % par an » n'autorise pas « -40 % après 10 ans » : la projection
        # n'existe nulle part dans le registre, donc ses chiffres sont des
        # inventions et bloquent.
        offer = {"version": "sg-v1", "publishable": True,
                 "registered_numbers": {"4", "25", "027", "150"}}
        assert "UNREGISTERED_OFFER_FACT" in qa_codes(
            "Après 10 ans, le prix de rachat a baissé de 40 %.", offer)


class TestOutcomePromiseInMetadata:
    def test_the_meta_description_is_guarded_too(self):
        codes = [f["code"] for f in _financing_findings(
            {"body": "Le projet est décrit lors de l'étude personnalisée.",
             "title": "T", "meta_title": "T",
             "meta_description": "Vous économisez forcément avec le solaire."},
            None)]
        assert "UNCONDITIONAL_OUTCOME_PROMISE" in codes

    def test_conditional_savings_in_meta_pass(self):
        codes = [f["code"] for f in _financing_findings(
            {"body": "Le projet est décrit lors de l'étude personnalisée.",
             "title": "T", "meta_title": "T",
             "meta_description": "Selon votre profil, des économies peuvent "
                                 "être réalisées."}, None)]
        assert codes == []


def test_the_outcome_predicate_is_conditional_aware():
    assert is_unconditional_outcome_promise(
        "Vous économisez forcément.") is True
    assert is_unconditional_outcome_promise(
        "Selon votre profil, vous économisez forcément.") is False
