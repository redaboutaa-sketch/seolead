"""Pipeline V2 end to end, with stub providers. Real persistence, no network."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.core.enums import (ApprovalState, ContentStatus, Observability,
                            QALayer, SourceState)
from app.core.errors import ErrorCode, ResearchUnavailable
from app.models import (Approval, ContentDraft, ProviderUsage, QAReview,
                        ResearchPackage, ResearchSource, SeoOpportunity,
                        SerpQuestionRow, SerpSnapshotRow)
from app.providers.llm.base import LLMResponse, LLMUsage
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.schemas.serp import OrganicResult, SerpQuestion, SerpSnapshot
from app.services.pipeline_v2 import run_pipeline_v2
from tests.test_qa import BODY

QUERY = "prix panneaux solaires Belgique"


class StubSearchProvider:
    code = "dataforseo"

    def __init__(self, *, fail: Exception | None = None):
        self.fail = fail
        self.serp_calls = 0
        self.metric_calls = 0
        self._usage = None

    @property
    def configured(self) -> bool:
        return True

    async def serp(self, *, query, context, correlation_id, depth=20):
        self.serp_calls += 1
        if self.fail:
            raise self.fail
        return SerpSnapshot(
            provider="dataforseo", query=query,
            location_code=context.location_code,
            location_name=context.location_name,
            language_code=context.language_code, device=context.device,
            retrieved_at=datetime.now(timezone.utc), total_items=12,
            organic=[
                OrganicResult(rank_group=1, domain="energie.wallonie.be",
                              url="https://energie.wallonie.be/prix",
                              title="Prix des panneaux solaires en Wallonie"),
                OrganicResult(rank_group=2, domain="installateur.be",
                              url="https://installateur.be/devis",
                              title="Comparatif des devis panneaux solaires"),
            ],
            questions=[
                SerpQuestion(text="Combien coûte une installation de 3 kWc ?",
                             kind="PAA"),
                SerpQuestion(text="prix panneaux solaires 2026", kind="RELATED"),
            ],
            provider_cost=0.002,
        )

    async def keyword_metrics(self, *, keywords, context, correlation_id):
        self.metric_calls += 1
        return {}


class StubWebProvider:
    code = "tavily"

    def __init__(self, *, include_irrelevant: bool = True):
        self.include_irrelevant = include_irrelevant
        self.calls = 0
        self._usage = None

    async def research(self, *, query, market, language, correlation_id,
                       idempotency_key=None):
        self.calls += 1
        sources = [NormalizedSource(
            source_type="web", state=SourceState.OK,
            url="https://energie.wallonie.be/prix",
            title="Prix des panneaux solaires en Wallonie",
            summary=("Le prix d'une installation de panneaux solaires dépend de "
                     "la puissance installée, du type de toiture et de la "
                     "complexité de la pose."),
            published_at=datetime.now(timezone.utc), candidate_id="w1")]
        facts = [NormalizedFact(
            fact=("Le prix d'une installation de panneaux solaires dépend de la "
                  "puissance installée, du type de toiture et de la complexité "
                  "de la pose."),
            evidence_type="retrieved_excerpt",
            observability=Observability.OBSERVED, source_ref="w1")]

        if self.include_irrelevant:
            # The Phase 2 poison pill.
            sources.append(NormalizedSource(
                source_type="web", state=SourceState.OK,
                url="https://marnetto.net/2026/07/18/dml-making-of-1",
                title=("The making of Don Matrelli's Legacy, a mod for Grand Prix "
                       "Circuit (part I)"),
                summary="Building a modification for a classic racing game.",
                candidate_id="w2"))
            facts.append(NormalizedFact(
                fact="The track editor supports 20 circuits.",
                evidence_type="retrieved_excerpt",
                observability=Observability.OBSERVED, source_ref="w2"))

        return ResearchProviderResult(
            provider="tavily", query=query, market=market, language=language,
            status="SUCCEEDED", sources=sources, facts=facts,
            source_outcomes=[SourceOutcome(source_type="web", state=SourceState.OK,
                                           item_count=len(sources))])


class StubCommunityProvider:
    code = "last30days"

    def __init__(self):
        self.calls = 0
        self._usage = None

    async def research(self, *, query, market, language, correlation_id,
                       idempotency_key=None):
        self.calls += 1
        return ResearchProviderResult(
            provider="last30days", query=query, market=market, language=language,
            status="SUCCEEDED", sources=[], facts=[],
            source_outcomes=[SourceOutcome(source_type="hackernews",
                                           state=SourceState.NO_RESULTS)])


class StubLLM:
    code = "stub"

    def __init__(self, *, configured: bool = True, body: str = BODY):
        self._configured = configured
        self._body = body
        self.calls: list[str] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def generate(self, request):
        self.calls.append(request.capability.value)
        capability = request.capability.value
        if capability == "CONTENT_BRIEF":
            payload = {"recommended_title": "Prix des panneaux solaires en Belgique",
                       "outline": [{"heading": "Ce qui détermine le prix",
                                    "purpose": "context"}]}
        elif capability == "SEO_QA":
            payload = {"findings": []}
        elif capability == "CLASSIFICATION":
            payload = {"status": "LOW_RELEVANCE", "reason": "unclear"}
        else:
            payload = {
                "title": "Prix des panneaux solaires en Belgique",
                "meta_title": "Prix panneaux solaires Belgique",
                "meta_description": ("Ce qui fait varier le prix d'une "
                                     "installation photovoltaïque en Belgique."),
                "body": self._body,
            }
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False),
                           provider="stub", model="stub-model",
                           usage=LLMUsage(input_tokens=10, output_tokens=20,
                                          total_tokens=30), latency_ms=5)


async def _run(session, settings, **kwargs):
    defaults = dict(
        vertical_code="SOLAR_BE", query=QUERY,
        search_provider=StubSearchProvider(), web_provider=StubWebProvider(),
        community_provider=StubCommunityProvider(), llm=StubLLM(),
    )
    defaults.update(kwargs)
    return await run_pipeline_v2(session, settings=settings, **defaults)


class TestSerpStage:
    async def test_serp_is_persisted_with_questions(self, seeded_session,
                                                    settings_all_providers):
        result = await _run(seeded_session, settings_all_providers)

        assert result.serp_snapshot_id is not None
        snapshot = await seeded_session.get(SerpSnapshotRow, result.serp_snapshot_id)
        assert snapshot.organic_count == 2
        assert snapshot.location_code == 2056
        assert snapshot.provider_cost_usd == 0.002

        questions = (await seeded_session.execute(
            select(SerpQuestionRow).where(
                SerpQuestionRow.serp_snapshot_id == snapshot.id))).scalars().all()
        assert {q.kind for q in questions} == {"PAA", "RELATED"}

    async def test_serp_failure_stops_the_pipeline(self, seeded_session,
                                                   settings_all_providers):
        """SERP is the backbone; without it there is no competitor view or gap."""
        result = await _run(
            seeded_session, settings_all_providers,
            search_provider=StubSearchProvider(fail=ResearchUnavailable("down")))
        assert result.stopped_at == "serp"
        assert result.error_code == ErrorCode.LAST30DAYS_UNAVAILABLE

    async def test_second_run_reuses_a_fresh_snapshot(self, seeded_session,
                                                      settings_all_providers):
        search = StubSearchProvider()
        await _run(seeded_session, settings_all_providers, search_provider=search,
                   llm=StubLLM(configured=False))
        result = await _run(seeded_session, settings_all_providers,
                            search_provider=search, llm=StubLLM(configured=False))

        assert search.serp_calls == 1, "a fresh SERP must not be paid for twice"
        assert result.serp_summary["reused"] is True

    async def test_force_refresh_bypasses_the_cache(self, seeded_session,
                                                    settings_all_providers):
        search = StubSearchProvider()
        await _run(seeded_session, settings_all_providers, search_provider=search,
                   llm=StubLLM(configured=False))
        await _run(seeded_session, settings_all_providers, search_provider=search,
                   llm=StubLLM(configured=False), force_refresh=True)
        assert search.serp_calls == 2


class TestProviderRouting:
    async def test_community_provider_is_not_called_for_solar(
            self, seeded_session, settings_all_providers):
        community = StubCommunityProvider()
        result = await _run(seeded_session, settings_all_providers,
                            community_provider=community,
                            llm=StubLLM(configured=False))
        assert community.calls == 0
        assert result.provider_plan["community"] is False

    async def test_operator_override_calls_it(self, seeded_session,
                                              settings_all_providers):
        community = StubCommunityProvider()
        await _run(seeded_session, settings_all_providers,
                   community_provider=community, force_community=True,
                   llm=StubLLM(configured=False))
        assert community.calls == 1


class TestRelevanceGate:
    async def test_racing_game_source_is_rejected_end_to_end(
            self, seeded_session, settings_all_providers):
        """The Phase 2 failure, reproduced through the whole pipeline."""
        result = await _run(seeded_session, settings_all_providers,
                            llm=StubLLM(configured=False))

        assert result.relevance_summary["rejected"] >= 1
        package = await seeded_session.get(ResearchPackage,
                                           result.research_package_id)

        rejected_titles = " ".join(str(r.get("title"))
                                   for r in package.rejected_evidence)
        assert "Grand Prix" in rejected_titles

        eligible_refs = {e["ref"] for e in package.eligible_evidence}
        assert "w2" not in eligible_refs
        assert "w1" in eligible_refs
        assert all(f["source_ref"] != "w2" for f in package.facts)

    async def test_rejection_reason_is_persisted_on_the_source_row(
            self, seeded_session, settings_all_providers):
        result = await _run(seeded_session, settings_all_providers,
                            llm=StubLLM(configured=False))
        rows = (await seeded_session.execute(
            select(ResearchSource).where(
                ResearchSource.research_run_id.in_(result.research_run_ids))
        )).scalars().all()

        rejected = [r for r in rows if r.relevance_status == "IRRELEVANT"]
        assert rejected, "a rejected source must still be stored"
        assert rejected[0].relevance_reason
        assert "matched only" in rejected[0].relevance_reason

    async def test_clean_run_rejects_nothing(self, seeded_session,
                                             settings_all_providers):
        result = await _run(seeded_session, settings_all_providers,
                            web_provider=StubWebProvider(include_irrelevant=False),
                            llm=StubLLM(configured=False))
        assert result.relevance_summary["rejected"] == 0
        assert result.relevance_summary["eligible"] == 1


class TestOpportunityAndPackage:
    async def test_opportunity_is_scored_and_persisted(self, seeded_session,
                                                       settings_all_providers):
        result = await _run(seeded_session, settings_all_providers,
                            llm=StubLLM(configured=False))
        opportunity = await seeded_session.get(SeoOpportunity,
                                               result.opportunity_id)
        assert opportunity.score_version == "v1"
        assert 0 <= (opportunity.overall_score or 0) <= 100
        assert "search_demand" in opportunity.missing_inputs

    async def test_package_version_tracks_the_builder(self, seeded_session,
                                                      settings_all_providers):
        """V3 introduced atomic claims; V4 added authority, region and freshness.

        Asserted against the builder's own constant rather than a literal, so the
        test tracks the model instead of failing on every version bump.
        """
        from app.services.package_builder_v3 import PACKAGE_VERSION

        result = await _run(seeded_session, settings_all_providers,
                            llm=StubLLM(configured=False))
        package = await seeded_session.get(ResearchPackage,
                                           result.research_package_id)
        assert package.package_version == PACKAGE_VERSION
        assert PACKAGE_VERSION >= 3
        assert package.serp_snapshot_id is not None
        assert package.user_questions
        assert package.content_gap


class TestFullRun:
    async def test_reaches_pending_approval(self, seeded_session,
                                            settings_all_providers):
        result = await _run(seeded_session, settings_all_providers)

        assert result.content_draft_id is not None
        assert result.approval_state == ApprovalState.PENDING.value
        draft = await seeded_session.get(ContentDraft, result.content_draft_id)
        assert draft.status in (ContentStatus.PENDING_APPROVAL.value,
                                ContentStatus.QA_FAILED.value)

    async def test_three_qa_reviews_are_recorded(self, seeded_session,
                                                 settings_all_providers):
        result = await _run(seeded_session, settings_all_providers)
        reviews = (await seeded_session.execute(
            select(QAReview).where(
                QAReview.content_draft_id == result.content_draft_id)
        )).scalars().all()
        # factual + SEO (deterministic) and one advisory.
        assert len(reviews) == 3
        assert sum(1 for r in reviews if r.qa_type == "LLM_ASSISTED") == 1

    async def test_qa_success_never_becomes_approval(self, seeded_session,
                                                     settings_all_providers):
        result = await _run(seeded_session, settings_all_providers)
        approval = await seeded_session.get(Approval, result.approval_id)
        assert approval.state == ApprovalState.PENDING.value
        assert approval.decided_by is None

    async def test_a_rejected_draft_does_not_block_its_replacement(
            self, seeded_session, settings_all_providers):
        """The deadlock this fix exists for.

        A rejected draft is TERMINAL — `approval_service` allows no transition
        out of `REJECTED` — so it can never be published and can never compete
        for a query. Counting its title made every rerun of the same query
        permanently unpublishable, because the writer is seeded with the
        brief's `working_title` and converges on the same title.
        """
        first = await _run(seeded_session, settings_all_providers)
        draft = await seeded_session.get(ContentDraft, first.content_draft_id)
        titre = draft.title
        draft.status = ContentStatus.REJECTED.value
        await seeded_session.commit()

        second = await _run(seeded_session, settings_all_providers)
        replacement = await seeded_session.get(ContentDraft,
                                               second.content_draft_id)
        assert replacement.title == titre, \
            "the rerun must produce the same title for this test to mean anything"
        seo = (await seeded_session.execute(
            select(QAReview).where(
                QAReview.content_draft_id == second.content_draft_id,
                QAReview.layer == QALayer.SEO.value))).scalars().one()
        codes = {f.get("code") for f in seo.findings}
        assert "DUPLICATE_TITLE" not in codes

    async def test_an_undecided_draft_still_blocks_its_replacement(
            self, seeded_session, settings_all_providers):
        """The other half, kept deliberately.

        A draft that merely failed QA is undecided. Letting a replacement
        appear silently beside it is how a queue fills with identical drafts,
        so the title stays taken until an operator disposes of it.
        """
        first = await _run(seeded_session, settings_all_providers)
        second = await _run(seeded_session, settings_all_providers)
        seo = (await seeded_session.execute(
            select(QAReview).where(
                QAReview.content_draft_id == second.content_draft_id,
                QAReview.layer == QALayer.SEO.value))).scalars().one()
        codes = {f.get("code") for f in seo.findings}
        assert "DUPLICATE_TITLE" in codes
        assert first.content_draft_id != second.content_draft_id

    async def test_no_llm_stops_after_the_brief(self, seeded_session,
                                                settings_all_providers):
        result = await _run(seeded_session, settings_all_providers,
                            llm=StubLLM(configured=False))
        assert result.stopped_at == "draft"
        assert result.error_code == ErrorCode.LLM_NOT_CONFIGURED
        assert result.research_package_id is not None
        assert result.content_brief_id is not None
        assert result.content_draft_id is None

    async def test_every_called_provider_appears_in_the_ledger(
            self, seeded_session, settings_all_providers):
        """The orchestrator backstops adapters that do not record themselves.

        Adapters record their own usage because only they know the provider's
        reported cost. That makes the ledger depend on each adapter remembering,
        and one that forgets is silently absent from the cost report — invisible
        exactly where money is involved. These stubs record nothing, so they
        exercise the backstop.
        """
        result = await _run(seeded_session, settings_all_providers)
        rows = (await seeded_session.execute(
            select(ProviderUsage).where(
                ProviderUsage.correlation_id == result.correlation_id)
        )).scalars().all()

        providers = {r.provider for r in rows}
        assert "dataforseo" in providers
        assert "tavily" in providers

        # A call with no reported cost is recorded as UNKNOWN, never as free.
        unpriced = [r for r in rows if r.cost_usd is None]
        assert unpriced and all(r.cost_is_actual is False for r in unpriced)
        assert result.usage_summary["total_cost_usd"] is None
