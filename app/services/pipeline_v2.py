"""Phase 3 pipeline: SERP + web research → relevance gate → package V2 → draft → QA.

Same orchestration contract as Phase 2 — deterministic control flow, an LLM that
never causes a side effect, a stage that cannot run stops with a code — extended
with the search-intelligence layer and the relevance gate.

The gate is the structural change. In Phase 2 every retrieved source became
evidence. Here a source must pass relevance before the writer ever sees it, and
what it rejected is persisted with the reason, because "why was this thrown away"
is the question an operator asks when relevance misbehaves.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import (ApprovalState, ContentStatus, EvidenceStatus,
                            KeywordStatus, ObservationStatus, QAType,
                            RunStatus, SearchIntent)
from app.core.errors import (ErrorCode, InvalidVertical, LLMNotConfigured,
                             ResearchProviderError, SeoLeadError)
from app.models import (Approval, ContentBrief, ContentDraft, EvidencePassage,
                        KeywordMetricRow, ProviderUsage, QAReview,
                        ResearchEvidence, ResearchPackage, ResearchRun,
                        ResearchSource, SeedKeyword, SeoOpportunity,
                        SerpQuestionRow, SerpResultRow, SerpSnapshotRow, Vertical)
from app.providers.capabilities import plan_providers
from app.providers.llm.base import LLMProvider
from app.providers.research.base import ResearchProvider
from app.providers.search.base import SearchIntelligenceProvider
from app.providers.search.location import get_search_context
from app.services.authoritative_research import execute_plan
from app.services.authority_registry import build_registry
from app.services.research_planner import plan_authoritative_research
from app.schemas.serp import KeywordMetric, SerpSnapshot
from app.services import (brief_service, draft_service, factual_qa_v2,
                          opportunity_score, package_builder_v3, qa_service,
                          serp_analysis)
from app.services.intent import classify_intent, normalize_query
from app.services.provider_usage import JobBudget, UsageRecorder
from app.services.relevance import (RelevanceDecision, RelevanceStatus,
                                    score_source, semantic_review)
from app.services.research_cache import (ResearchKind, is_fresh, serp_cache_key)
from app.services.source_quality import SourceQuality, classify_domain
from app.verticals.profile import VerticalProfile, load_profile

logger = logging.getLogger(__name__)


@dataclass
class PipelineV2Result:
    correlation_id: str
    vertical_code: str
    keyword_id: uuid.UUID | None = None
    serp_snapshot_id: uuid.UUID | None = None
    research_run_ids: list[uuid.UUID] = field(default_factory=list)
    research_package_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    content_brief_id: uuid.UUID | None = None
    content_draft_id: uuid.UUID | None = None
    qa_review_ids: list[uuid.UUID] = field(default_factory=list)
    approval_id: uuid.UUID | None = None
    provider_plan: dict = field(default_factory=dict)
    serp_summary: dict = field(default_factory=dict)
    relevance_summary: dict = field(default_factory=dict)
    authoritative: dict = field(default_factory=dict)
    package_summary: dict = field(default_factory=dict)
    opportunity_summary: dict = field(default_factory=dict)
    factual_qa: dict = field(default_factory=dict)
    seo_qa: dict = field(default_factory=dict)
    usage_summary: dict = field(default_factory=dict)
    approval_state: str | None = None
    stopped_at: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        def sid(value):
            return str(value) if value else None

        return {
            "correlation_id": self.correlation_id,
            "vertical": self.vertical_code,
            "keyword_id": sid(self.keyword_id),
            "serp_snapshot_id": sid(self.serp_snapshot_id),
            "research_run_ids": [str(i) for i in self.research_run_ids],
            "research_package_id": sid(self.research_package_id),
            "seo_opportunity_id": sid(self.opportunity_id),
            "content_brief_id": sid(self.content_brief_id),
            "content_draft_id": sid(self.content_draft_id),
            "qa_review_ids": [str(i) for i in self.qa_review_ids],
            "approval_id": sid(self.approval_id),
            "provider_plan": self.provider_plan,
            "serp": self.serp_summary,
            "relevance": self.relevance_summary,
            "authoritative": self.authoritative,
            "package": self.package_summary,
            "opportunity": self.opportunity_summary,
            "factual_qa": self.factual_qa,
            "seo_qa": self.seo_qa,
            "provider_usage": self.usage_summary,
            "approval_state": self.approval_state,
            "stopped_at": self.stopped_at,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "notes": self.notes,
        }


async def _get_vertical(session: AsyncSession, code: str) -> Vertical:
    vertical = (
        await session.execute(select(Vertical).where(Vertical.code == code))
    ).scalar_one_or_none()
    if vertical is None:
        raise InvalidVertical(f"vertical {code!r} is not registered")
    if not vertical.active:
        raise InvalidVertical(f"vertical {code!r} is inactive")
    return vertical


async def _get_or_create_keyword(session, *, vertical, query, language, market):
    normalized = normalize_query(query)
    existing = (
        await session.execute(
            select(SeedKeyword).where(
                SeedKeyword.vertical_id == vertical.id,
                SeedKeyword.normalized_query == normalized,
                SeedKeyword.language == language,
                SeedKeyword.market == market,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    keyword = SeedKeyword(vertical_id=vertical.id, query=query.strip(),
                          normalized_query=normalized, language=language,
                          market=market, status=KeywordStatus.NEW.value)
    session.add(keyword)
    await session.flush()
    return keyword


async def _persist_serp(session, *, keyword, snapshot: SerpSnapshot, analysis: dict,
                        cache_key: str) -> SerpSnapshotRow:
    row = SerpSnapshotRow(
        keyword_id=keyword.id, provider=snapshot.provider, query=snapshot.query,
        cache_key=cache_key, location_code=snapshot.location_code,
        location_name=snapshot.location_name,
        language_code=snapshot.language_code, device=snapshot.device,
        se_domain=snapshot.se_domain, retrieved_at=snapshot.retrieved_at,
        total_items=snapshot.total_items, organic_count=len(snapshot.organic),
        provider_cost_usd=snapshot.provider_cost, analysis=analysis,
        provider_metadata=snapshot.provider_metadata,
    )
    session.add(row)
    await session.flush()

    shapes = {p.get("url"): p.get("shape", {})
              for p in analysis.get("competitor_pages", [])}
    for result in snapshot.organic:
        session.add(SerpResultRow(
            serp_snapshot_id=row.id, rank_group=result.rank_group,
            rank_absolute=result.rank_absolute, result_type="organic",
            is_organic=True, domain=result.domain, url=result.url,
            title=result.title, description=result.description,
            breadcrumb=result.breadcrumb, shape=shapes.get(result.url, {}),
        ))
    for question in snapshot.questions:
        session.add(SerpQuestionRow(
            serp_snapshot_id=row.id, kind=question.kind, text=question.text,
            rank_absolute=question.rank_absolute,
        ))
    return row


async def _persist_research(session, *, keyword, result, decisions, correlation_id):
    """One ResearchRun per provider, with relevance decisions on every source."""
    run = ResearchRun(
        keyword_id=keyword.id, provider=result.provider,
        status=(RunStatus.PARTIAL.value if result.status == "PARTIAL"
                else RunStatus.SUCCEEDED.value),
        idempotency_key=f"{correlation_id}:{result.provider}",
        correlation_id=correlation_id,
        started_at=result.started_at, completed_at=result.completed_at,
        duration_ms=result.duration_ms, engine_commit=result.engine_commit,
        engine_version=result.engine_version,
        provider_metadata=result.provider_metadata,
    )
    session.add(run)
    await session.flush()

    for index, source in enumerate(result.sources):
        ref = source.candidate_id or f"{result.provider}-{index:03d}"
        decision = decisions.get(ref)
        quality = classify_domain(source.url, source_type=source.source_type)
        row = ResearchSource(
            research_run_id=run.id, source_type=source.source_type,
            provider=result.provider, url=source.url, title=source.title,
            published_at=source.published_at, retrieved_at=source.retrieved_at,
            status=source.state.value, confidence=source.confidence,
            freshness_verdict=(source.freshness_verdict.value
                               if source.freshness_verdict else None),
            candidate_id=ref,
            relevance_status=decision.status.value if decision else None,
            relevance_score=decision.score if decision else None,
            # Kept even when rejected: this is the audit trail for the gate.
            relevance_reason=decision.reason if decision else None,
            source_quality=quality.value,
            source_metadata=source.metadata,
        )
        session.add(row)

    # Source-level outcomes with no item still leave a trace (Phase 2 rule).
    seen = {s.source_type for s in result.sources}
    for outcome in result.source_outcomes:
        if outcome.source_type not in seen:
            session.add(ResearchSource(
                research_run_id=run.id, source_type=outcome.source_type,
                provider=result.provider, status=outcome.state.value,
                source_metadata={"item_count": 0,
                                 "no_item_reason": outcome.state.value},
            ))
    return run


async def run_pipeline_v2(
    session: AsyncSession,
    *,
    settings: Settings,
    vertical_code: str,
    query: str,
    market: str | None = None,
    language: str | None = None,
    device: str = "desktop",
    search_provider: SearchIntelligenceProvider,
    web_provider: ResearchProvider,
    community_provider: ResearchProvider | None,
    llm: LLMProvider,
    correlation_id: str | None = None,
    force_refresh: bool = False,
    force_community: bool | None = None,
    stop_after: str | None = None,
    authoritative: bool = True,
) -> PipelineV2Result:
    correlation_id = correlation_id or uuid.uuid4().hex
    profile: VerticalProfile = load_profile(vertical_code)
    market = (market or profile.market).upper()
    language = (language or profile.default_language).lower()

    if language not in profile.languages:
        raise InvalidVertical(
            f"language {language!r} is not configured for vertical {vertical_code!r} "
            f"(configured: {', '.join(profile.languages)})"
        )

    result = PipelineV2Result(correlation_id=correlation_id,
                              vertical_code=vertical_code)
    log_ctx = {"correlation_id": correlation_id, "vertical": vertical_code}

    context = get_search_context(market, language, device=device)
    intent: SearchIntent = classify_intent(query, profile)

    budget = JobBudget(default_max_calls=settings.max_calls_per_provider)
    usage = UsageRecorder(budget=budget)
    # Rebind the recorder so provider adapters write into this job's ledger.
    for provider in (search_provider, web_provider, community_provider):
        if provider is not None and hasattr(provider, "_usage"):
            provider._usage = usage  # noqa: SLF001 — deliberate injection point

    plan = plan_providers(query=query, intent=intent, profile=profile,
                          force_community=force_community)
    result.provider_plan = plan.as_dict()

    vertical = await _get_vertical(session, vertical_code)
    keyword = await _get_or_create_keyword(session, vertical=vertical, query=query,
                                           language=language, market=market)
    result.keyword_id = keyword.id
    await session.commit()

    # ── Stage 1: SERP ────────────────────────────────────────────────────────
    snapshot: SerpSnapshot | None = None
    analysis: dict = {}
    serp_row: SerpSnapshotRow | None = None
    cache_key = serp_cache_key(query=query, location_code=context.location_code,
                               language_code=context.language_code,
                               device=context.device)

    if plan.serp:
        cached = None
        if not force_refresh:
            cached = (
                await session.execute(
                    select(SerpSnapshotRow)
                    .where(SerpSnapshotRow.cache_key == cache_key)
                    .order_by(SerpSnapshotRow.retrieved_at.desc())
                )
            ).scalars().first()
            if cached and not is_fresh(cached.retrieved_at, ResearchKind.SERP,
                                       settings):
                cached = None

        if cached is not None:
            serp_row = cached
            analysis = cached.analysis or {}
            result.serp_snapshot_id = cached.id
            result.notes.append(
                f"Reused SERP snapshot from {cached.retrieved_at.isoformat()} "
                f"(TTL {settings.serp_ttl_hours}h)."
            )
            result.serp_summary = {
                "reused": True, "organic_count": cached.organic_count,
                "retrieved_at": cached.retrieved_at.isoformat(),
                "location": cached.location_name, "language": cached.language_code,
            }
        else:
            try:
                usage.check_and_consume("dataforseo")
                snapshot = await search_provider.serp(
                    query=query, context=context, correlation_id=correlation_id,
                    depth=settings.dataforseo_serp_depth)
            except ResearchProviderError as exc:
                # SERP is the backbone. Without it there is no competitor view, no
                # PAA and no gap analysis, so this stops rather than degrading.
                result.stopped_at = "serp"
                result.error_code = exc.code
                result.error_detail = exc.detail
                result.usage_summary = usage.summary()
                logger.error("SERP stage failed",
                             extra={**log_ctx, "error_code": exc.code})
                return result

            usage.ensure_recorded(provider="dataforseo", operation="serp",
                                  correlation_id=correlation_id)
            analysis = serp_analysis.analyse_serp(snapshot, profile)
            serp_row = await _persist_serp(session, keyword=keyword,
                                           snapshot=snapshot, analysis=analysis,
                                           cache_key=cache_key)
            await session.commit()
            result.serp_snapshot_id = serp_row.id
            result.serp_summary = {
                "reused": False,
                "organic_count": len(snapshot.organic),
                "total_items": snapshot.total_items,
                "paa_count": len(snapshot.paa),
                "related_count": len(snapshot.related),
                "features": sorted(snapshot.feature_types),
                "dominant_framing": analysis.get("dominant_framing"),
                "content_gap": analysis.get("content_gap", []),
                "location": context.location_name,
                "language": context.language_code,
                "device": context.device,
                "provider_cost_usd": snapshot.provider_cost,
            }

    # ── Stage 2: keyword metrics (optional) ──────────────────────────────────
    metrics: list[KeywordMetric] = []
    if plan.keyword_metrics:
        try:
            usage.check_and_consume("dataforseo")
            by_keyword = await search_provider.keyword_metrics(
                keywords=[query], context=context, correlation_id=correlation_id)
            usage.ensure_recorded(provider="dataforseo",
                                  operation="keyword_metrics",
                                  correlation_id=correlation_id)
            metrics = by_keyword.get(query, [])
            for metric in metrics:
                session.add(KeywordMetricRow(
                    keyword_id=keyword.id, provider=metric.provider,
                    metric_type=metric.metric_type, value=metric.value,
                    value_text=metric.value_text, currency=metric.currency,
                    observability=metric.observability.value,
                    retrieved_at=metric.retrieved_at or datetime.now(timezone.utc),
                ))
            await session.commit()
        except SeoLeadError as exc:
            # Metrics are a nice-to-have. Their absence is UNKNOWN, not a failure.
            result.notes.append(
                f"Keyword metrics unavailable ({exc.code}); demand scores as UNKNOWN."
            )

    # ── Stage 3: research providers ──────────────────────────────────────────
    research_results = []

    if plan.web_research:
        try:
            usage.check_and_consume("tavily")
            web_result = await web_provider.research(
                query=query, market=market, language=language,
                correlation_id=correlation_id)
            usage.ensure_recorded(provider=web_provider.code, operation="search",
                                  correlation_id=correlation_id,
                                  duration_ms=web_result.duration_ms)
            research_results.append(web_result)
        except ResearchProviderError as exc:
            result.notes.append(f"Web research failed ({exc.code}): {exc.detail}")

    if plan.community and community_provider is not None:
        try:
            usage.check_and_consume("last30days")
            community_result = await community_provider.research(
                query=query, market=market, language=language,
                correlation_id=correlation_id)
            usage.ensure_recorded(provider=community_provider.code,
                                  operation="research",
                                  correlation_id=correlation_id,
                                  duration_ms=community_result.duration_ms)
            research_results.append(community_result)
        except ResearchProviderError as exc:
            result.notes.append(f"Community research failed ({exc.code}).")

    if not research_results:
        result.stopped_at = "research"
        result.error_code = ErrorCode.RESEARCH_FAILED
        result.error_detail = "No research provider returned a result."
        result.usage_summary = usage.summary()
        return result

    # ── Stage 4: relevance gate ──────────────────────────────────────────────
    decisions: dict[str, RelevanceDecision] = {}
    thresholds = settings.relevance_thresholds()

    for provider_result in research_results:
        for index, source in enumerate(provider_result.sources):
            ref = source.candidate_id or f"{provider_result.provider}-{index:03d}"
            decision = score_source(
                query=query, profile=profile, title=source.title,
                body=source.summary, url=source.url, thresholds=thresholds)

            # Stage B only for the ambiguous middle, and never to overturn a hard
            # rejection — a model that disagrees with "shares no topic with the
            # query" is wrong, and asking invites it to be.
            if (settings.relevance_semantic_enabled
                    and decision.status is RelevanceStatus.LOW_RELEVANCE):
                decision = await semantic_review(
                    query=query, title=source.title, body=source.summary,
                    llm=llm, correlation_id=correlation_id, current=decision)

            decisions[ref] = decision

    eligible = sum(1 for d in decisions.values() if d.status.is_eligible)
    rejected = len(decisions) - eligible
    result.relevance_summary = {
        "evaluated": len(decisions),
        "eligible": eligible,
        "rejected": rejected,
        "by_status": {
            status.value: sum(1 for d in decisions.values() if d.status is status)
            for status in RelevanceStatus
        },
        "semantic_reviews": sum(1 for d in decisions.values()
                                if d.stage == "semantic"),
    }

    for provider_result in research_results:
        run = await _persist_research(session, keyword=keyword,
                                      result=provider_result, decisions=decisions,
                                      correlation_id=correlation_id)
        result.research_run_ids.append(run.id)
    keyword.status = KeywordStatus.RESEARCHED.value
    await session.commit()

    # ── Stage 5: package ─────────────────────────────────────────────────────
    registry = build_registry(profile)
    payload = package_builder_v3.build_package_v3(
        query=query, market=market, language=language, intent=intent,
        profile=profile, serp=snapshot, serp_analysis=analysis,
        keyword_metrics=metrics, research_results=research_results,
        relevance_decisions=decisions, thresholds=thresholds, registry=registry,
    )

    # ── Stage 5b: targeted authoritative research ────────────────────────────
    # A general web search does not surface a regulator for a pricing query, so
    # HIGH-risk claims would stay permanently unresolvable without this pass.
    # It runs only when something is actually blocked, and only against domains
    # the vertical configured.
    authoritative_summary: dict = {}
    if authoritative:
        unresolved = [c for c in payload["claims"]
                      if c["claim_risk"] == "HIGH"
                      and c["evidence_status"] != EvidenceStatus.SUPPORTED.value]
        # Phase 3.4: an unanswered core question is also a research gap. The
        # HIGH-risk trigger alone never fired for pricing — price claims are
        # MEDIUM and LOW risk — so a price query whose evidence answered nothing
        # produced no second look at all.
        price_gap = _price_answer_missing(query, payload["claims"], profile)
        if unresolved or price_gap:
            plan = plan_authoritative_research(
                topic=query, market=market,
                unresolved=_as_evaluated(payload["claims"], profile,
                                         price_gap=price_gap),
                profile=profile)
            if not plan.is_empty:
                run = await execute_plan(
                    plan, profile=profile, registry=registry,
                    web_provider=web_provider, market=market, language=language,
                    correlation_id=correlation_id, usage=usage)
                authoritative_summary = run.as_dict()
                result.authoritative = authoritative_summary

                if run.accepted:
                    official_result = run.to_provider_result(
                        query=query, market=market, language=language)
                    research_results.append(official_result)

                    # Official pages go through the same relevance gate as
                    # everything else — being official does not make a page
                    # on-topic.
                    for index, source in enumerate(official_result.sources):
                        ref = source.candidate_id or f"official-{index:03d}"
                        decisions[ref] = score_source(
                            query=query, profile=profile, title=source.title,
                            body=source.summary, url=source.url,
                            thresholds=thresholds)

                    run_row = await _persist_research(
                        session, keyword=keyword, result=official_result,
                        decisions=decisions, correlation_id=correlation_id)
                    result.research_run_ids.append(run_row.id)
                    await session.commit()

                    # Rebuild rather than patch: the enriched package supersedes
                    # the first, and its version records what it replaced.
                    payload = package_builder_v3.build_package_v3(
                        query=query, market=market, language=language,
                        intent=intent, profile=profile, serp=snapshot,
                        serp_analysis=analysis, keyword_metrics=metrics,
                        research_results=research_results,
                        relevance_decisions=decisions, thresholds=thresholds,
                        registry=registry,
                        authoritative_run=authoritative_summary,
                        previous_package_version=package_builder_v3.PACKAGE_VERSION,
                    )
                else:
                    payload["authoritative_run"] = authoritative_summary

    # Attach claim risk to the persisted evidence rows.
    await _persist_evidence(session, result.research_run_ids, payload, profile)

    # ── Stage 6: opportunity score ───────────────────────────────────────────
    mean_relevance = payload["confidence_summary"].get("mean_relevance")
    score = opportunity_score.compute(
        intent=intent, profile=profile, serp_analysis=analysis,
        keyword_metrics=metrics,
        eligible_evidence_count=len(payload["eligible_evidence"]),
        topic_alignment=mean_relevance,
    )
    opportunity = SeoOpportunity(
        keyword_id=keyword.id, overall_score=score.overall,
        confidence=score.confidence, score_version=score.version,
        components=[c.as_dict() for c in score.components],
        missing_inputs=score.missing_inputs,
    )
    session.add(opportunity)
    await session.flush()
    result.opportunity_id = opportunity.id
    result.opportunity_summary = score.as_dict()

    package = ResearchPackage(
        keyword_id=keyword.id,
        research_run_id=result.research_run_ids[0],
        version=1,
        package_version=package_builder_v3.PACKAGE_VERSION,
        serp_snapshot_id=serp_row.id if serp_row else None,
        seo_opportunity_id=opportunity.id,
        query=payload["query"], market=payload["market"],
        language=payload["language"], intent=payload["intent"],
        summary=payload["summary"], facts=payload["facts"],
        sources=payload["sources"],
        eligible_evidence=payload["eligible_evidence"],
        rejected_evidence=payload["rejected_evidence"],
        competitor_pages=payload["competitor_pages"],
        serp_observations=payload["serp_observations"],
        serp_features=payload["serp_features"],
        content_gap=payload["content_gap"],
        user_questions=payload["user_questions"],
        related_searches=payload["related_searches"],
        keyword_metrics=payload["keyword_metrics"],
        source_quality_summary=payload["source_quality_summary"],
        claim_risk_summary=payload["claim_risk_summary"],
        unresolved_questions=payload["unresolved_questions"],
        confidence_summary=payload["confidence_summary"],
        provider_provenance=payload["provider_provenance"],
    )
    session.add(package)
    await session.commit()

    result.research_package_id = package.id
    result.package_summary = payload["confidence_summary"]

    if stop_after == "package":
        result.stopped_at = "package"
        result.usage_summary = usage.summary()
        await _persist_usage(session, usage, correlation_id)
        return result

    # ── Stage 7: brief ───────────────────────────────────────────────────────
    brief_payload = brief_service.build_brief_payload(payload, profile=profile,
                                                      query=query)
    # The SERP is the clearest statement of what searchers also want to know.
    if payload["user_questions"]:
        brief_payload["key_questions"] = payload["user_questions"][:10]
    brief_payload = await brief_service.enrich_brief_with_llm(
        brief_payload, llm=llm, correlation_id=correlation_id)

    brief = ContentBrief(research_package_id=package.id,
                         status=ContentStatus.BRIEF_CREATED.value, **brief_payload)
    session.add(brief)
    await session.commit()
    result.content_brief_id = brief.id

    if stop_after == "brief":
        result.stopped_at = "brief"
        result.usage_summary = usage.summary()
        await _persist_usage(session, usage, correlation_id)
        return result

    # ── Stage 8: draft ───────────────────────────────────────────────────────
    if not llm.configured:
        result.stopped_at = "draft"
        result.error_code = ErrorCode.LLM_NOT_CONFIGURED
        result.error_detail = ("No LLM provider configured. SERP, research package "
                               "and deterministic brief were produced and persisted.")
        result.usage_summary = usage.summary()
        await _persist_usage(session, usage, correlation_id)
        return result

    # The writer sees supported claims, unresolved facts and forbidden topics —
    # never a rejected source and never a raw page excerpt.
    writer_view = package_builder_v3.writer_payload(payload, allow_partial=False)

    try:
        draft_payload, llm_response = await draft_service.generate_draft(
            brief_payload, {**payload, "writer_view": writer_view},
            llm=llm, correlation_id=correlation_id)
    except (LLMNotConfigured, SeoLeadError) as exc:
        result.stopped_at = "draft"
        result.error_code = exc.code or ErrorCode.CONTENT_GENERATION_FAILED
        result.error_detail = exc.detail
        result.usage_summary = usage.summary()
        await _persist_usage(session, usage, correlation_id)
        return result

    usage.record(provider=llm_response.provider, operation="draft",
                 correlation_id=correlation_id, requests=1,
                 units=llm_response.usage.total_tokens,
                 cost_usd=None, cost_is_actual=False,
                 duration_ms=llm_response.latency_ms)

    draft = ContentDraft(
        content_brief_id=brief.id, provider=llm_response.provider,
        model=llm_response.model, title=draft_payload["title"],
        body=draft_payload["body"], meta_title=draft_payload["meta_title"],
        meta_description=draft_payload["meta_description"],
        status=ContentStatus.DRAFT_CREATED.value,
        usage=llm_response.usage.model_dump(), latency_ms=llm_response.latency_ms,
    )
    session.add(draft)
    brief.status = ContentStatus.DRAFT_CREATED.value
    await session.commit()
    result.content_draft_id = draft.id

    # ── Stage 9: QA ──────────────────────────────────────────────────────────
    existing_titles = (
        await session.execute(
            select(ContentDraft.title).where(ContentDraft.id != draft.id))
    ).scalars().all()

    factual = factual_qa_v2.run_factual_qa_v2(draft_payload, payload, profile)
    factual_row = QAReview(content_draft_id=draft.id,
                           qa_type=QAType.DETERMINISTIC.value,
                           status=factual["status"], score=factual["score"],
                           findings=factual["findings"] + [
                               {"code": "CLAIM_LEDGER",
                                "message": "atomic claim ledger",
                                "blocking": False, "detail": "",
                                "ledger": factual["claim_ledger"]}],
                           blocking_issues=factual["blocking_issues"])
    session.add(factual_row)
    await session.flush()
    result.qa_review_ids.append(factual_row.id)
    result.factual_qa = {"status": factual["status"], "score": factual["score"],
                         "claim_ledger": factual["claim_ledger"],
                         "blocking": len(factual["blocking_issues"])}

    seo = qa_service.run_seo_qa_v2(draft_payload, brief_payload, payload, profile,
                                   existing_titles=existing_titles)
    seo_row = QAReview(content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
                       status=seo["status"], score=seo["score"],
                       findings=seo["findings"],
                       blocking_issues=seo["blocking_issues"])
    session.add(seo_row)
    await session.flush()
    result.qa_review_ids.append(seo_row.id)
    result.seo_qa = {"status": seo["status"], "score": seo["score"],
                     "findings": len(seo["findings"]),
                     "blocking": len(seo["blocking_issues"])}

    advisory = await qa_service.run_llm_qa(draft_payload, brief_payload, llm=llm,
                                           correlation_id=correlation_id)
    advisory_row = QAReview(content_draft_id=draft.id,
                            qa_type=QAType.LLM_ASSISTED.value, **advisory)
    session.add(advisory_row)
    await session.flush()
    result.qa_review_ids.append(advisory_row.id)

    qa_passed = not (factual["blocking_issues"] or seo["blocking_issues"])
    draft.status = (ContentStatus.QA_PASSED.value if qa_passed
                    else ContentStatus.QA_FAILED.value)

    # ── Stage 10: approval gate ──────────────────────────────────────────────
    approval = Approval(content_draft_id=draft.id, state=ApprovalState.PENDING.value)
    session.add(approval)
    if qa_passed:
        draft.status = ContentStatus.PENDING_APPROVAL.value
    await session.commit()

    result.approval_id = approval.id
    result.approval_state = ApprovalState.PENDING.value
    result.stopped_at = "approval"
    if not qa_passed:
        result.error_code = ErrorCode.QA_FAILED
        result.error_detail = (
            f"{len(factual['blocking_issues'])} factual and "
            f"{len(seo['blocking_issues'])} SEO blocking issue(s)")

    result.usage_summary = usage.summary()
    await _persist_usage(session, usage, correlation_id)

    logger.info("pipeline v2 complete", extra={
        **log_ctx, "status": draft.status, "draft_id": str(draft.id)})
    return result


async def _persist_evidence(session, run_ids, payload, profile) -> None:
    """Persist atomic claims and the passages supporting them.

    One `research_evidence` row per claim; one `evidence_passage` row per
    (claim, source) pair. A claim with three corroborating sources leaves three
    passage rows, which is what makes corroboration auditable after the fact.
    """
    if not run_ids:
        return
    sources = (
        await session.execute(
            select(ResearchSource).where(ResearchSource.research_run_id.in_(run_ids)))
    ).scalars().all()
    by_ref = {s.candidate_id: s for s in sources if s.candidate_id}

    for claim in payload.get("claims", []):
        origin = by_ref.get(claim.get("source_ref"))
        if origin is None:
            continue
        evidence = ResearchEvidence(
            research_source_id=origin.id,
            fact=claim["claim"],
            passage=claim.get("passage"),
            evidence_type="atomic_claim",
            observability=_observation_for(claim),
            claim_risk=claim.get("claim_risk"),
            claim_category=claim.get("category"),
            evidence_status=claim.get("evidence_status"),
            authority_requirement=claim.get("authority_requirement"),
            freshness_requirement=claim.get("freshness_requirement"),
            corroborating_sources=claim.get("corroborating_sources"),
            extraction_method=claim.get("extraction_method"),
            evaluation_reason=claim.get("reason"),
            support_status=claim.get("evidence_status"),
            evidence_sufficient=(claim.get("evidence_status")
                                 == EvidenceStatus.SUPPORTED.value),
        )
        session.add(evidence)
        await session.flush()

        for ref in claim.get("evidence", []):
            source_row = by_ref.get(ref.get("source_ref"))
            if source_row is None:
                continue
            session.add(EvidencePassage(
                research_evidence_id=evidence.id,
                research_source_id=source_row.id,
                passage=ref.get("passage", "")[:4000],
                supports=bool(ref.get("supports")),
                agrees_numerically=ref.get("agrees_numerically"),
                observation_status=ref.get("observation_status"),
                source_quality=ref.get("source_quality"),
                note=ref.get("note"),
            ))


def _observation_for(claim: dict) -> str:
    """Observation status of the claim's best supporting evidence.

    Recorded alongside — never instead of — the evidence status. They answer
    different questions.
    """
    for ref in claim.get("evidence", []):
        if ref.get("supports") and ref.get("observation_status"):
            return str(ref["observation_status"])
    return ObservationStatus.ESTIMATED.value


async def _persist_usage(session, usage: UsageRecorder, correlation_id: str) -> None:
    for event in usage.events:
        session.add(ProviderUsage(
            correlation_id=correlation_id, provider=event.provider,
            operation=event.operation, requests=event.requests, units=event.units,
            cost_usd=event.cost_usd, cost_is_actual=event.cost_is_actual,
            duration_ms=event.duration_ms,
        ))
    await session.commit()


_PRICE_ANSWER_CATEGORIES = ("OBSERVED_PRICE_RANGE", "MARKET_AVERAGE",
                            "MARKET_PRICE", "VENDOR_PRICE")


def _price_answer_missing(query: str, claims: list[dict], profile) -> bool:
    """Whether a price query ended with no usable, supported price figure.

    Config-driven throughout: a vertical that declares no price policy, or a query
    its own vocabulary does not recognise as a price question, has no price gap by
    definition.
    """
    from app.services.price_normalization import extract_price_context

    policy = getattr(profile, "price_policy", None) or {}
    if not policy.get("enabled"):
        return False
    terms = [t.casefold() for t in policy.get("price_query_terms") or ()]
    if not any(term in query.casefold() for term in terms):
        return False

    for claim in claims:
        if claim.get("category") not in _PRICE_ANSWER_CATEGORIES:
            continue
        if claim.get("evidence_status") != EvidenceStatus.SUPPORTED.value:
            continue
        context = extract_price_context(claim.get("claim") or "")
        if context is not None and context.is_usable:
            return False
    return True


def _as_evaluated(claims: list[dict], profile, *, price_gap: bool = False) -> list:
    """Rehydrate claims the planner should look for better sources for.

    The planner reasons over `EvaluatedClaim`, and the package carries dicts. A
    thin shim beats threading the objects through the whole builder just so one
    consumer can read two fields.
    """
    from app.services.claim_extraction import AtomicClaim
    from app.services.claim_policy import requirements_for
    from app.services.evidence_model import EvaluatedClaim

    out = []
    for claim in claims:
        wanted = (claim.get("claim_risk") == "HIGH"
                  or (price_gap
                      and claim.get("category") in _PRICE_ANSWER_CATEGORIES))
        if not wanted:
            continue
        if claim.get("evidence_status") == EvidenceStatus.SUPPORTED.value:
            continue
        atomic = AtomicClaim(text=claim["claim"], passage=claim.get("passage", ""),
                             source_ref=claim.get("source_ref", ""), offset=0)
        evaluated = EvaluatedClaim(claim=atomic,
                                   requirements=requirements_for(claim["claim"],
                                                                 profile))
        evaluated.status = EvidenceStatus(claim["evidence_status"])
        out.append(evaluated)
    return out
