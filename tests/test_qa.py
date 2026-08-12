"""QA gate.

The deterministic layer is the only thing standing between a generated draft and
an operator's approval queue, so these tests are mostly about what it must
*block*. The unsupported-number test is the single most important one in the
suite: a page stating a solar price nobody researched is the most damaging output
this system could produce.
"""
from __future__ import annotations

import pytest

from app.core.enums import QAStatus
from app.services.qa_service import run_deterministic_qa

BODY = """# Prix des panneaux solaires en Belgique

## Ce qui détermine le prix

Le prix dépend de la puissance installée, du type de toiture et de la complexité
de la pose. Un installateur détaille pourquoi deux devis pour une même maison
peuvent différer selon l'onduleur, la structure de fixation et la distance au
tableau électrique.

## Comment comparer deux devis

Comparez le matériel proposé, la garantie de pose et les travaux de raccordement.
Demandez le détail poste par poste plutôt qu'un montant global, et vérifiez ce qui
est inclus dans chaque proposition avant de vous décider.

## Ce qu'il faut vérifier avant de signer

Vérifiez la couverture d'assurance de l'installateur, les délais annoncés et les
conditions de raccordement au réseau. Ces éléments varient d'un prestataire à
l'autre et méritent une question directe.

## Prochaine étape

Demandez un devis personnalisé pour obtenir une estimation adaptée à votre
toiture et à votre consommation réelle.
"""


def _draft(**overrides) -> dict:
    draft = {
        "title": "Prix des panneaux solaires en Belgique",
        "meta_title": "Prix panneaux solaires Belgique",
        "meta_description": "Ce qui fait varier le prix d'une installation "
                            "photovoltaïque en Belgique et comment comparer deux devis.",
        "body": BODY,
    }
    draft.update(overrides)
    return draft


def _brief(**overrides) -> dict:
    brief = {
        "primary_query": "prix panneaux solaires Belgique",
        "content_type": "GUIDE",
        "search_intent": "COMMERCIAL",
        "target_audience": "Propriétaires belges",
        "objective": "Générer des demandes de devis",
        "required_facts": [
            {"fact": "Le prix dépend de la puissance installée, du type de toiture "
                     "et de la complexité de la pose.",
             "source_ref": "s1", "observability": "OBSERVED"},
            {"fact": "Deux devis peuvent différer selon l'onduleur, la structure de "
                     "fixation et la distance au tableau électrique.",
             "source_ref": "s2", "observability": "OBSERVED"},
        ],
        "required_sources": [
            {"ref": "s1", "url": "https://example.invalid/a", "title": "A",
             "published_at": "2026-08-01T00:00:00+00:00"},
        ],
        "cautionary_claims": [
            {"topic": "prime", "rule": "may_not_be_asserted_without_dated_source",
             "has_supported_evidence": False},
        ],
        "cta_strategy": {"code": "quote_request", "label": "Demander un devis"},
        "missing_information": [],
    }
    brief.update(overrides)
    return brief


def _package(**overrides) -> dict:
    package = {
        "facts": [
            {"fact": "Le prix dépend de la puissance installée."},
            {"fact": "Deux devis peuvent différer selon l'onduleur."},
        ],
        "sources": [{"title": "Guide des prix"}],
    }
    package.update(overrides)
    return package


def _codes(verdict: dict) -> set[str]:
    return {f["code"] for f in verdict["findings"]}


def _blocking_codes(verdict: dict) -> set[str]:
    return {f["code"] for f in verdict["blocking_issues"]}


class TestBaseline:
    def test_a_well_formed_draft_passes(self, solar_profile):
        verdict = run_deterministic_qa(_draft(), _brief(), _package(), solar_profile)
        assert verdict["status"] == QAStatus.PASSED.value, verdict["blocking_issues"]
        assert verdict["blocking_issues"] == []


class TestPresence:
    @pytest.mark.parametrize("field,code", [
        ("title", "MISSING_TITLE"),
        ("body", "MISSING_BODY"),
        ("meta_title", "MISSING_META_TITLE"),
        ("meta_description", "MISSING_META_DESCRIPTION"),
    ])
    def test_missing_field_blocks(self, field, code, solar_profile):
        verdict = run_deterministic_qa(_draft(**{field: ""}), _brief(), _package(),
                                       solar_profile)
        assert code in _blocking_codes(verdict)

    def test_overlong_meta_is_advisory_not_blocking(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(meta_title="x" * 90), _brief(), _package(), solar_profile)
        assert "META_TITLE_TOO_LONG" in _codes(verdict)
        assert "META_TITLE_TOO_LONG" not in _blocking_codes(verdict)


class TestStructure:
    def test_missing_h1_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(body=BODY.replace("# Prix", "Prix", 1)), _brief(), _package(),
            solar_profile)
        assert "NO_H1" in _blocking_codes(verdict)

    def test_multiple_h1_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(body=BODY + "\n# Un deuxième titre principal\n"), _brief(),
            _package(), solar_profile)
        assert "MULTIPLE_H1" in _blocking_codes(verdict)

    def test_short_body_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(body="# Titre\n\n## Section\n\nTrop court."), _brief(), _package(),
            solar_profile)
        assert "BODY_TOO_SHORT" in _blocking_codes(verdict)


