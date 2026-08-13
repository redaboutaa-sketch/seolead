"""Phase 3.4 — a price page must answer the price question, or say it cannot.

The Phase 3.3 live draft was titled "Prix des panneaux solaires en Belgique",
contained no price at all, and passed factual QA. That pass was vacuous: the page
asserted nothing checkable, so nothing could be checked. These regressions pin the
two honest outcomes and forbid the third.

The distinction they exist to protect is between *cautious* and *useless*. A page
with no eligible evidence that states no figure is cautious and correct. A page
handed six sourced figures that still states none is useless, and must block.
"""
from __future__ import annotations

import pytest

from app.core.enums import ClaimCategory, SearchIntent
from app.services.brief_service import build_brief_payload
from app.services.claim_extraction import extract_claim_set
from app.services.claim_policy import classify_category
from app.services.draft_service import build_generation_prompt
from app.services.passage_extraction import Passage
from app.services.price_normalization import (PriceBasis, VatStatus,
                                              extract_price_context,
                                              observed_range)
from app.services.qa_service import run_seo_qa_v2

SOLAR_QUERY = "prix panneaux solaires Belgique"

# Two real sentences from the Phase 3.4 live corpus, quoted rather than invented
# so the regressions exercise text the pipeline actually met.
LIVE_RANGE = ("Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à "
              "10 kWc, pose comprise.")
LIVE_TOTAL = ("Une installation standard de 5 kWc coûte environ 6.500 € à "
              "8.500 € TVAC, pose comprise.")


def _package(claims: list[dict]) -> dict:
    return {"query": SOLAR_QUERY, "market": "BE", "language": "fr",
            "intent": "COMMERCIAL", "facts": [], "sources": [],
            "supported_claims": claims, "user_questions": [],
            "unresolved_questions": [], "confidence_summary": {}}


def _claim(text: str, category: str, url: str = "https://example.be/prix") -> dict:
    return {"claim": text, "category": category, "evidence_status": "SUPPORTED",
            "source_ref": "web-001",
            "evidence": [{"url": url, "supports": True}]}


# ─── 1 & 2: the two honest outcomes ──────────────────────────────────────────

class TestCoreQuestion:
    def test_1_eligible_price_evidence_makes_the_answer_mandatory(self,
                                                                   solar_profile):
        brief = build_brief_payload(
            _package([_claim(LIVE_RANGE, "OBSERVED_PRICE_RANGE")]),
            profile=solar_profile, query=SOLAR_QUERY)

        assert brief["core_answer_status"] == "EVIDENCE_AVAILABLE"
        assert brief["must_answer_directly"] is True
        assert brief["core_answer_evidence"]["answers"], \
            "the figures the writer may use must reach the brief"
        # The answer leads the brief, not the third bullet of section four.
        assert LIVE_RANGE in brief["required_facts"][0]["fact"]

    def test_2_no_eligible_evidence_leaves_the_core_question_unresolved(
            self, solar_profile):
        """The outcome the mission calls acceptable: refuse rather than fake."""
        brief = build_brief_payload(
            _package([_claim("Les panneaux solaires durent environ 25 ans.",
                             "GENERAL")]),
            profile=solar_profile, query=SOLAR_QUERY)

        assert brief["core_answer_status"] == "CORE_QUESTION_UNRESOLVED"
        assert brief["must_answer_directly"] is False
        assert brief["core_answer_evidence"]["answers"] == []
        assert any("unresolved" in note.lower()
                   for note in brief["missing_information"]), \
            "an unanswerable core question must be stated as a limitation"

    def test_a_price_figure_with_no_stated_basis_is_not_an_answer(self,
                                                                  solar_profile):
        """€6 000 could be a total, a per-kWc rate or a per-m² figure."""
        brief = build_brief_payload(
            _package([_claim("Le montant s'élève à 6 000 €.", "MARKET_PRICE")]),
            profile=solar_profile, query=SOLAR_QUERY)
        assert brief["core_answer_status"] == "CORE_QUESTION_UNRESOLVED"

    def test_a_non_price_query_has_no_core_price_question(self, solar_profile):
        """Nothing here is Solar-specific: the vertical's vocabulary decides."""
        brief = build_brief_payload(
            _package([_claim(LIVE_RANGE, "OBSERVED_PRICE_RANGE")]),
            profile=solar_profile,
            query="comment fonctionne un onduleur photovoltaïque")
        assert brief["core_answer_status"] == "NOT_APPLICABLE"
        assert brief["must_answer_directly"] is False


# ─── 3: a vendor's own price is not the market ───────────────────────────────

