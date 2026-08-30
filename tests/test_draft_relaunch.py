"""Re-emitting the draft, twice at most.

Everything expensive in a run is bought before the writer speaks. When the gate
refuses the prose, throwing the run away pays for the research a second time to
fix a writing fault — and judges the replacement against a different evidence
set, so the two verdicts cannot even be compared. So the writer's call alone is
re-emitted, carrying what refused it, against the same sealed brief and package.

Two extra attempts and no more. A policy that keeps going is not a retry policy,
it is sampling until the gate looks away.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.models import ContentDraft, QAReview
from app.providers.llm.base import LLMResponse, LLMUsage
from app.services import draft_retry, draft_service
from tests.test_pipeline_v2 import (QUERY, StubCommunityProvider, StubLLM,
                                    StubSearchProvider, StubWebProvider, _run)
from tests.test_qa import BODY



THIN = "# Prix des panneaux solaires en Belgique\n\nCe sujet est vaste.\n"


class SequenceLLM(StubLLM):
    """Returns a different body per draft call, so a retry is observable."""

    def __init__(self, bodies: list[str]):
        super().__init__()
        self._bodies = list(bodies)
        self.draft_calls = 0
        self.carried: list[list[dict]] = []

    async def generate(self, request):
        if request.capability.value in ("CONTENT_BRIEF", "SEO_QA",
                                        "CLASSIFICATION"):
            return await super().generate(request)
        payload = json.loads(request.prompt)
        self.carried.append(payload.get("refused_last_time") or [])
        self._body = self._bodies[min(self.draft_calls, len(self._bodies) - 1)]
        self.draft_calls += 1
        return await super().generate(request)


# ─── The policy itself ───────────────────────────────────────────────────────

class TestPolicy:
    def test_a_clean_draft_is_not_re_emitted(self):
        assert draft_retry.decide([], attempt=1).retry is False

    def test_a_writing_fault_earns_another_attempt(self):
        decision = draft_retry.decide(
            [{"code": "HIGH_RISK_CLAIM_ASSERTED"}], attempt=1)
        assert decision.retry is True
        assert decision.attempts_left == 2

    def test_the_third_attempt_is_the_last(self):
        blocking = [{"code": "REGIONAL_SCOPE_NOT_STATED"}]
        assert draft_retry.decide(blocking, attempt=2).retry is True
        third = draft_retry.decide(blocking, attempt=3)
        assert third.retry is False
        assert "sampling" in third.reason

    @pytest.mark.parametrize("code", sorted(draft_retry.NOT_RETRIABLE))
    def test_what_no_rewrite_can_answer_is_never_re_emitted(self, code):
        decision = draft_retry.decide([{"code": code}], attempt=1)
        assert decision.retry is False
        assert decision.blocked_by == (code,)

    def test_one_unanswerable_finding_stops_the_whole_retry(self):
        """A retriable finding beside it does not buy an attempt.

        The run would spend a call on a draft that cannot pass whatever it
        writes, because what refuses it is the evidence set, not the prose.
        """
        decision = draft_retry.decide(
            [{"code": "HIGH_RISK_CLAIM_ASSERTED"},
             {"code": "INSUFFICIENT_SUPPORTED_EVIDENCE"}], attempt=1)
        assert decision.retry is False
        assert decision.blocked_by == ("INSUFFICIENT_SUPPORTED_EVIDENCE",)

    def test_an_ambiguous_match_is_not_a_drafting_fault(self):
        """It says so in its own message. Re-rolling on it is the failure mode.

        The writer would be asked to change a sentence that may well be right,
        blind, until the matcher happens to like one.
        """
        assert draft_retry.decide([{"code": "AMBIGUOUS_MATCH"}],
                                  attempt=1).retry is False


# ─── What the second attempt is told ─────────────────────────────────────────

class TestCarriedFindings:
    BRIEF = {"primary_query": "prix panneaux solaires", "content_type": "ARTICLE",
             "search_intent": "COMMERCIAL", "target_audience": "propriétaires",
             "objective": "informer", "recommended_title": "Prix",
             "outline": [], "key_questions": [], "required_facts": [],
             "required_sources": [], "missing_information": [],
             "cta_strategy": {}, "cautionary_claims": []}

    def test_a_first_attempt_carries_nothing(self):
        system, user = draft_service.build_generation_prompt(
            self.BRIEF, {"language": "fr", "market": "BE"})
        assert "PREVIOUS ATTEMPT" not in system
        assert json.loads(user)["refused_last_time"] == []

    def test_a_re_emission_carries_the_gate_s_own_words(self):
        carried = draft_retry.carried([
            {"code": "HIGH_RISK_CLAIM_ASSERTED",
             "message": "the draft asserts a HIGH-risk SUBSIDY claim",
             "detail": "La prime atteint 1500 euros."}])
        system, user = draft_service.build_generation_prompt(
            self.BRIEF, {"language": "fr", "market": "BE"},
            previous_findings=carried)
        payload = json.loads(user)["refused_last_time"]
        assert payload[0]["code"] == "HIGH_RISK_CLAIM_ASSERTED"
        assert "1500" in payload[0]["in_your_text"]
        assert "PREVIOUS ATTEMPT" in system

    def test_it_is_told_the_evidence_has_not_changed(self):
        """Otherwise the obvious way to satisfy the gate is to invent a source."""
        system, _ = draft_service.build_generation_prompt(
            self.BRIEF, {"language": "fr", "market": "BE"},
            previous_findings=[{"code": "X", "problem": "y", "in_your_text": ""}])
        assert "evidence is unchanged" in system.replace("\n", " ")


# ─── End to end ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRelaunchInThePipeline:
    async def test_a_refused_draft_is_re_emitted_and_the_second_one_is_kept(
            self, seeded_session, settings_all_providers):
        llm = SequenceLLM([THIN, BODY])
        result = await _run(seeded_session, settings_all_providers, llm=llm)

        assert llm.draft_calls == 2
        assert len(result.draft_attempts) == 2
        assert result.draft_attempts[0]["retry"] is True
        assert result.draft_attempts[1]["retry"] is False
        assert llm.carried[0] == [], "the first attempt carries nothing"
        assert llm.carried[1], "the second is told what refused the first"

    async def test_only_the_kept_draft_is_persisted(self, seeded_session,
                                                    settings_all_providers):
        """A discarded attempt is not content. It never reaches the table."""
        await _run(seeded_session, settings_all_providers, llm=SequenceLLM([THIN, BODY]))
        drafts = (await seeded_session.execute(
            select(func.count()).select_from(ContentDraft))).scalar_one()
        assert drafts == 1

    async def test_the_discarded_attempts_are_still_auditable(
            self, seeded_session, settings_all_providers):
        """Otherwise a re-emitted run looks exactly like a first-time pass."""
        await _run(seeded_session, settings_all_providers, llm=SequenceLLM([THIN, BODY]))
        reviews = (await seeded_session.execute(select(QAReview))).scalars().all()
        history = [f for r in reviews for f in (r.findings or [])
                   if f.get("code") == "DRAFT_ATTEMPTS"]
        assert len(history) == 1
        assert len(history[0]["attempts"]) == 2

    async def test_the_research_is_not_bought_again(self, seeded_session,
                                                    settings_all_providers):
        """The whole reason the retry is bounded to the writer's call."""
        search, web = StubSearchProvider(), StubWebProvider()
        await _run(seeded_session, settings_all_providers, llm=SequenceLLM([THIN, BODY]),
                   search_provider=search, web_provider=web)
        assert search.serp_calls == 1
        assert web.calls == 1

    async def test_a_draft_that_never_passes_costs_three_calls_and_stops(
            self, seeded_session, settings_all_providers):
        llm = SequenceLLM([THIN])
        result = await _run(seeded_session, settings_all_providers, llm=llm)
        assert llm.draft_calls == draft_retry.MAX_ATTEMPTS == 3
        assert result.draft_attempts[-1]["retry"] is False
        assert "sampling" in result.draft_attempts[-1]["reason"]
        assert result.error_code == "QA_FAILED"
