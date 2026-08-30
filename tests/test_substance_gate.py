"""The substance floor: a page must state what was established, not gesture at it.

A draft scored 100/100 on factual QA and said almost nothing. Every sentence
traced to evidence; there was barely any evidence in it. One number in the whole
article, and a FAQ answering « cela varie selon plusieurs facteurs » to « quelle
est la rentabilité moyenne ? » — while the package held « 6 à 9 ans », « 8 à 12
ans » and « entre 7,3 % et 8,4 % ».

Factual QA certifies traceability. This floor certifies there was something to
trace. It is an editorial judgement, so the number lives in vertical
configuration and the owner ratifies it.
"""
from __future__ import annotations

import pytest

from app.services.qa_service import run_seo_qa_v2
from app.verticals.profile import load_profile

# The real body of draft 0372ddb2, as `site preview-draft` rendered it on
# 2026-08-30. Nine sections, five substantive statements, one figure.
HOLLOW_BODY = """# Guide Complet sur la Rentabilité des Panneaux Solaires en Belgique

## Introduction

Ce guide a pour objectif d'informer les propriétaires de maisons individuelles
et les petites entreprises en Belgique sur la rentabilité des panneaux solaires.

## Les Notions de Base des Panneaux Solaires

Les panneaux solaires sont des dispositifs qui convertissent la lumière du
soleil en électricité. L'électricité produite peut être utilisée directement
dans votre maison ou injectée dans le réseau.

## Facteurs Influant sur la Rentabilité

La rentabilité d'une installation photovoltaïque dépend de plusieurs facteurs,
notamment l'orientation de votre toiture, l'ensoleillement, et votre
consommation d'électricité.

## Questions Fréquemment Posées

**Quelle est la rentabilité moyenne d'un panneau solaire ?**

Cela varie selon plusieurs facteurs, dont l'orientation de la toiture et les
habitudes de consommation.

## Prochaine étape

Pour en savoir plus, n'hésitez pas à recevoir le guide complet.
"""

# What the package had actually established, and the article never said.
ESTABLISHED = [
    "En Wallonie, le retour sur investissement est compris entre 6 et 9 ans.",
    "En Flandre, une installation est rentabilisée après 8 à 12 ans.",
    "En Wallonie, la rentabilité des petites installations atteint 7,3 % à 8,4 %.",
    "Le prix moyen est d'environ 1 €/Wc hors TVA.",
    "Une installation de 1 kWc produit entre 900 et 1000 kWh par an en Belgique.",
    "L'autoconsommation doit dépasser 40 % pour rentabiliser l'installation.",
    "À Bruxelles, les certificats verts sont octroyés pendant dix ans.",
    "En Wallonie comme en Flandre, les primes directes ont été supprimées.",
    "Le tarif prosumer est facturé par le gestionnaire de réseau wallon.",
    "Une installation de 3,5 kWc couvre un ménage de quatre personnes.",
]


@pytest.fixture
def solar():
    return load_profile("SOLAR_BE")


def _brief(facts):
    return {
        "primary_query": "rentabilité panneaux solaires Belgique",
        "required_facts": [{"fact": f, "source_ref": "s1"} for f in facts],
        "required_sources": [{"ref": "s1", "url": "https://energie.wallonie.be/p",
                              "title": "T", "published_at": None}],
        "cautionary_claims": [], "cta_strategy": {"code": "ESTIMATE_REQUEST"},
    }


def _codes(verdict):
    return {f["code"] for f in verdict["blocking_issues"]}


class TestTheRatifiedFloor:
    def test_solar_be_ratified_eight(self, solar):
        """Seven outline sections plus a FAQ: one supported fact each."""
        assert solar.minimum_supported_facts_used == 8

    def test_a_vertical_that_ratifies_nothing_is_not_gated(self):
        assert load_profile("TEST_GENERIC").minimum_supported_facts_used == 0


class TestTheCanary:
    """The real hollow article must fall. That is the whole test."""

    def test_the_hollow_draft_is_now_blocking(self, solar):
        verdict = run_seo_qa_v2({"title": "T", "body": HOLLOW_BODY,
                                 "meta_title": "T", "meta_description": "D"},
                                _brief(ESTABLISHED), {}, solar,
                                existing_titles=[])
        assert "REQUIRED_FACTS_UNDERUSED" in _codes(verdict)
        assert verdict["status"] == "FAILED"

    def test_the_finding_says_how_far_short_it_fell(self, solar):
        verdict = run_seo_qa_v2({"title": "T", "body": HOLLOW_BODY,
                                 "meta_title": "T", "meta_description": "D"},
                                _brief(ESTABLISHED), {}, solar,
                                existing_titles=[])
        message = next(f["message"] for f in verdict["blocking_issues"]
                       if f["code"] == "REQUIRED_FACTS_UNDERUSED")
        assert "floor of 8" in message

    def test_an_article_that_states_what_was_established_passes_the_floor(self,
                                                                          solar):
        """The counter-proof. Without it the gate could just be a bar too high."""
        body = "# Rentabilité des panneaux solaires en Belgique\n\n"
        for index, fact in enumerate(ESTABLISHED):
            body += f"## Section {index + 1}\n\n{fact}\n\n"
        verdict = run_seo_qa_v2({"title": "T", "body": body, "meta_title": "T",
                                 "meta_description": "D"},
                                _brief(ESTABLISHED), {}, solar,
                                existing_titles=[])
        assert "REQUIRED_FACTS_UNDERUSED" not in _codes(verdict)