class TestPriceTaxonomy:
    def test_3_vendor_advertised_price_is_not_a_belgian_market_average(
            self, solar_profile):
        vendor = classify_category("Nos tarifs pour 5 kWc sont de 4 400 €.",
                                   solar_profile)
        average = classify_category(
            "Le prix moyen d'une installation est de 5 000 € en Belgique.",
            solar_profile)
        assert vendor is ClaimCategory.VENDOR_PRICE
        assert average is ClaimCategory.MARKET_AVERAGE
        assert vendor is not average, \
            "one installer's rate card cannot establish a national average"

    def test_a_sourced_range_is_not_an_average_claim(self, solar_profile):
        """Phase 3.4's central taxonomy split.

        27 of 34 quantified price claims were blocked by the three-source
        market-average bar while asserting no average at all. A range reported BY
        a source is a statement about what that source observed.
        """
        assert classify_category(LIVE_RANGE,
                                 solar_profile) is ClaimCategory.OBSERVED_PRICE_RANGE


# ─── 4 & 5: ranges may only be formed from comparable observations ───────────

class TestObservedRange:
    def test_4_comparable_observations_may_form_an_observed_range(self):
        contexts = [extract_price_context(LIVE_RANGE),
                    extract_price_context(LIVE_TOTAL)]
        result = observed_range(contexts, minimum=2)

        assert result is not None
        assert result["basis"] == PriceBasis.TOTAL.value
        assert result["vat_status"] == VatStatus.INCLUDED.value
        assert result["low"] <= result["high"]
        assert result["observation_count"] >= 2
        assert "not a market average" in result["wording"], \
            "an observed sample must never be presented as an average"

    def test_5_incomparable_observations_may_not_form_a_range(self):
        """Per-kWc and whole-installation figures differ by an order of magnitude."""
        per_kwp = extract_price_context("Comptez 1 500 € par kWc installé.")
        total = extract_price_context(LIVE_TOTAL)
        assert per_kwp.basis is PriceBasis.PER_KWP
        assert total.basis is PriceBasis.TOTAL

        assert observed_range([per_kwp, total], minimum=2) is None, \
            "ranging across incompatible bases would invent a figure"

    def test_a_single_observation_is_not_a_range(self):
        assert observed_range([extract_price_context(LIVE_RANGE)], minimum=2) is None

    def test_vat_treatment_is_carried_not_assumed(self):
        excluded = extract_price_context("Le kit revient à 5 000 € HTVA.")
        included = extract_price_context(LIVE_TOTAL)
        assert excluded.vat is VatStatus.EXCLUDED
        assert included.vat is VatStatus.INCLUDED
        assert observed_range([excluded, included], minimum=2) is None


# ─── 6: no outbound competitor links ─────────────────────────────────────────

class TestExternalLinks:
    def test_6_the_writer_is_told_not_to_link_to_competitors(self, solar_profile):
        """Prompt prevention. QA enforcement is the second layer, tested below."""
        system, _ = build_generation_prompt(
            {"primary_query": SOLAR_QUERY, "content_type": "LANDING_PAGE",
             "search_intent": "COMMERCIAL", "target_audience": "x",
             "objective": "y", "recommended_title": "t", "outline": [],
             "key_questions": [], "required_facts": [], "required_sources": [],
             "missing_information": [], "cta_strategy": {}, "cautionary_claims": []},
            {"language": "fr", "market": "BE"})
        lowered = system.lower()
        assert "competitor" in lowered
        assert "markdown link" in lowered or "url" in lowered

    def test_an_external_link_in_the_body_still_blocks_at_qa(self, solar_profile):
        verdict = run_seo_qa_v2(
            {"title": "Prix", "body": "# Prix\n\nVoir [ce comparateur](https://autre.be).\n",
             "meta_title": "Prix", "meta_description": "d"},
            {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
             "key_questions": []},
            {"facts": [], "sources": []}, solar_profile)
        assert "EXTERNAL_LINK_IN_BODY" in {f["code"] for f in verdict["blocking_issues"]}


# ─── 7 & 8: silence blocks only when the evidence could have spoken ──────────

def _draft_without_a_figure() -> dict:
    body = ("# Prix des panneaux solaires en Belgique\n\n"
            "Le prix dépend de nombreux facteurs.\n\n"
            "## Ce qui influence le budget\n\n"
            "La surface, l'orientation et le type de matériel jouent un rôle.\n\n"
            "## Comment obtenir un chiffre\n\n"
            "Demandez une étude personnalisée auprès d'un installateur.\n")
    return {"title": "Prix des panneaux solaires en Belgique", "body": body,
            "meta_title": "Prix panneaux solaires", "meta_description": "d"}


