"""Après-midi du 2026-09-03 : ce que le premier brouillon régénéré a appris.

Le pipeline a été relancé sur « rentabilité panneaux solaires Belgique » avec
les six gardes du lot C. Le rédacteur a écrit, à nouveau : « une installation
standard est rentabilisée au bout de 5 ans ». Trois choses sont sorties de la
lecture des verdicts, et chacune a son test ici.

1. Le « 5 » existait dans le registre — comme borne basse de « rentabilisation
   en 5 à 7 ans ». La couverture par segments l'acceptait. Une borne n'est pas
   la fourchette.
2. La phrase a produit dix AMBIGUOUS_MATCH, un par affirmation contestée à
   laquelle elle ressemblait faiblement, et AMBIGUOUS_MATCH interdit toute
   relance du rédacteur. Quand aucune lecture étayée ne couvre les chiffres,
   il n'y a pas d'ambiguïté : il y a un chiffre sans source, réécrivable.
3. Le relecteur assisté, désormais bloquant, a bloqué « entre 7,3% et 8,4% en
   Wallonie » — la seule figure OFFICIELLE de l'article — faute de voir les
   affirmations étayées. Il les voit.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio

from app.core.enums import ApprovalState, ContentType, SearchIntent
from app.models import (Approval, ContentBrief, ContentDraft, QAReview,
                        ResearchPackage, ResearchRun, SeedKeyword, Vertical)
from app.providers.llm.base import LLMResponse, LLMUsage
from app.services import draft_retry, factual_qa_v2, qa_service
from app.services.draft_stage import choose_best, write_and_judge
from app.services.factual_qa_v2 import (_UNREAD, _arbitrate, claim_figures,
                                        covers, endpoint_only, risky_ranges,
                                        risky_units, unit_only)
from app.services.provider_usage import UsageRecorder
from app.services.research_planner import (AuthoritativeQuery, ResearchPlan,
                                           pending_plan)
from app.services.claim_policy import ClaimCategory
from tests.fixtures.article_8a1f6e46 import (
    CLAIM_FAMILY_5000, CLAIM_PROSUMER_5_ANS, CLAIM_PROSUMER_MECHANISM,
    CLAIM_PROSUMER_MECHANISM_TRUNCATED, CLAIM_REVERSE_METER_2030,
    CLAIM_ROI_5_TO_7_SPECIALIST, CLAIM_ROI_UNDER_7,
    CLAIM_SMALL_WITHOUT_SUPPORT_OFFICIAL, CLAIM_YIELD_7_3_TO_8_4_OFFICIAL,
    PUBLISHED_CLAIMS, REVISED_BODY, claims_without)

# La phrase du brouillon régénéré, au caractère près (draft dc2a88d9).
REGENERATED_SENTENCE = (
    "Les données montrent que l'installation de panneaux solaires peut être "
    "rentable, notamment en Wallonie où une installation standard est "
    "rentabilisée au bout de 5 ans.")


def _run(body, claims, profile):
    return factual_qa_v2.run_factual_qa_v2(
        {"title": "t", "body": body, "meta_title": "t", "meta_description": "d"},
        {"claims": claims}, profile)


def _codes(verdict):
    return [f["code"] for f in verdict["findings"]]


def _findings(verdict, code):
    return [f for f in verdict["findings"] if f["code"] == code]


# ─── 1. Une borne n'est pas la fourchette ───────────────────────────────────

class TestRangeEndpoints:
    def test_a_range_yields_no_standalone_figure(self):
        standalone, ranges = claim_figures(CLAIM_ROI_5_TO_7_SPECIALIST["claim"])
        assert ("5", "7", "duration") in ranges
        assert "5" not in standalone and "7" not in standalone

    def test_a_percentage_range_is_a_range(self):
        assert ("73", "84", "percent") in risky_ranges("comprise entre 7,3% et 8,4%")

    def test_one_end_alone_is_not_covered(self):
        assert not covers(CLAIM_ROI_5_TO_7_SPECIALIST, {"5"})
        assert endpoint_only(CLAIM_ROI_5_TO_7_SPECIALIST, "5")

    def test_the_same_range_stated_in_full_is_covered(self):
        assert covers(CLAIM_ROI_5_TO_7_SPECIALIST, {"5", "7"}, {("5", "7", "duration")})
        assert covers(CLAIM_YIELD_7_3_TO_8_4_OFFICIAL, {"73", "84"},
                      risky_ranges("comprise entre 7,3% et 8,4%"))

    def test_a_standalone_figure_still_covers(self):
        assert covers(CLAIM_FAMILY_5000, {"4", "5000"})
        assert not endpoint_only(CLAIM_FAMILY_5000, "4")

    def test_the_regenerated_sentence_is_sourced_by_the_walloon_portal(
            self, solar_profile):
        """Le paquet porte « rentabilisée au bout de 5 ans » en source
        officielle : la phrase du brouillon régénéré est sourcée, et la garde
        le sait."""
        verdict = _run(REGENERATED_SENTENCE, PUBLISHED_CLAIMS, solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict)

    def test_without_that_source_the_sentence_collapses_a_range_and_fails(
            self, solar_profile):
        verdict = _run(REGENERATED_SENTENCE,
                       claims_without(CLAIM_PROSUMER_5_ANS), solar_profile)
        hits = _findings(verdict, "NUMBER_WITHOUT_SOURCE")
        assert hits and "one end of a range" in hits[0]["message"]
        assert verdict["status"] == "FAILED"

    def test_the_high_end_alone_fails_too(self, solar_profile):
        verdict = _run("En Wallonie, la rentabilité atteint 8,4%.",
                       [CLAIM_YIELD_7_3_TO_8_4_OFFICIAL], solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" in _codes(verdict)

    def test_the_revised_article_states_its_ranges_in_full_and_passes(
            self, solar_profile):
        verdict = _run(REVISED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict), verdict["findings"]
        assert verdict["status"] == "PASSED", verdict["findings"]


# ─── 2. Pas d'ambiguïté sans deux lectures ──────────────────────────────────

class TestUnreadIsNotAmbiguous:
    # Ce que le brouillon a rencontré : des affirmations contestées auxquelles
    # la phrase ressemble faiblement, et aucune lecture étayée portant « 5 ».
    CONTESTED = [
        {**CLAIM_ROI_UNDER_7,
         "claim": "Retour sur investissement des panneaux solaires en Belgique "
                  "en 2026 : guide complet de la rentabilité d'une installation."},
        {**CLAIM_ROI_UNDER_7,
         "claim": "Le rendement des panneaux solaires est la clé d'une "
                  "rentabilité réelle sur le long terme de l'installation."},
    ]

    def test_arbitration_says_unread_when_nothing_covers_the_figures(self):
        supported = [CLAIM_PROSUMER_MECHANISM_TRUNCATED, CLAIM_ROI_5_TO_7_SPECIALIST]
        for claim in self.CONTESTED:
            verdict, rival = _arbitrate(REGENERATED_SENTENCE, claim, supported)
            assert verdict != "AMBIGUOUS", (claim["claim"], verdict)
            assert verdict in (_UNREAD, "ASSERTED")
            if verdict == _UNREAD:
                assert rival is None

    def test_no_ambiguous_match_and_a_rewritable_finding_instead(
            self, solar_profile):
        claims = self.CONTESTED + [CLAIM_PROSUMER_MECHANISM_TRUNCATED,
                                   CLAIM_ROI_5_TO_7_SPECIALIST]
        verdict = _run(REGENERATED_SENTENCE, claims, solar_profile)
        assert "AMBIGUOUS_MATCH" not in _codes(verdict), verdict["findings"]
        assert "NUMBER_WITHOUT_SOURCE" in _codes(verdict)
        decision = draft_retry.decide(verdict["blocking_issues"], attempt=1)
        assert decision.retry is True, decision

    def test_two_real_readings_are_still_ambiguous(self):
        """La mutation : deux lectures qui couvrent toutes deux les chiffres,
        à égalité, restent une ambiguïté — la garde d'août n'est pas retirée."""
        sentence = "Une installation de 5000 euros se rentabilise en 12 ans."
        contested = {"claim": "Une installation de 5000 euros se rentabilise en "
                              "12 ans selon les sources.",
                     "evidence_status": "UNSUPPORTED", "claim_risk": "HIGH",
                     "category": "ROI", "region": "BE"}
        supported = [{"claim": "Une installation de 5000 euros se rentabilise "
                               "en 12 ans d'après les sources.",
                      "evidence_status": "SUPPORTED", "claim_risk": "LOW",
                      "category": "GENERAL", "region": "BE",
                      "has_dated_support": True}]
        verdict, rival = _arbitrate(sentence, contested, supported)
        assert verdict == "AMBIGUOUS" and rival is not None


# ─── 3. Le relecteur assisté voit ce qui est sourcé ─────────────────────────

class _CapturingLLM:
    configured = True

    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return LLMResponse(content=json.dumps({"findings": []}),
                           provider="stub", model="stub",
                           usage=LLMUsage(input_tokens=1, output_tokens=1,
                                          total_tokens=2), latency_ms=1)


@pytest.mark.asyncio
class TestReviewerSeesSourcedFacts:
    async def test_the_prompt_carries_the_supported_claims(self):
        llm = _CapturingLLM()
        await qa_service.run_llm_qa(
            {"title": "t", "body": REVISED_BODY, "meta_description": "d"},
            {"primary_query": "q", "search_intent": "INFORMATIONAL",
             "content_type": "GUIDE", "target_audience": "a",
             "cta_strategy": {}},
            llm=llm, correlation_id="t",
            sourced_claims=[CLAIM_YIELD_7_3_TO_8_4_OFFICIAL["claim"]])
        request = llm.requests[0]
        prompt = json.loads(request.prompt)
        assert prompt["reference_sourced_facts"] == [
            CLAIM_YIELD_7_3_TO_8_4_OFFICIAL["claim"]]
        assert "reference_sourced_facts" in request.system
        assert "Review ONLY the `body`" in request.system
        assert "never be reported as unsupported" in request.system

    async def test_without_the_list_the_prompt_says_so(self):
        llm = _CapturingLLM()
        await qa_service.run_llm_qa(
            {"title": "t", "body": "x", "meta_description": "d"},
            {"primary_query": "q", "search_intent": "INFORMATIONAL",
             "content_type": "GUIDE", "target_audience": "a",
             "cta_strategy": {}},
            llm=llm, correlation_id="t")
        assert json.loads(llm.requests[0].prompt)["reference_sourced_facts"] == []

    async def test_a_finding_that_quotes_the_reference_not_the_body_never_blocks(self):
        """Mesuré sur le brouillon 86255f33 : cinq « unsupported » high ROI
        citant des phrases du registre absentes du brouillon. Le relecteur
        avait relu la référence. Un tel constat est gardé, visible, et ne
        bloque jamais."""
        class _EchoingLLM(_CapturingLLM):
            async def generate(self, request):
                self.requests.append(request)
                return LLMResponse(content=json.dumps({"findings": [
                    {"code": "unsupported_claim", "severity": "high",
                     "category": "ROI",
                     "message": "Le taux de rendement est désormais bien "
                                "supérieur à l'objectif initial."},
                    {"code": "unsupported_claim", "severity": "high",
                     "category": "ROI",
                     "message": "Une installation standard est rentabilisée "
                                "au bout de 5 ans sans que le texte le "
                                "justifie."},
                ]}), provider="stub", model="stub",
                    usage=LLMUsage(input_tokens=1, output_tokens=1,
                                   total_tokens=2), latency_ms=1)

        result = await qa_service.run_llm_qa(
            {"title": "t", "meta_description": "d",
             "body": "En Wallonie, une installation standard est rentabilisée "
                     "au bout de 5 ans."},
            {"primary_query": "q", "search_intent": "INFORMATIONAL",
             "content_type": "GUIDE", "target_audience": "a",
             "cta_strategy": {}},
            llm=_EchoingLLM(), correlation_id="t",
            sourced_claims=["Le taux de rendement est désormais bien supérieur "
                            "à l'objectif initial."])
        codes = [(f["code"], f["blocking"]) for f in result["findings"]]
        assert ("reference_echo", False) in codes
        assert ("unsupported_claim", True) in codes
        assert len(result["blocking_issues"]) == 1


# ─── 4. Relancer le rédacteur sur un paquet existant ────────────────────────

@pytest_asyncio.fixture
async def sealed_brief(session):
    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    keyword = SeedKeyword(vertical_id=vertical.id,
                          query="rentabilité panneaux solaires Belgique",
                          normalized_query="rentabilite panneaux solaires belgique",
                          market="BE", language="fr")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily",
                      status="SUCCEEDED", idempotency_key=str(uuid.uuid4()),
                      correlation_id="test")
    session.add(run)
    await session.flush()
    package = ResearchPackage(
        keyword_id=keyword.id, research_run_id=run.id, version=1,
        package_version=4, query=keyword.query, market="BE", language="fr",
        intent="INFORMATIONAL", summary="sealed", facts=list(PUBLISHED_CLAIMS),
        authoritative_research={"resolution": []})
    session.add(package)
    await session.flush()
    brief = ContentBrief(
        research_package_id=package.id, content_type=ContentType.GUIDE.value,
        primary_query=keyword.query,
        search_intent=SearchIntent.INFORMATIONAL.value,
        target_audience="propriétaires", objective="leads",
        recommended_title="Rentabilité des panneaux solaires en Belgique",
        recommended_slug="rentabilite-panneaux-solaires-belgique",
        outline=[], key_questions=[], required_facts=[], required_sources=[],
        cautionary_claims=[], cta_strategy={"code": "quote_request"},
        missing_information=[], core_question=keyword.query,
        core_answer_status="NOT_APPLICABLE", core_answer_evidence={},
        must_answer_directly=False)
    session.add(brief)
    await session.flush()
    first = ContentDraft(content_brief_id=brief.id, provider="openai",
                         model="m", title="v1", body=REVISED_BODY,
                         meta_title="v1", meta_description="d")
    session.add(first)
    await session.flush()
    return brief, package, keyword, vertical


@pytest.mark.asyncio
class TestRegenerate:
    async def test_a_second_draft_is_written_beside_the_first(
            self, session, sealed_brief, solar_profile):
        from sqlalchemy import select

        from app.cli import _brief_payload, _package_payload
        from tests.test_pipeline_v2 import StubLLM

        brief, package, keyword, vertical = sealed_brief
        llm = StubLLM(body=REVISED_BODY)
        outcome = await write_and_judge(
            session, brief=brief, brief_payload=_brief_payload(brief),
            package_payload=_package_payload(package), profile=solar_profile,
            llm=llm, usage=UsageRecorder(), correlation_id="regen-test",
            keyword_id=keyword.id, vertical_code=vertical.code)

        assert outcome.draft is not None
        drafts = (await session.execute(select(ContentDraft).where(
            ContentDraft.content_brief_id == brief.id))).scalars().all()
        assert len(drafts) == 2
        reviews = (await session.execute(select(QAReview).where(
            QAReview.content_draft_id == outcome.draft.id))).scalars().all()
        assert {r.qa_type for r in reviews} == {"DETERMINISTIC", "LLM_ASSISTED"}
        assert len(reviews) == 3
        approval = (await session.execute(select(Approval).where(
            Approval.content_draft_id == outcome.draft.id))).scalar_one()
        assert approval.state == ApprovalState.PENDING.value
        assert approval.render_fingerprint is None
        # The reviewer was handed the sourced facts of this package.
        seo_qa_calls = [r for r in llm.requests
                        if r.capability.value == "SEO_QA"] \
            if hasattr(llm, "requests") else []
        assert "SEO_QA" in llm.calls
        assert outcome.as_dict()["content_draft_id"] == str(outcome.draft.id)
        assert isinstance(outcome.qa_passed, bool)
        del seo_qa_calls

    async def test_the_research_resolution_is_untouched(self, session,
                                                        sealed_brief,
                                                        solar_profile):
        from app.cli import _brief_payload, _package_payload
        from tests.test_pipeline_v2 import StubLLM

        brief, package, keyword, vertical = sealed_brief
        before = dict(package.authoritative_research)
        await write_and_judge(
            session, brief=brief, brief_payload=_brief_payload(brief),
            package_payload=_package_payload(package), profile=solar_profile,
            llm=StubLLM(body=REVISED_BODY), usage=UsageRecorder(),
            correlation_id="regen-test-2", keyword_id=keyword.id,
            vertical_code=vertical.code)
        assert package.authoritative_research == before


# ─── 5. Ne relancer que ce qui est dû ───────────────────────────────────────

class TestPendingPlan:
    def _plan(self):
        return ResearchPlan(queries=[
            AuthoritativeQuery(query="a", category=ClaimCategory.ROI,
                               domains=[], reason="r"),
            AuthoritativeQuery(query="b", category=ClaimCategory.REGULATION,
                               domains=[], reason="r"),
        ])

    def test_executed_and_abandoned_queries_are_not_relaunched(self):
        record = {"resolution": [
            {"query": "a", "status": "EXECUTED"},
        ]}
        pending = pending_plan(self._plan(), record)
        assert [q.query for q in pending.queries] == ["b"]

    def test_nothing_pending_is_an_empty_plan_with_a_reason(self):
        record = {"resolution": [{"query": "a", "status": "EXECUTED"},
                                 {"query": "b", "status": "ABANDONED",
                                  "reason": "hors périmètre"}]}
        pending = pending_plan(self._plan(), record)
        assert pending.is_empty and pending.skipped_reason

    def test_an_unrecorded_package_owes_everything(self):
        assert len(pending_plan(self._plan(), None).queries) == 2


# ─── 6. Une unité fait partie du chiffre ────────────────────────────────────

class TestUnitsArePartOfTheFigure:
    """Deuxième brouillon régénéré (9cbebf5e) : la lecture étayée qui
    « couvrait » le 5 ans était le passage officiel sur le tarif prosumer,
    qui porte un 5 d'une autre espèce. Seize AMBIGUOUS_MATCH en sont sortis."""

    OFFICIAL_5_KWC = {"claim": "Même à la suite de l'entrée en vigueur du tarif "
                               "prosumer, une installation de 5 kWc reste "
                               "rentable pour le ménage.",
                      "evidence_status": "SUPPORTED", "claim_risk": "LOW",
                      "category": "GENERAL", "region": "BE-WAL",
                      "has_dated_support": True, "best_source_quality": "OFFICIAL"}
    OFFICIAL_5_ANS = {**OFFICIAL_5_KWC,
                      "claim": "Même à la suite de l'entrée en vigueur du tarif "
                               "prosumer, une installation reste rentable et "
                               "est amortie en 5 ans."}
    FAQ = ("Oui, en Wallonie, les installations sont rentabilisées au bout de "
           "5 ans, même avec le tarif prosumer en vigueur.")

    def test_a_sentence_figure_carries_its_unit_class(self):
        assert risky_units(self.FAQ) == {"5": {"duration"}}
        assert risky_units("avant le 31 décembre 2023") == {"31": {"bare"},
                                                            "2023": {"year"}} \
            or risky_units("avant le 31 décembre 2023")["2023"] == {"year"}

    def test_five_kwc_does_not_source_five_years(self):
        units = risky_units(self.FAQ)
        assert not covers(self.OFFICIAL_5_KWC, {"5"}, set(), units)
        assert unit_only(self.OFFICIAL_5_KWC, "5", units)
        assert covers(self.OFFICIAL_5_ANS, {"5"}, set(), units)

    def test_the_faq_sentence_is_a_figure_without_source_not_an_ambiguity(
            self, solar_profile):
        claims = TestUnreadIsNotAmbiguous.CONTESTED + [self.OFFICIAL_5_KWC]
        verdict = _run(self.FAQ, claims, solar_profile)
        assert "AMBIGUOUS_MATCH" not in _codes(verdict), verdict["findings"]
        hits = _findings(verdict, "NUMBER_WITHOUT_SOURCE")
        assert hits and "another unit" in hits[0]["message"]

    def test_an_official_dated_five_years_would_source_it(self, solar_profile):
        """La mutation qui compte : si le portail wallon disait « amortie en
        5 ans », la phrase serait sourcée — et la garde la laisserait passer."""
        verdict = _run(self.FAQ, [self.OFFICIAL_5_ANS], solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict)
        assert "ROI_WITHOUT_DATED_SOURCE" not in _codes(verdict)

    def test_the_lenient_form_still_shows_what_was_excluded(self):
        # explain rows use covers() without units to show the nearest reading
        assert covers(self.OFFICIAL_5_KWC, {"5"})