class TestTheFloorIsAbsoluteNotAFraction:
    """The case that separates the two rules, and the reason for the change.

    The old bar was a third of whatever happened to be supplied. With ten facts
    supplied it sat at three, so an article stating five of ten passed — half
    the established evidence left on the floor, and the page called publishable.
    The ratified floor is eight, and it catches exactly this.

    Without this test the change is unpinned: the hollow article of `TestCanary`
    falls under either rule, so it cannot tell them apart.
    """

    def _body_using(self, count):
        body = "# Rentabilité des panneaux solaires en Belgique\n\n"
        for index, fact in enumerate(ESTABLISHED[:count]):
            body += f"## Section {index + 1}\n\n{fact}\n\n"
        return body

    def test_five_of_ten_used_to_pass_and_now_does_not(self, solar):
        supplied = ESTABLISHED           # ten facts -> old bar was three
        verdict = run_seo_qa_v2({"title": "T", "body": self._body_using(5),
                                 "meta_title": "T", "meta_description": "D"},
                                _brief(supplied), {}, solar, existing_titles=[])
        assert "REQUIRED_FACTS_UNDERUSED" in _codes(verdict)
        message = next(f["message"] for f in verdict["blocking_issues"]
                       if f["code"] == "REQUIRED_FACTS_UNDERUSED")
        assert "uses 5 supported fact(s) of 10" in message

    def test_eight_of_ten_clears_it(self, solar):
        verdict = run_seo_qa_v2({"title": "T", "body": self._body_using(8),
                                 "meta_title": "T", "meta_description": "D"},
                                _brief(ESTABLISHED), {}, solar,
                                existing_titles=[])
        assert "REQUIRED_FACTS_UNDERUSED" not in _codes(verdict)


class TestThinResearchIsNamedAsSuch:
    def test_fewer_facts_than_the_floor_blames_the_research(self, solar):
        """Blaming the writer would send an operator to fix the wrong thing."""
        verdict = run_seo_qa_v2({"title": "T", "body": HOLLOW_BODY,
                                 "meta_title": "T", "meta_description": "D"},
                                _brief(ESTABLISHED[:3]), {}, solar,
                                existing_titles=[])
        assert "INSUFFICIENT_SUPPORTED_EVIDENCE" in _codes(verdict)
        assert "REQUIRED_FACTS_UNDERUSED" not in _codes(verdict)

    def test_no_supported_fact_at_all_is_still_its_own_finding(self, solar):
        verdict = run_seo_qa_v2({"title": "T", "body": HOLLOW_BODY,
                                 "meta_title": "T", "meta_description": "D"},
                                _brief([]), {}, solar, existing_titles=[])
        assert "NO_SUPPORTED_EVIDENCE" in _codes(verdict)


class TestTheWriterReceivesTheMatterNotASample:
    """Twelve of a hundred and nine, taken in package order, is not a brief.

    The run of 2026-08-30 established 109 supported claims and handed the writer
    twelve — eleven percent — then asked for a seven-section guide plus a FAQ.
    The gap was designed in, and it was filled the only ways it could be: with
    generalities, or with figures half-remembered from the passages. That second
    habit is the UNSUPPORTED_DRAFT_CLAIM that failed the run at score 67. It was
    never variance.
    """

    def _facts(self, n, category, region):
        return [{"category": category, "region": region, "fact": f"{category}{i}"}
                for i in range(n)]

    def test_selection_covers_the_subjects_instead_of_the_first_page(self):
        from app.services.brief_service import _spread
        facts = (self._facts(40, "ROI", "BE-WAL")
                 + self._facts(30, "SUBSIDY", "BE-VLG")
                 + self._facts(39, "GENERAL", "BE"))
        categories = {f["category"] for f in _spread(facts, 24)}
        assert categories == {"ROI", "SUBSIDY", "GENERAL"}, (
            "package order gave twelve facts about one subject and nothing "
            "about the rest")

    def test_it_returns_everything_when_there_is_room(self):
        from app.services.brief_service import _spread
        facts = self._facts(5, "ROI", "BE-WAL")
        assert _spread(facts, 24) == facts

    def test_the_ceiling_is_respected(self):
        from app.services.brief_service import _spread
        facts = self._facts(100, "ROI", "BE-WAL")
        assert len(_spread(facts, 24)) == 24

    def test_order_inside_a_subject_is_left_alone(self):
        """The package ranks by evidence strength; re-ranking would override it."""
        from app.services.brief_service import _spread
        facts = self._facts(30, "ROI", "BE-WAL")
        picked = [f["fact"] for f in _spread(facts, 24)]
        assert picked == [f["fact"] for f in facts[:24]]