class TestFabrication:
    def test_number_absent_from_evidence_blocks(self, solar_profile):
        """The most important check in the system."""
        body = BODY.replace(
            "Le prix dépend",
            "Une installation coûte 8 500 € en moyenne. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" in _blocking_codes(verdict)

    def test_number_present_in_evidence_passes(self, solar_profile):
        body = BODY.replace(
            "Le prix dépend",
            "Une source relève un ordre de grandeur de 8 500 €. Le prix dépend")
        package = _package(facts=[
            {"fact": "Une installation résidentielle se situe autour de 8 500 € "
                     "selon le guide."},
            {"fact": "Le prix dépend de la puissance installée."},
            {"fact": "Deux devis peuvent différer selon l'onduleur."},
        ])
        verdict = run_deterministic_qa(_draft(body=body), _brief(), package,
                                       solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" not in _blocking_codes(verdict)

    def test_percentage_absent_from_evidence_blocks(self, solar_profile):
        body = BODY.replace("Le prix dépend",
                            "Vous économiserez 40 % sur votre facture. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" in _blocking_codes(verdict)

    def test_years_are_not_treated_as_fabricated_numbers(self, solar_profile):
        body = BODY.replace("Le prix dépend",
                            "Depuis 2024, les pratiques ont changé. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" not in _blocking_codes(verdict)

    def test_quantified_restricted_topic_blocks(self, solar_profile):
        body = BODY.replace(
            "Le prix dépend",
            "La prime régionale couvre 1 750 euros du montant. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        blocking = _blocking_codes(verdict)
        assert "RESTRICTED_CLAIM_QUANTIFIED" in blocking or \
               "UNSUPPORTED_NUMERIC_CLAIM" in blocking

    def test_forbidden_phrase_blocks(self, solar_profile):
        body = BODY.replace("Le prix dépend",
                            "Nous offrons un rendement garanti. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "FORBIDDEN_PHRASE" in _blocking_codes(verdict)

    def test_placeholder_leakage_blocks(self, solar_profile):
        body = BODY.replace("Le prix dépend", "TODO: write this. Le prix dépend")
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "PLACEHOLDER_LEAKED" in _blocking_codes(verdict)


class TestEvidenceUse:
    def test_draft_ignoring_every_supported_fact_blocks(self, solar_profile):
        body = ("# Titre générique\n\n## Une section\n\n" + "Du contenu de remplissage "
                "sans rapport avec les faits fournis. " * 30 +
                "\n\n## Une autre section\n\nEncore du contenu générique. " * 5)
        verdict = run_deterministic_qa(_draft(body=body), _brief(), _package(),
                                       solar_profile)
        assert "REQUIRED_FACTS_UNUSED" in _blocking_codes(verdict)

    def test_no_supported_evidence_at_all_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(), _brief(required_facts=[]), _package(), solar_profile)
        assert "NO_SUPPORTED_EVIDENCE" in _blocking_codes(verdict)

    def test_no_traceable_sources_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(), _brief(required_sources=[]), _package(), solar_profile)
        assert "NO_TRACEABLE_SOURCES" in _blocking_codes(verdict)


class TestSeoPolicy:
    def test_keyword_stuffing_blocks(self, solar_profile):
        stuffed = "# Titre\n\n## Section\n\n" + \
                  "prix panneaux solaires Belgique " * 60 + \
                  "\n\n## Autre section\n\nUn peu de texte normal ici pour la forme."
        verdict = run_deterministic_qa(_draft(body=stuffed), _brief(), _package(),
                                       solar_profile)
        assert "KEYWORD_STUFFING" in _blocking_codes(verdict)

    def test_duplicate_title_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(), _brief(), _package(), solar_profile,
            existing_titles=["  prix DES panneaux solaires en belgique  "])
        assert "DUPLICATE_TITLE" in _blocking_codes(verdict)

    def test_missing_cta_blocks(self, solar_profile):
        verdict = run_deterministic_qa(
            _draft(), _brief(cta_strategy={"code": None}), _package(), solar_profile)
        assert "NO_CTA" in _blocking_codes(verdict)


class TestScoring:
    def test_score_falls_with_blocking_issues(self, solar_profile):
        clean = run_deterministic_qa(_draft(), _brief(), _package(), solar_profile)
        broken = run_deterministic_qa(_draft(title="", meta_title=""), _brief(),
                                      _package(), solar_profile)
        assert clean["score"] > broken["score"]

    def test_score_is_not_the_gate(self, solar_profile):
        """A high score with a blocking issue must still fail."""
        verdict = run_deterministic_qa(_draft(meta_description=""), _brief(),
                                       _package(), solar_profile)
        assert verdict["status"] == QAStatus.FAILED.value
        assert verdict["score"] > 50