class TestNoQuantifiedAnswerPolicy:
    def test_7_eligible_evidence_and_no_figure_is_blocking(self, solar_profile):
        verdict = run_seo_qa_v2(
            _draft_without_a_figure(),
            {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
             "key_questions": [], "core_question": SOLAR_QUERY,
             "core_answer_status": "EVIDENCE_AVAILABLE",
             "must_answer_directly": True,
             "core_answer_evidence": {"answers": [{"claim": LIVE_RANGE}],
                                      "observed_range": None}},
            {"facts": [], "sources": []}, solar_profile)

        codes = {f["code"] for f in verdict["blocking_issues"]}
        assert "NO_QUANTIFIED_ANSWER" in codes, \
            "given sourced figures, a page that states none has failed"

    def test_8_no_eligible_evidence_and_no_figure_is_not_blocked(self,
                                                                 solar_profile):
        """Blocking here would only pressure the next run into inventing a price."""
        verdict = run_seo_qa_v2(
            _draft_without_a_figure(),
            {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
             "key_questions": [], "core_question": SOLAR_QUERY,
             "core_answer_status": "CORE_QUESTION_UNRESOLVED",
             "must_answer_directly": False,
             "core_answer_evidence": {"answers": [], "observed_range": None}},
            {"facts": [], "sources": []}, solar_profile)

        codes = {f["code"] for f in verdict["blocking_issues"]}
        assert "NO_QUANTIFIED_ANSWER" not in codes
        assert "NO_QUANTIFIED_ANSWER" in {f["code"] for f in verdict["findings"]}, \
            "it is still reported — silence is a limitation even when it is correct"


class TestVatQualification:
    """VAT belongs to one figure, not to a list."""

    def _brief(self, vat_statuses: list[str]) -> dict:
        return {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
                "key_questions": [], "core_question": SOLAR_QUERY,
                "core_answer_status": "EVIDENCE_AVAILABLE",
                "must_answer_directly": True,
                "core_answer_evidence": {
                    "answers": [{"claim": LIVE_RANGE,
                                 "price_context": {"vat_status": v}}
                                for v in vat_statuses],
                    "observed_range": None}}

    def _draft(self, sentence: str) -> dict:
        body = ("# Prix\n\n## Fourchettes\n\nComptez entre 4.000 € et 14.000 € "
                f"TVAC.\n\n{sentence}\n\n## Variables\n\n"
                + "La taille du système et le matériel choisi. " * 30)
        return {"title": "Prix", "body": body, "meta_title": "Prix",
                "meta_description": "d"}

    def test_a_blanket_vat_statement_blocks_when_sources_did_not_say_it(
            self, solar_profile):
        """The defect in the first regenerated Phase 3.4 draft.

        One of six figures was marked TVAC; the page said "Ces prix incluent la
        TVA" about all of them, restating five prices by up to 21%.
        """
        verdict = run_seo_qa_v2(
            self._draft("Ces prix incluent la TVA."),
            self._brief(["INCLUDED", "UNKNOWN", "UNKNOWN"]),
            {"facts": [], "sources": [{"title": "4.000 14.000"}]}, solar_profile)
        assert "VAT_STATUS_GENERALISED" in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_a_blanket_vat_statement_is_fine_when_every_source_said_it(
            self, solar_profile):
        verdict = run_seo_qa_v2(
            self._draft("Ces prix incluent la TVA."),
            self._brief(["INCLUDED", "INCLUDED"]),
            {"facts": [], "sources": [{"title": "4.000 14.000"}]}, solar_profile)
        assert "VAT_STATUS_GENERALISED" not in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_an_explicitly_hedged_vat_statement_is_not_a_generalisation(
            self, solar_profile):
        """"Ces prix incluent la TVA lorsque cela est spécifié" says exactly the
        right thing: the treatment holds only where a source stated it."""
        verdict = run_seo_qa_v2(
            self._draft("Ces prix incluent la TVA lorsque cela est spécifié."),
            self._brief(["INCLUDED", "UNKNOWN", "UNKNOWN"]),
            {"facts": [], "sources": [{"title": "4.000 14.000"}]}, solar_profile)
        assert "VAT_STATUS_GENERALISED" not in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_a_per_figure_vat_statement_is_not_a_generalisation(self,
                                                                solar_profile):
        verdict = run_seo_qa_v2(
            self._draft("Le montant de 4.000 € est TVAC."),
            self._brief(["INCLUDED", "UNKNOWN"]),
            {"facts": [], "sources": [{"title": "4.000 14.000"}]}, solar_profile)
        assert "VAT_STATUS_GENERALISED" not in {
            f["code"] for f in verdict["blocking_issues"]}


# ─── 9: a page title is not a proposition ────────────────────────────────────

