"""Which claim is a sentence actually stating?

The gate that produced draft 8a1f6e46 returned factual score 100 — every factual
sentence in the body matched a SUPPORTED claim — and, in the same verdict, five
blocking findings saying those sentences asserted UNSUPPORTED ones. Both readings
were true, because `_matches_claim` answers "could this be that claim" and the
blocking checks read it as "the draft states that claim".

These tests pin the arbitration that separates the two, and the two things it is
forbidden to become: a preference for the supported reading, and a silence.
"""
from __future__ import annotations

from app.core.enums import EvidenceStatus
from app.services import factual_qa_v2
from app.services.claim_policy import ClaimRisk


def _claim(text, *, status=EvidenceStatus.SUPPORTED, risk=ClaimRisk.MEDIUM,
           category="GENERAL", region="UNKNOWN", regionally_determined=False):
    return {
        "claim": text, "evidence_status": status.value,
        "claim_risk": risk if isinstance(risk, str) else risk.value,
        "category": category, "region": region,
        "regionally_determined": regionally_determined,
        "reason": "fixture",
    }


def _run(body, claims, profile):
    return factual_qa_v2.run_factual_qa_v2(
        {"title": "t", "body": body, "meta_title": "t",
         "meta_description": "d"},
        {"claims": claims}, profile)


def _codes(verdict):
    return [f["code"] for f in verdict["findings"]]


# ─── The observed defect ─────────────────────────────────────────────────────