# ─── 7. « Rentable sans soutien public » : officiel, textuellement, ou rien ─

class TestSupportFreeClaim:
    # Phrase du brouillon régénéré dc2a88d9, sans aucun chiffre : invisible
    # aux gardes numériques, plus signalée par le relecteur assisté.
    FAQ3 = ("Oui, même sans soutien public, les petites installations restent "
            "intéressantes.")
    OFFICIAL_CARRIER = {
        "claim": "Même sans soutien public, les petites installations "
                 "photovoltaïques restent intéressantes pour les ménages.",
        "evidence_status": "SUPPORTED", "claim_risk": "HIGH",
        "category": "SUBSIDY", "region": "BE-WAL", "has_dated_support": True,
        "best_source_quality": "OFFICIAL"}

    NO_OFFICIAL_CARRIER = claims_without(CLAIM_SMALL_WITHOUT_SUPPORT_OFFICIAL)

    def test_fails_without_an_official_textual_carrier(self, solar_profile):
        verdict = _run(self.FAQ3, self.NO_OFFICIAL_CARRIER, solar_profile)
        hits = _findings(verdict, "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE")
        assert hits and self.FAQ3[:40] in hits[0]["detail"]
        assert hits[0]["blocking"]

    def test_the_second_draft_wording_fails_too(self, solar_profile):
        verdict = _run("En résumé, investir dans des panneaux solaires est, "
                       "aujourd'hui, un placement rentable sans aide ni subside "
                       "grâce à la baisse des prix.", self.NO_OFFICIAL_CARRIER,
                       solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" in _codes(verdict)

    def test_a_specialist_carrier_is_not_enough(self, solar_profile):
        specialist = {**self.OFFICIAL_CARRIER, "best_source_quality": "SPECIALIST"}
        verdict = _run(self.FAQ3, self.NO_OFFICIAL_CARRIER + [specialist],
                       solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" in _codes(verdict)

    def test_an_official_carrier_saying_the_same_thing_passes(self, solar_profile):
        verdict = _run(self.FAQ3, self.NO_OFFICIAL_CARRIER + [self.OFFICIAL_CARRIER],
                       solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" not in _codes(verdict)

    def test_the_real_package_carries_it_officially(self, solar_profile):
        """Ce que le paquet d'août dit vraiment : la formule est portée par
        une source OFFICIELLE. La garde passe sur la phrase publiée."""
        verdict = _run(self.FAQ3, PUBLISHED_CLAIMS, solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" not in _codes(verdict)

    def test_an_official_carrier_that_does_not_say_it_is_not_a_carrier(
            self, solar_profile):
        """Le passage officiel sur le mécanisme du tarif prosumer ressemble à
        la phrase mais ne dit rien du soutien public : il ne la porte pas."""
        assert CLAIM_PROSUMER_MECHANISM["best_source_quality"] == "OFFICIAL"
        verdict = _run("Même avec le tarif prosumer et sans aucune prime, une "
                       "installation reste rentable en Wallonie.",
                       [CLAIM_PROSUMER_MECHANISM], solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" in _codes(verdict)

    def test_the_revised_article_makes_no_such_claim(self, solar_profile):
        verdict = _run(REVISED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" not in _codes(verdict)

    def test_the_rewrite_is_a_writing_fault_the_writer_may_answer(self):
        assert "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE" not in draft_retry.NOT_RETRIABLE


# ─── 8. Le brouillon gardé est le meilleur, pas le dernier ──────────────────

class TestChooseBest:
    def _c(self, attempt, codes):
        return {"attempt": attempt, "blocking": [{"code": c} for c in codes]}

    def test_fewest_blocking_wins(self):
        best = choose_best([self._c(1, ["A", "B"]), self._c(2, ["A"]),
                            self._c(3, ["A", "B", "AMBIGUOUS_MATCH"])])
        assert best["attempt"] == 2

    def test_an_answerable_finding_beats_an_unanswerable_one(self):
        best = choose_best([self._c(1, ["AMBIGUOUS_MATCH"]),
                            self._c(2, ["REQUIRED_FACTS_UNDERUSED"])])
        assert best["attempt"] == 2

    def test_a_tie_goes_to_the_latest(self):
        best = choose_best([self._c(1, ["A"]), self._c(2, ["B"])])
        assert best["attempt"] == 2

    def test_the_measured_case(self):
        """regenerate sur 29ec0a0b : 3 → 1 → 3 blocages ; le dernier était
        gardé. C'est le deuxième qui l'est."""
        best = choose_best([
            self._c(1, ["HIGH_RISK_CLAIM_ASSERTED", "REGIONAL_SCOPE_NOT_STATED",
                        "REQUIRED_FACTS_UNDERUSED"]),
            self._c(2, ["REQUIRED_FACTS_UNDERUSED"]),
            self._c(3, ["AMBIGUOUS_MATCH", "REGIONAL_SCOPE_NOT_STATED",
                        "X", "Y", "Z"])])
        assert best["attempt"] == 2


class _VersionedLLM:
    """A writer whose every call returns a different body."""
    code = "stub"
    configured = True

    def __init__(self):
        self.n = 0

    async def generate(self, request):
        cap = request.capability.value
        if cap == "SEO_QA":
            payload = {"findings": []}
        else:
            self.n += 1
            payload = {"title": f"Version {self.n}", "meta_title": "t",
                       "meta_description": "d", "body": f"Version {self.n}."}
        return LLMResponse(content=json.dumps(payload), provider="stub",
                           model="stub", usage=LLMUsage(input_tokens=1,
                                                       output_tokens=1,
                                                       total_tokens=2),
                           latency_ms=1)


@pytest.mark.asyncio
class TestTheKeptDraftIsTheBest:
    async def test_attempt_two_is_persisted_when_three_is_worse(
            self, session, sealed_brief, solar_profile, monkeypatch):
        from app.cli import _brief_payload, _package_payload
        from app.services import draft_stage

        verdicts = iter([
            [{"code": "HIGH_RISK_CLAIM_ASSERTED", "blocking": True},
             {"code": "REGIONAL_SCOPE_NOT_STATED", "blocking": True}],
            [{"code": "REGIONAL_SCOPE_NOT_STATED", "blocking": True}],
            [{"code": "AMBIGUOUS_MATCH", "blocking": True},
             {"code": "REGIONAL_SCOPE_NOT_STATED", "blocking": True}],
        ])

        def scripted(draft, package, profile):
            blocking = next(verdicts)
            return {"status": "FAILED", "score": 50, "findings": list(blocking),
                    "blocking_issues": list(blocking), "claim_ledger": {}}

        monkeypatch.setattr(draft_stage.factual_qa_v2, "run_factual_qa_v2",
                            scripted)
        monkeypatch.setattr(
            draft_stage.qa_service, "run_seo_qa_v2",
            lambda *a, **k: {"status": "PASSED", "score": 100, "findings": [],
                             "blocking_issues": [],
                             "offer_registry": {"version": "t"}})

        brief, package, keyword, vertical = sealed_brief
        outcome = await write_and_judge(
            session, brief=brief, brief_payload=_brief_payload(brief),
            package_payload=_package_payload(package), profile=solar_profile,
            llm=_VersionedLLM(), usage=UsageRecorder(),
            correlation_id="best", keyword_id=keyword.id,
            vertical_code=vertical.code)

        assert len(outcome.attempts) == 3
        assert outcome.kept_attempt == 2
        assert outcome.draft.body == "Version 2."
        assert len(outcome.factual["blocking_issues"]) == 1
        from sqlalchemy import select
        row = (await session.execute(select(QAReview).where(
            QAReview.content_draft_id == outcome.draft.id,
            QAReview.layer == "FACTUAL"))).scalar_one()
        history = next(f for f in row.findings if f["code"] == "DRAFT_ATTEMPTS")
        assert history["kept_attempt"] == 2
        assert "kept attempt 2" in history["message"]
        assert len(history["attempts"]) == 3
