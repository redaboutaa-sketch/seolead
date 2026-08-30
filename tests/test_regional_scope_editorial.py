"""Regionally determined subjects are written in regional scope.

Measured on 2026-08-30: twenty official sources asked the real payback question,
and not one states a payback for Belgium as a whole. The regions set the terms —
prosumer tariff, green certificates, premiums — and the regions publish the
figures. Belgian solar profitability is not a national quantity.

The scope rule does not move. Regional evidence still cannot establish a
country-wide claim, and two concordant regional sources are not one Belgian
claim — they are two regional claims. What changes is what a region-less
sentence IS, and what the writer is told to do with it.
"""
from __future__ import annotations

import pytest

from app.core.enums import (ClaimCategory, EvidenceStatus,
                            ObservationStatus)
from app.services import brief_service
from app.services.claim_extraction import AtomicClaim
from app.services.claim_policy import is_regionally_determined, requirements_for
from app.services.evidence_model import EvidenceRef, evaluate_claim
from app.services.factual_qa_v2 import run_factual_qa_v2
from app.services.freshness import FreshnessStatus
from app.services.region import Region, names_region
from app.services.relevance import RelevanceStatus
from app.services.source_quality import SourceQuality
from app.verticals.profile import load_profile

PAYBACK = "Le retour sur investissement est généralement compris entre 6 et 9 ans."


@pytest.fixture
def solar():
    return load_profile("SOLAR_BE")


def _evidence(region: Region, *, supports=True, ref="s1") -> EvidenceRef:
    return EvidenceRef(
        source_ref=ref, passage=PAYBACK, url="https://x.be/p",
        source_type="official", quality=SourceQuality.OFFICIAL,
        relevance=RelevanceStatus.RELEVANT,
        observation=ObservationStatus.OBSERVED,
        published_at=None, retrieved_at=None, provider="tavily_authoritative",
        supports=supports, region=region,
        freshness_status=FreshnessStatus.UNDATED_CURRENT)


class TestWhichSubjectsBelgiumSetsRegionally:
    @pytest.mark.parametrize("category", [
        ClaimCategory.ROI, ClaimCategory.SUBSIDY, ClaimCategory.GRID_RULE,
        ClaimCategory.TARIFF, ClaimCategory.GRID_FEE, ClaimCategory.ELIGIBILITY,
    ])
    def test_the_declared_ones(self, category, solar):
        assert is_regionally_determined(category, solar) is True

    @pytest.mark.parametrize("category", [
        ClaimCategory.GENERAL, ClaimCategory.TAX, ClaimCategory.MARKET_AVERAGE,
    ])
    def test_and_the_ones_that_are_not(self, category, solar):
        """VAT is federal. A general fact about sunlight has no region at all."""
        assert is_regionally_determined(category, solar) is False

    def test_it_is_configuration_not_code(self, solar):
        """A unitary market declares none, and nothing here would change."""
        generic = load_profile("TEST_GENERIC")
        assert is_regionally_determined(ClaimCategory.ROI, generic) is False


class TestARegionlessClaimTakesTheScopeOfItsEvidence:
    def test_the_seventeen_roi_claims_stop_dying_on_a_country_wide_bar(self, solar):
        """The measured failure: payback, no region named, Walloon evidence.

        The market default stamped it BE, and the scope rule then refused the
        only sources that supported it.
        """
        evaluated = evaluate_claim(
            AtomicClaim(text=PAYBACK, passage=PAYBACK, source_ref="s1", offset=0),
            [_evidence(Region.BE_WAL), _evidence(Region.BE_WAL, ref="s2")],
            solar, default_region=Region.BE)
        assert evaluated.claim_region is Region.BE_WAL
        assert evaluated.status is not EvidenceStatus.UNSUPPORTED
        assert "scoped to BE-WAL" in (evaluated.as_dict()["scope_note"] or "")

    def test_evidence_from_two_regions_is_not_one_belgian_claim(self, solar):
        """Two regional claims, not one national one. The article breaks them out."""
        evaluated = evaluate_claim(
            AtomicClaim(text=PAYBACK, passage=PAYBACK, source_ref="s1", offset=0),
            [_evidence(Region.BE_WAL), _evidence(Region.BE_VLG, ref="s2")],
            solar, default_region=Region.BE)
        assert evaluated.claim_region is Region.BE
        assert evaluated.as_dict()["scope_note"] is None

    def test_a_claim_that_names_its_region_is_untouched(self, solar):
        text = "En Wallonie, le retour sur investissement est de 8 ans."
        evaluated = evaluate_claim(
            AtomicClaim(text=text, passage=text, source_ref="s1", offset=0),
            [_evidence(Region.BE_WAL)], solar, default_region=Region.BE)
        assert evaluated.claim_region is Region.BE_WAL
        assert evaluated.as_dict()["scope_note"] is None

    def test_a_category_the_market_does_not_set_regionally_is_untouched(self,
                                                                        solar):
        """VAT is federal: Walloon evidence must NOT rescope a tax claim."""
        text = "Le taux de TVA applicable est de 6 %."
        evaluated = evaluate_claim(
            AtomicClaim(text=text, passage=text, source_ref="s1", offset=0),
            [_evidence(Region.BE_WAL)], solar, default_region=Region.BE)
        assert evaluated.claim_region is Region.BE