class TestMisattributedBlame:
    def test_a_sentence_stating_a_supported_claim_is_not_blamed_for_a_neighbour(
            self, solar_profile):
        """The 8a1f6e46 shape: one sentence, two matches, one of them stronger.

        The body reproduces the supported claim almost word for word. It shares
        `installation` and a figure with the unsupported ledger entry, which was
        enough for the old check to declare the draft asserted it.
        """
        body = ("Le prix moyen d'une installation photovoltaïque de 5 kWc est "
                "d'environ 8000 euros hors TVA en Belgique.")
        claims = [
            _claim("Le prix moyen d'une installation photovoltaïque de 5 kWc "
                   "est d'environ 8000 euros hors TVA."),
            _claim("Une installation de 5 kWc permet une économie de 8000 euros "
                   "sur la durée de vie et un retour garanti par la Région.",
                   status=EvidenceStatus.UNSUPPORTED, risk=ClaimRisk.HIGH,
                   category="ROI"),
        ]
        verdict = _run(body, claims, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" not in _codes(verdict)
        assert "AMBIGUOUS_MATCH" not in _codes(verdict)
        assert verdict["status"] == "PASSED"

    def test_the_draft_that_really_asserts_the_unsupported_claim_still_blocks(
            self, solar_profile):
        """The same ledger, a body that states the unsupported claim instead."""
        body = ("Une installation de 5 kWc permet une économie de 8000 euros "
                "sur la durée de vie, avec un retour garanti par la Région.")
        claims = [
            _claim("Le prix moyen d'une installation photovoltaïque de 5 kWc "
                   "est d'environ 8000 euros hors TVA."),
            _claim("Une installation de 5 kWc permet une économie de 8000 euros "
                   "sur la durée de vie et un retour garanti par la Région.",
                   status=EvidenceStatus.UNSUPPORTED, risk=ClaimRisk.HIGH,
                   category="ROI"),
        ]
        verdict = _run(body, claims, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" in _codes(verdict)
        assert verdict["status"] == "FAILED"


# ─── Fail-closed, and named ──────────────────────────────────────────────────

class TestTiesBlock:
    def test_two_readings_of_equal_strength_block_as_ambiguous(self,
                                                               solar_profile):
        """Identical claim texts, opposite statuses: nothing can separate them.

        The point of the code is that the operator sees a matcher case. Blocking
        it as HIGH_RISK_CLAIM_ASSERTED would tell them to rewrite a sentence that
        is not wrong.
        """
        text = ("Le retour sur investissement d'une installation de 5 kWc est "
                "de 8 ans en moyenne.")
        claims = [
            _claim(text),
            _claim(text, status=EvidenceStatus.UNSUPPORTED,
                   risk=ClaimRisk.HIGH, category="ROI"),
        ]
        verdict = _run(text, claims, solar_profile)
        assert "AMBIGUOUS_MATCH" in _codes(verdict)
        assert "HIGH_RISK_CLAIM_ASSERTED" not in _codes(verdict)
        assert verdict["status"] == "FAILED", "a tie must not pass the gate"

    def test_the_ambiguous_finding_names_both_readings(self, solar_profile):
        text = ("Le retour sur investissement d'une installation de 5 kWc est "
                "de 8 ans en moyenne.")
        claims = [
            _claim(text),
            _claim(text, status=EvidenceStatus.UNSUPPORTED,
                   risk=ClaimRisk.HIGH, category="ROI"),
        ]
        finding = next(f for f in _run(text, claims, solar_profile)["findings"]
                       if f["code"] == "AMBIGUOUS_MATCH")
        assert finding["blocking"] is True
        assert "contested:" in finding["detail"]
        assert "supported:" in finding["detail"]
        assert "HIGH_RISK_CLAIM_ASSERTED" in finding["message"]

    def test_a_later_assertion_outranks_an_earlier_tie(self, solar_profile):
        """One claim, two sentences: the draft is judged on the stronger.

        The first sentence states the part the two ledger entries share, and
        nothing can separate them on it. The second reproduces the unsupported
        entry whole. Reporting the tie would send the operator to read a matcher
        when what is in front of them is an assertion.
        """
        supported = ("La prime régionale atteint 1500 euros pour une "
                     "installation résidentielle.")
        unsupported = ("La prime régionale atteint 1500 euros pour une "
                       "installation photovoltaïque.")
        claims = [
            _claim(supported),
            _claim(unsupported, status=EvidenceStatus.UNSUPPORTED,
                   risk=ClaimRisk.HIGH, category="SUBSIDY"),
        ]
        tie = "La prime régionale atteint 1500 euros."
        assert _codes(_run(tie, claims, solar_profile)) == ["AMBIGUOUS_MATCH"], \
            "the first sentence on its own is genuinely undecidable"

        codes = _codes(_run(tie + " " + unsupported, claims, solar_profile))
        assert "HIGH_RISK_CLAIM_ASSERTED" in codes
        assert "AMBIGUOUS_MATCH" not in codes

    def test_an_unsupported_claim_with_no_supported_rival_blocks_outright(
            self, solar_profile):
        """No rival means no ambiguity. This is the case the gate exists for."""
        body = ("La prime régionale pour une installation de 5 kWc atteint "
                "1500 euros par installation.")
        claims = [_claim(body, status=EvidenceStatus.UNSUPPORTED,
                         risk=ClaimRisk.HIGH, category="SUBSIDY")]
        verdict = _run(body, claims, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" in _codes(verdict)
        assert "AMBIGUOUS_MATCH" not in _codes(verdict)


# ─── The forbidden shape ─────────────────────────────────────────────────────

class TestNeverPrefersTheSupportedReading:
    def test_a_supported_claim_that_matches_less_well_does_not_clear_the_draft(
            self, solar_profile):
        """A weak supported match must not launder a strong unsupported one.

        The supported claim shares one topic word and no figure; the unsupported
        one is reproduced entire. Arbitration is a comparison, and here the
        comparison has an answer.
        """
        body = ("La prime régionale pour une installation de 5 kWc atteint "
                "1500 euros par installation.")
        claims = [
            _claim("Une installation photovoltaïque produit environ 950 kWh "
                   "par kWc et par an."),
            _claim(body, status=EvidenceStatus.UNSUPPORTED,
                   risk=ClaimRisk.HIGH, category="SUBSIDY"),
        ]
        verdict = _run(body, claims, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" in _codes(verdict)


# ─── The regional check arbitrates too ───────────────────────────────────────

class TestRegionalScopeArbitration:
    """The scope check reads the matcher too, so it inherits the same defect.

    Two supported payback claims sit in this ledger: one that names no region
    and one Walloon. They share their whole vocabulary, which is what makes the
    misattribution possible — and what makes the arbitration testable.
    """

    def _ledger(self):
        return [
            _claim("Le retour sur investissement d'une installation "
                   "photovoltaïque se situe entre 10 et 12 ans selon la "
                   "consommation du ménage."),
            _claim("En Wallonie, le retour sur investissement d'une "
                   "installation atteint 10 ans.",
                   category="ROI", region="BE-WAL", regionally_determined=True),
        ]

    def test_a_flat_walloon_figure_still_blocks(self, solar_profile):
        """The Walloon claim, restated without its region. False by omission."""
        body = ("Le retour sur investissement d'une installation atteint "
                "10 ans.")
        assert "REGIONAL_SCOPE_NOT_STATED" in _codes(
            _run(body, self._ledger(), solar_profile))

    def test_the_unscoped_claim_restated_is_not_blamed_for_the_walloon_one(
            self, solar_profile):
        """Same words, same figure, different claim — and it needs no region."""
        body = ("Le retour sur investissement d'une installation "
                "photovoltaïque se situe entre 10 et 12 ans selon la "
                "consommation du ménage.")
        codes = _codes(_run(body, self._ledger(), solar_profile))
        assert "REGIONAL_SCOPE_NOT_STATED" not in codes
        assert "AMBIGUOUS_MATCH" not in codes

    def test_naming_the_region_clears_it_as_before(self, solar_profile):
        body = ("En Wallonie, le retour sur investissement d'une installation "
                "atteint 10 ans.")
        assert "REGIONAL_SCOPE_NOT_STATED" not in _codes(
            _run(body, self._ledger(), solar_profile))


# ─── Strength is a comparison, not a threshold ───────────────────────────────

class TestMatchStrength:
    def test_a_non_match_scores_zero(self, solar_profile):
        assert factual_qa_v2._match_strength(
            "Le prix est de 8000 euros.",
            _claim("Le tarif prosumer wallon est appliqué depuis 2020.")) == 0.0

    def test_a_near_miss_scores_zero_too_and_cannot_outvote_anything(self):
        """Strength is only ever asked of a claim the sentence already matches.

        These two share every word and contradict each other on the only figure
        that matters, so `_matches_claim` refuses them. If strength answered
        anyway it would answer 0.6 — enough to become the strongest "supported
        reading" of a sentence it has nothing to do with, and to clear a genuine
        assertion off the gate.
        """
        sentence = "Le prix moyen d'une installation photovoltaïque atteint 8000 euros."
        claim = _claim("Le prix moyen d'une installation photovoltaïque "
                       "atteint 12000 euros.")
        assert factual_qa_v2._matches_claim(sentence, claim) is False
        assert factual_qa_v2._match_strength(sentence, claim) == 0.0

    def test_figures_separate_two_claims_that_share_every_word(self,
                                                              solar_profile):
        """Vocabulary alone cannot decide here, and the draft is not ambiguous.

        The two ledger entries differ only in their last figure — the shape a
        page and its outdated copy actually take. The sentence reproduces one of
        them exactly. Judged on words alone the two readings tie, and a correct
        draft is blocked as AMBIGUOUS_MATCH; judged on figures too, the answer
        is plain.
        """
        body = "Une installation de 5000 euros se rentabilise en 12 ans."
        claims = [
            _claim(body),
            _claim("Une installation de 5000 euros se rentabilise en 18 ans.",
                   status=EvidenceStatus.UNSUPPORTED, risk=ClaimRisk.HIGH,
                   category="ROI"),
        ]
        verdict = _run(body, claims, solar_profile)
        assert _codes(verdict) == []
        assert verdict["status"] == "PASSED"

    def test_reproducing_a_claim_beats_sharing_two_words_with_it(self):
        sentence = "Le prix moyen d'une installation de 5 kWc est de 8000 euros."
        near = _claim("Le prix moyen d'une installation de 5 kWc est de "
                      "8000 euros hors TVA.")
        far = _claim("Une installation photovoltaïque de 5 kWc produit de "
                     "l'électricité pendant 25 ans.")
        assert (factual_qa_v2._match_strength(sentence, near)
                > factual_qa_v2._match_strength(sentence, far))
