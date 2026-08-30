"""End-to-end pipeline, with a stub research provider and a stub LLM.

These are the integration tests: real models, real SQLite persistence, real
services, no network. They assert the two behaviours the mission cares about most
— that the pipeline stops cleanly when it cannot proceed, and that nothing reaches
APPROVED without a person.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.core.enums import (ApprovalState, ContentStatus, Observability,
                            RunStatus, SourceState)
from app.core.errors import ErrorCode, InvalidVertical, LLMProviderError
from app.models import (Approval, ContentBrief, ContentDraft, QAReview,
                        ResearchEvidence, ResearchPackage, ResearchRun,
                        ResearchSource, SeedKeyword)
from app.providers.llm.base import LLMResponse, LLMUsage
from app.providers.research.last30days_normalizer import normalize
from app.services.pipeline import run_pipeline
from tests.test_qa import BODY

QUERY = "prix panneaux solaires Belgique"


class StubResearchProvider:
    code = "last30days"

    def __init__(self, envelope, *, fail_with: Exception | None = None):
        self._envelope = envelope
        self._fail_with = fail_with
        self.calls = 0

    async def research(self, *, query, market, language, correlation_id,
                       idempotency_key=None):
        self.calls += 1
        if self._fail_with:
            raise self._fail_with
        return normalize(self._envelope, query=query, market=market,
                         language=language)

    async def health(self):
        return {"reachable": True}


class StubLLM:
    """Returns a fixed, well-formed draft. Never talks to a network."""

    code = "stub"

    def __init__(self, *, configured: bool = True, body: str = BODY,
                 raise_with: Exception | None = None):
        self._configured = configured
        self._body = body
        self._raise_with = raise_with
        self.calls: list[str] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def generate(self, request):
        self.calls.append(request.capability.value)
        if self._raise_with:
            raise self._raise_with
        if request.capability.value == "CONTENT_BRIEF":
            payload = {"recommended_title": "Prix des panneaux solaires en Belgique",
                       "outline": [{"heading": "Ce qui détermine le prix",
                                    "purpose": "context"}]}
        elif request.capability.value == "SEO_QA":
            payload = {"findings": [{"code": "TONE", "message": "Reads well.",
                                     "severity": "low"}]}
        else:
            payload = {
                "title": "Prix des panneaux solaires en Belgique",
                "meta_title": "Prix panneaux solaires Belgique",
                "meta_description": "Ce qui fait varier le prix d'une installation "
                                    "photovoltaïque et comment comparer deux devis.",
                "body": self._body,
            }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False),
                           provider="stub", model="stub-model",
                           usage=LLMUsage(input_tokens=10, output_tokens=20,
                                          total_tokens=30),
                           latency_ms=5)


async def _run(session, envelope, llm, **kwargs):
    return await run_pipeline(
        session, vertical_code="SOLAR_BE", query=QUERY,
        research_provider=StubResearchProvider(envelope), llm=llm, **kwargs)


class TestWithoutLLM:
    async def test_stops_cleanly_at_llm_not_configured(self, seeded_session, envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False))

        assert result.stopped_at == "draft"
        assert result.error_code == ErrorCode.LLM_NOT_CONFIGURED
        # And the useful work is still persisted.
        assert result.research_run_id is not None
        assert result.research_package_id is not None
        assert result.content_brief_id is not None
        assert result.content_draft_id is None

    async def test_brief_is_complete_without_a_model(self, seeded_session, envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False))
        brief = await seeded_session.get(ContentBrief, result.content_brief_id)

        assert brief.generated_by == "deterministic"
        assert brief.required_facts
        assert brief.required_sources
        assert brief.cautionary_claims
        assert brief.cta_strategy["code"] == "quote_request"
        assert brief.missing_information

    async def test_stop_after_package_skips_the_brief(self, seeded_session, envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False),
                            stop_after="package")
        assert result.stopped_at == "package"
        assert result.content_brief_id is None


class TestResearchPersistence:
    async def test_every_source_state_reaches_the_database(self, seeded_session,
                                                           envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False))

        rows = (await seeded_session.execute(
            select(ResearchSource).where(
                ResearchSource.research_run_id == result.research_run_id)
        )).scalars().all()

        states = {r.status for r in rows}
        # All ten upstream states survive the round trip, including the six that
        # produced no item and would otherwise be invisible.
        assert states == {s.value for s in SourceState}

    async def test_degraded_source_leaves_a_row_with_no_url(self, seeded_session,
                                                            envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False))
        rows = (await seeded_session.execute(
            select(ResearchSource).where(
                ResearchSource.research_run_id == result.research_run_id,
                ResearchSource.status == SourceState.RATE_LIMITED.value)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].url is None
        assert rows[0].source_metadata["item_count"] == 0

    async def test_evidence_observability_is_persisted(self, seeded_session, envelope):
        await _run(seeded_session, envelope, StubLLM(configured=False))
        rows = (await seeded_session.execute(select(ResearchEvidence))).scalars().all()
        observabilities = {r.observability for r in rows}
        assert Observability.OBSERVED.value in observabilities
        assert Observability.UNKNOWN.value in observabilities

    async def test_partial_research_is_recorded_as_partial(self, seeded_session,
                                                           envelope):
        result = await _run(seeded_session, envelope, StubLLM(configured=False))
        run = await seeded_session.get(ResearchRun, result.research_run_id)
        assert run.status == RunStatus.PARTIAL.value
        assert run.error_code == ErrorCode.RESEARCH_PARTIAL
        assert run.engine_commit == "52f53312ff2f272e16bbc1785e1c04f9d9c19b31"

    async def test_research_failure_stops_and_records_the_code(self, seeded_session,
                                                              envelope):
        from app.core.errors import ResearchUnavailable

        result = await run_pipeline(
            seeded_session, vertical_code="SOLAR_BE", query=QUERY,
            research_provider=StubResearchProvider(
                envelope, fail_with=ResearchUnavailable("connection refused")),
            llm=StubLLM(configured=False),
        )
        assert result.stopped_at == "research"
        assert result.error_code == ErrorCode.LAST30DAYS_UNAVAILABLE

        run = await seeded_session.get(ResearchRun, result.research_run_id)
        assert run.status == RunStatus.FAILED.value
        assert run.error_code == ErrorCode.LAST30DAYS_UNAVAILABLE


class TestFullPipeline:
    async def test_reaches_pending_approval(self, seeded_session, envelope):
        """The guarantee this test guards: the pipeline stops at a person.

        It used to also assert QA PASSED. It no longer can, and the reason is
        the point of the next test rather than a regression: SOLAR_BE ratified a
        substance floor of eight supported facts, and this envelope carries five
        community results. Five is not eight, and a page built on it would be
        padding. The pipeline still runs to the end and still parks the draft in
        front of a human, which is what this test exists to protect.
        """
        result = await _run(seeded_session, envelope, StubLLM())

        assert result.content_draft_id is not None
        assert result.approval_state == ApprovalState.PENDING.value
        assert result.stopped_at == "approval"

        draft = await seeded_session.get(ContentDraft, result.content_draft_id)
        assert draft.usage["total_tokens"] == 30
        # Never APPROVED without a person, whatever QA said.
        assert draft.status != ContentStatus.APPROVED.value

    async def test_a_thin_research_envelope_cannot_produce_a_publishable_page(
            self, seeded_session, envelope):
        """And the floor names the real gap: the research, not the draft.

        Blaming the writer for a page it could not have written better would
        send an operator to fix the wrong thing.
        """
        result = await _run(seeded_session, envelope, StubLLM())
        reviews = (await seeded_session.execute(
            select(QAReview).where(
                QAReview.content_draft_id == result.content_draft_id)
        )).scalars().all()
        codes = {f.get("code") for r in reviews for f in (r.blocking_issues or [])}
        assert "INSUFFICIENT_SUPPORTED_EVIDENCE" in codes

    async def test_both_qa_layers_are_recorded(self, seeded_session, envelope):
        result = await _run(seeded_session, envelope, StubLLM())
        reviews = (await seeded_session.execute(
            select(QAReview).where(
                QAReview.content_draft_id == result.content_draft_id)
        )).scalars().all()

        by_type = {r.qa_type: r for r in reviews}
        assert set(by_type) == {"DETERMINISTIC", "LLM_ASSISTED"}
        # The advisory layer can never contribute a blocking issue.
        assert by_type["LLM_ASSISTED"].blocking_issues == []

    async def test_qa_failure_still_creates_a_pending_approval(self, seeded_session,
                                                               envelope):
        """A failed draft is not silently discarded — a human still sees it."""
        bad_body = BODY.replace("Le prix dépend",
                                "Une installation coûte 9 750 € en moyenne. Le prix dépend")
        result = await _run(seeded_session, envelope, StubLLM(body=bad_body))

        assert result.qa_status == "FAILED"
        assert result.error_code == ErrorCode.QA_FAILED
        assert result.approval_state == ApprovalState.PENDING.value

        draft = await seeded_session.get(ContentDraft, result.content_draft_id)
        assert draft.status == ContentStatus.QA_FAILED.value

    async def test_qa_success_never_becomes_approval(self, seeded_session, envelope):
        """The central rule of the gate."""
        result = await _run(seeded_session, envelope, StubLLM())
        approval = await seeded_session.get(Approval, result.approval_id)

        assert approval.state == ApprovalState.PENDING.value
        assert approval.decided_by is None
        assert approval.decided_at is None

    async def test_llm_error_stops_before_persisting_a_draft(self, seeded_session,
                                                             envelope):
        result = await _run(seeded_session, envelope,
                            StubLLM(raise_with=LLMProviderError("upstream 500")))
        assert result.stopped_at == "draft"
        assert result.error_code == ErrorCode.LLM_PROVIDER_ERROR
        assert result.content_draft_id is None

        count = (await seeded_session.execute(
            select(func.count()).select_from(ContentDraft))).scalar_one()
        assert count == 0


class TestIdempotency:
    async def test_second_identical_run_reuses_the_research(self, seeded_session,
                                                            envelope):
        provider = StubResearchProvider(envelope)
        common = dict(vertical_code="SOLAR_BE", query=QUERY,
                      research_provider=provider, llm=StubLLM(configured=False))

        first = await run_pipeline(seeded_session, **common)
        second = await run_pipeline(seeded_session, **common)

        assert provider.calls == 1, "the provider must not be paid twice"
        assert second.research_run_id == first.research_run_id
        assert second.research_package_id == first.research_package_id
        assert any("Reused research run" in n for n in second.notes)

    async def test_case_and_spacing_variants_are_the_same_seed(self, seeded_session,
                                                               envelope):
        provider = StubResearchProvider(envelope)
        await run_pipeline(seeded_session, vertical_code="SOLAR_BE", query=QUERY,
                           research_provider=provider, llm=StubLLM(configured=False))
        await run_pipeline(seeded_session, vertical_code="SOLAR_BE",
                           query="  PRIX   Panneaux Solaires  BELGIQUE ",
                           research_provider=provider, llm=StubLLM(configured=False))

        keywords = (await seeded_session.execute(select(SeedKeyword))).scalars().all()
        assert len(keywords) == 1
        assert provider.calls == 1

    async def test_a_rerun_creates_a_new_brief_not_a_duplicate_package(
            self, seeded_session, envelope):
        provider = StubResearchProvider(envelope)
        common = dict(vertical_code="SOLAR_BE", query=QUERY,
                      research_provider=provider, llm=StubLLM(configured=False))
        await run_pipeline(seeded_session, **common)
        await run_pipeline(seeded_session, **common)

        packages = (await seeded_session.execute(
            select(func.count()).select_from(ResearchPackage))).scalar_one()
        briefs = (await seeded_session.execute(
            select(func.count()).select_from(ContentBrief))).scalar_one()
        assert packages == 1
        assert briefs == 2


class TestValidation:
    async def test_unregistered_vertical_is_refused(self, seeded_session, envelope):
        with pytest.raises(InvalidVertical):
            await run_pipeline(
                seeded_session, vertical_code="NOT_A_VERTICAL", query=QUERY,
                research_provider=StubResearchProvider(envelope),
                llm=StubLLM(configured=False))

    async def test_language_outside_the_profile_is_refused(self, seeded_session,
                                                           envelope):
        with pytest.raises(InvalidVertical) as exc:
            await run_pipeline(
                seeded_session, vertical_code="SOLAR_BE", query=QUERY, language="de",
                research_provider=StubResearchProvider(envelope),
                llm=StubLLM(configured=False))
        assert "de" in str(exc.value)

    async def test_profile_without_a_database_row_is_refused(self, session, envelope):
        """A YAML profile alone does not make a vertical usable."""
        with pytest.raises(InvalidVertical):
            await run_pipeline(
                session, vertical_code="SOLAR_BE", query=QUERY,
                research_provider=StubResearchProvider(envelope),
                llm=StubLLM(configured=False))