class TestTheBriefCarriesTheScope:
    def _facts(self):
        return [
            {"fact": PAYBACK, "category": "ROI", "region": "BE-WAL",
             "regionally_determined": True, "scope_note": "…"},
            {"fact": "De terugverdientijd bedraagt 7 jaar.", "category": "ROI",
             "region": "BE-VLG", "regionally_determined": True,
             "scope_note": "…"},
            {"fact": "Les panneaux produisent plus au printemps.",
             "category": "GENERAL", "region": "BE",
             "regionally_determined": False, "scope_note": None},
        ]

    def test_it_groups_the_facts_by_region(self):
        scope = brief_service.regional_scope(self._facts())
        assert scope["subnational_regions_with_evidence"] == ["BE-VLG", "BE-WAL"]
        assert scope["applies_to_categories"] == ["ROI"]
        assert len(scope["facts_by_region"]["BE-WAL"]) == 1

    def test_it_names_the_regions_no_fact_covers(self):
        """Their absence is a research gap, not evidence the subject is moot.

        Without this the writer completes the breakdown from its own knowledge
        to make it look whole, which is the invention the page must never make.
        """
        scope = brief_service.regional_scope(self._facts())
        assert scope["silent_regions"] == ["BE-BRU"]

    def test_a_fact_with_no_regional_subject_is_left_out_of_the_rule(self):
        scope = brief_service.regional_scope(self._facts())
        assert "Les panneaux produisent plus au printemps." not in [
            f for facts in scope["facts_by_region"].values() for f in facts]


class TestTheRegionMustSurviveIntoTheSentence:
    """The failure the rescoping makes possible, and the guard that refuses it.

    Scoping a claim to BE-WAL makes it provable. It also lets the writer state a
    Walloon figure flat, telling a Flemish reader something false about their
    own region — with a perfectly sourced number.
    """

    CLAIM = {"claim": PAYBACK, "category": "ROI", "claim_risk": "HIGH",
             "evidence_status": "SUPPORTED", "region": "BE-WAL",
             "regionally_determined": True, "supported": True}

    def _qa(self, body, solar):
        package = {"claims": [self.CLAIM], "supported_claims": [self.CLAIM]}
        return run_factual_qa_v2({"body": body}, package, solar)

    def test_stating_a_walloon_figure_flat_is_blocking(self, solar):
        body = ("# Rentabilité\n\n"
                "Le retour sur investissement est généralement compris entre 6 "
                "et 9 ans.\n")
        codes = {f["code"] for f in self._qa(body, solar)["blocking_issues"]}
        assert "REGIONAL_SCOPE_NOT_STATED" in codes

    def test_naming_the_region_in_the_same_sentence_passes(self, solar):
        body = ("# Rentabilité\n\n"
                "En Wallonie, le retour sur investissement est généralement "
                "compris entre 6 et 9 ans.\n")
        codes = {f["code"] for f in self._qa(body, solar)["blocking_issues"]}
        assert "REGIONAL_SCOPE_NOT_STATED" not in codes

    def test_a_ventilated_sentence_passes(self, solar):
        """« en Wallonie : X ; en Flandre : Y » names its region among others."""
        body = ("# Rentabilité\n\n"
                "Le retour sur investissement est généralement compris entre 6 "
                "et 9 ans en Wallonie, et entre 7 et 10 ans en Flandre.\n")
        codes = {f["code"] for f in self._qa(body, solar)["blocking_issues"]}
        assert "REGIONAL_SCOPE_NOT_STATED" not in codes

    def test_naming_the_wrong_region_is_still_blocking(self, solar):
        body = ("# Rentabilité\n\n"
                "À Bruxelles, le retour sur investissement est généralement "
                "compris entre 6 et 9 ans.\n")
        codes = {f["code"] for f in self._qa(body, solar)["blocking_issues"]}
        assert "REGIONAL_SCOPE_NOT_STATED" in codes

    def test_a_claim_the_draft_never_states_is_not_flagged(self, solar):
        """An unused claim is a research surplus, not a draft defect."""
        body = "# Rentabilité\n\nLes panneaux produisent toute l'année.\n"
        codes = {f["code"] for f in self._qa(body, solar)["blocking_issues"]}
        assert "REGIONAL_SCOPE_NOT_STATED" not in codes


class TestNamesRegionIsAdditive:
    def test_a_ventilated_sentence_names_every_region_it_lists(self):
        text = "En Wallonie : 8 ans ; en Flandre : 7 ans ; à Bruxelles : 9 ans."
        for region in (Region.BE_WAL, Region.BE_VLG, Region.BE_BRU):
            assert names_region(text, region) is True

    def test_it_does_not_answer_for_a_region_that_is_absent(self):
        assert names_region("En Wallonie, 8 ans.", Region.BE_VLG) is False