class TestPageTitleIsNotAClaim:
    @pytest.mark.parametrize("title", [
        "CREG : Commission de Régulation de l'Électricité et du Gaz",
        "Prix des panneaux solaires en Belgique 2025 | Guide complet",
        "Panneaux solaires photovoltaïques Wallonie Bruxelles Flandre",
    ])
    def test_9_a_page_title_alone_does_not_become_an_atomic_claim(self, title):
        claims = extract_claim_set([Passage(text=title, source_ref="web-001",
                                            offset=0)])
        assert claims.claims == [], f"title became a claim: {title!r}"

    def test_a_promotional_sentence_does_not_become_a_required_fact(self):
        """The route by which Phase 3.3's draft linked to a competitor.

        The brief told the writer to state "Pour en savoir plus, découvrez notre
        article sur les panneaux Plug and Play !" — so the outbound link was
        supplied, not invented.
        """
        promo = ("Pour en savoir plus, découvrez notre article sur les panneaux "
                 "Plug and Play !")
        claims = extract_claim_set([Passage(text=promo, source_ref="web-001",
                                            offset=0)])
        assert claims.claims == []

    def test_a_real_sentence_survives_the_title_filter(self):
        claims = extract_claim_set([Passage(text=LIVE_RANGE, source_ref="web-001",
                                            offset=0)])
        assert len(claims.claims) == 1


# ─── 10: every figure in the draft maps back to evidence ─────────────────────

class TestQuantifiedClaimsMapToEvidence:
    def test_10_a_quantified_draft_claim_must_map_to_a_retrieved_number(
            self, solar_profile):
        package = {"facts": [{"fact": LIVE_RANGE}], "sources": []}
        brief = {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
                 "key_questions": []}
        body = ("# Prix\n\n## Le budget\n\nComptez entre 4.000 € et 14.000 € TVAC "
                "pour une installation de 3 à 10 kWc.\n\n## Ce qui fait varier\n\n"
                + "La taille du système et le matériel choisi. " * 30)
        draft = {"title": "Prix", "body": body, "meta_title": "Prix",
                 "meta_description": "d"}

        supported = run_seo_qa_v2(draft, brief, package, solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" not in {
            f["code"] for f in supported["blocking_issues"]}

        # The same page with one figure nobody reported must block.
        invented = dict(draft, body=body.replace("14.000 €", "19.750 €"))
        verdict = run_seo_qa_v2(invented, brief, package, solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_a_v3_package_supplies_its_numbers_from_supported_claims(
            self, solar_profile):
        """The bug that made the first regenerated draft unpublishable.

        A V3 package keys its propositions `claim`; the numeric check read only
        `fact`, so every correctly sourced price read as "in no retrieved source".
        Phase 3.3's figure-free draft hid it completely.
        """
        package = {"supported_claims": [_claim(LIVE_RANGE, "OBSERVED_PRICE_RANGE")],
                   "facts": [], "sources": []}
        brief = {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
                 "key_questions": []}
        body = ("# Prix\n\n## Le budget\n\nComptez entre 4.000 € et 14.000 € "
                "TVAC pour une installation de 3 à 10 kWc.\n\n## Variables\n\n"
                + "La taille du système et le matériel choisi. " * 30)
        verdict = run_seo_qa_v2({"title": "Prix", "body": body,
                                 "meta_title": "Prix", "meta_description": "d"},
                                brief, package, solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" not in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_an_unsupported_claims_numbers_do_not_count_as_evidence(
            self, solar_profile):
        """Narrower than the V2 rule: only SUPPORTED claims license a figure."""
        package = {"supported_claims": [],
                   "claims": [_claim(LIVE_RANGE, "OBSERVED_PRICE_RANGE")],
                   "facts": [], "sources": []}
        brief = {"primary_query": SOLAR_QUERY, "search_intent": "COMMERCIAL",
                 "key_questions": []}
        body = ("# Prix\n\n## Le budget\n\nComptez entre 4.000 € et 14.000 € "
                "TVAC.\n\n## Variables\n\n" + "La taille du système. " * 40)
        verdict = run_seo_qa_v2({"title": "Prix", "body": body,
                                 "meta_title": "Prix", "meta_description": "d"},
                                brief, package, solar_profile)
        assert "UNSUPPORTED_NUMERIC_CLAIM" in {
            f["code"] for f in verdict["blocking_issues"]}

    def test_a_paraphrase_carrying_the_same_figures_traces_to_its_claim(self):
        """Phase 3.4: the draft was blocked for asserting what the source said.

        "Le panneau seul coûte entre 130 € et 170 €/m²" against the ledger claim
        "Le panneau seul revient à 130 € – 170 €/m²" shares one long content word
        and every figure. Blocking that would teach the writer to avoid quoting
        evidence accurately.
        """
        from app.services.factual_qa_v2 import _matches_claim

        ledger = {"claim": "Le panneau seul revient à 130 € – 170 €/m²."}
        assert _matches_claim(
            "**Le panneau seul coûte entre 130 € et 170 €/m²**.", ledger)
        # A different figure on the same subject must still fail.
        assert not _matches_claim(
            "**Le panneau seul coûte entre 130 € et 450 €/m²**.", ledger)
