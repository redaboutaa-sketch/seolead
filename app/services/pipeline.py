"""The Phase 2 pipeline: seed query → research → package → brief → draft → QA → approval.

Runs inline. There is no queue and no worker, because Phase 2 has one operator
running one job at a time and a Celery broker would be infrastructure carrying no
weight.

The orchestration rule throughout: **a stage that cannot run stops the pipeline
with a code, it does not degrade into inventing its output.** Missing LLM
credentials stop it at LLM_NOT_CONFIGURED with the package and the deterministic
brief already persisted — which is a genuinely useful result, not a failure.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (ApprovalState, ContentStatus, KeywordStatus, QAType,
                            RunStatus, SearchIntent)
from app.core.errors import (ErrorCode, InvalidVertical, LLMNotConfigured,
                             ResearchProviderError, SeoLeadError)
from app.models import (Approval, ContentBrief, ContentDraft, QAReview,
                        ResearchEvidence, ResearchPackage, ResearchRun,
                        ResearchSource, SeedKeyword, Vertical)
from app.providers.llm.base import LLMProvider
from app.providers.research.base import ResearchProvider
from app.services import brief_service, draft_service, package_builder, qa_service
from app.services.intent import classify_intent, normalize_query
from app.verticals.profile import VerticalProfile, load_profile

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Everything an operator needs to inspect what happened, including failures."""

    correlation_id: str
    vertical_code: str
    keyword_id: uuid.UUID | None = None
    research_run_id: uuid.UUID | None = None
    research_package_id: uuid.UUID | None = None
    content_brief_id: uuid.UUID | None = None
    content_draft_id: uuid.UUID | None = None
    qa_review_ids: list[uuid.UUID] = field(default_factory=list)
    approval_id: uuid.UUID | None = None
    research_status: str | None = None
    qa_status: str | None = None
    approval_state: str | None = None
    stopped_at: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "vertical": self.vertical_code,
            "keyword_id": str(self.keyword_id) if self.keyword_id else None,
            "research_run_id": str(self.research_run_id) if self.research_run_id else None,
            "research_package_id": (
                str(self.research_package_id) if self.research_package_id else None
            ),
            "content_brief_id": (
                str(self.content_brief_id) if self.content_brief_id else None
            ),
            "content_draft_id": (
                str(self.content_draft_id) if self.content_draft_id else None
            ),
            "qa_review_ids": [str(i) for i in self.qa_review_ids],
            "approval_id": str(self.approval_id) if self.approval_id else None,
            "research_status": self.research_status,
            "qa_status": self.qa_status,
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


async def _get_or_create_keyword(
    session: AsyncSession, *, vertical: Vertical, query: str, language: str,
    market: str,
) -> SeedKeyword:
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

    keyword = SeedKeyword(
        vertical_id=vertical.id, query=query.strip(), normalized_query=normalized,
        language=language, market=market, status=KeywordStatus.NEW.value,
    )
    session.add(keyword)
    await session.flush()
    return keyword


async def _persist_research(
    session: AsyncSession, run: ResearchRun, result,
) -> None:
    """Persist sources and evidence.

    Every source *type* gets a row even when it produced no item, so a degraded
    source leaves a trace. Without this, a rate-limited source and a source that
    genuinely found nothing would be indistinguishable in the database.
    """
    by_type: dict[str, list] = {}
    for source in result.sources:
        by_type.setdefault(source.source_type, []).append(source)

    for outcome in result.source_outcomes:
        items = by_type.get(outcome.source_type, [])
        if not items:
            session.add(ResearchSource(
                research_run_id=run.id, source_type=outcome.source_type,
                status=outcome.state.value,
                source_metadata={"item_count": 0, "no_item_reason": outcome.state.value},
            ))

    # Facts are attached to the source carrying their candidate_id.
    facts_by_ref: dict[str | None, list] = {}
    for fact in result.facts:
        facts_by_ref.setdefault(fact.source_ref, []).append(fact)

    for source in result.sources:
        row = ResearchSource(
            research_run_id=run.id,
            source_type=source.source_type,
            url=source.url,
            title=source.title,
            published_at=source.published_at,
            retrieved_at=source.retrieved_at,
            status=source.state.value,
            confidence=source.confidence,
            freshness_verdict=(
                source.freshness_verdict.value if source.freshness_verdict else None
            ),
            candidate_id=source.candidate_id,
            source_metadata=source.metadata,
        )
        session.add(row)
        await session.flush()

        for fact in facts_by_ref.get(source.candidate_id, []):
            session.add(ResearchEvidence(
                research_source_id=row.id,
                fact=fact.fact,
                evidence_type=fact.evidence_type,
                confidence=fact.confidence,
                observability=fact.observability.value,
            ))


async def run_pipeline(
    session: AsyncSession,
    *,
    vertical_code: str,
    query: str,
    market: str | None = None,
    language: str | None = None,
    research_provider: ResearchProvider,
    llm: LLMProvider,
    correlation_id: str | None = None,
    stop_after: str | None = None,
) -> PipelineResult:
    """Execute the bounded pipeline. Commits once per completed stage."""
    correlation_id = correlation_id or uuid.uuid4().hex
    profile: VerticalProfile = load_profile(vertical_code)
    market = (market or profile.market).upper()
    language = (language or profile.default_language).lower()

    if language not in profile.languages:
        raise InvalidVertical(
            f"language {language!r} is not configured for vertical {vertical_code!r} "
            f"(configured: {', '.join(profile.languages)})"
        )

    result = PipelineResult(correlation_id=correlation_id, vertical_code=vertical_code)
    log_ctx = {"correlation_id": correlation_id, "vertical": vertical_code}

    vertical = await _get_vertical(session, vertical_code)
    keyword = await _get_or_create_keyword(
        session, vertical=vertical, query=query, language=language, market=market
    )
    result.keyword_id = keyword.id
    await session.commit()

    # ── Stage 1: research ────────────────────────────────────────────────────
    from app.providers.research.last30days import build_idempotency_key

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    idem = build_idempotency_key(normalize_query(query), market, language, day)

    existing_run = (
        await session.execute(
            select(ResearchRun).where(ResearchRun.idempotency_key == idem)
        )
    ).scalar_one_or_none()

    if existing_run is not None and existing_run.status in (
        RunStatus.SUCCEEDED.value, RunStatus.PARTIAL.value
    ):
        # Same query, same market, same day: reuse rather than pay for it twice.
        run = existing_run
        result.notes.append(
            f"Reused research run {run.id} (same query/market/language today)."
        )
        result.research_run_id = run.id
        result.research_status = run.status
        package = (
            await session.execute(
                select(ResearchPackage)
                .where(ResearchPackage.research_run_id == run.id)
                .order_by(ResearchPackage.version.desc())
            )
        ).scalars().first()
    else:
        run = ResearchRun(
            keyword_id=keyword.id, provider=research_provider.code,
            status=RunStatus.RUNNING.value, idempotency_key=idem,
            correlation_id=correlation_id, started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        keyword.status = KeywordStatus.RESEARCHING.value
        await session.commit()
        result.research_run_id = run.id

        try:
            provider_result = await research_provider.research(
                query=query, market=market, language=language,
                correlation_id=correlation_id, idempotency_key=idem,
            )
        except ResearchProviderError as exc:
            run.status = RunStatus.FAILED.value
            run.error_code = exc.code
            run.error_detail = exc.detail
            run.completed_at = datetime.now(timezone.utc)
            keyword.status = KeywordStatus.FAILED.value
            await session.commit()
            logger.error("research failed", extra={**log_ctx, "error_code": exc.code})
            result.research_status = RunStatus.FAILED.value
            result.stopped_at = "research"
            result.error_code = exc.code
            result.error_detail = exc.detail
            return result

        run.status = (
            RunStatus.PARTIAL.value if provider_result.status == "PARTIAL"
            else RunStatus.SUCCEEDED.value
        )
        run.completed_at = datetime.now(timezone.utc)
        run.duration_ms = provider_result.duration_ms
        run.engine_commit = provider_result.engine_commit
        run.engine_version = provider_result.engine_version
        run.provider_metadata = provider_result.provider_metadata
        if run.status == RunStatus.PARTIAL.value:
            run.error_code = ErrorCode.RESEARCH_PARTIAL

        await _persist_research(session, run, provider_result)
        keyword.status = KeywordStatus.RESEARCHED.value
        result.research_status = run.status

        # ── Stage 2: package ─────────────────────────────────────────────────
        intent: SearchIntent = classify_intent(query, profile)
        payload = package_builder.build_package_payload(
            provider_result, intent=intent, profile=profile
        )
        package = ResearchPackage(
            keyword_id=keyword.id, research_run_id=run.id, version=1, **payload
        )
        session.add(package)
        await session.commit()

    if package is None:
        result.stopped_at = "package"
        result.error_code = ErrorCode.RESEARCH_FAILED
        result.error_detail = "reused research run has no package"
        return result

    result.research_package_id = package.id
    if package.confidence_summary.get("partial_observation"):
        result.notes.append(
            "Research was partial — at least one source could not be observed."
        )

    if stop_after == "package":
        result.stopped_at = "package"
        return result

    # ── Stage 3: brief (deterministic core, optional LLM synthesis) ──────────
    package_dict = {
        "query": package.query, "market": package.market, "language": package.language,
        "intent": package.intent, "facts": package.facts, "sources": package.sources,
        "user_questions": package.user_questions,
        "unresolved_questions": package.unresolved_questions,
        "confidence_summary": package.confidence_summary,
    }
    brief_payload = brief_service.build_brief_payload(
        package_dict, profile=profile, query=query
    )
    brief_payload = await brief_service.enrich_brief_with_llm(
        brief_payload, llm=llm, correlation_id=correlation_id
    )

    brief = ContentBrief(
        research_package_id=package.id,
        status=ContentStatus.BRIEF_CREATED.value,
        **brief_payload,
    )
    session.add(brief)
    await session.commit()
    result.content_brief_id = brief.id

    if stop_after == "brief":
        result.stopped_at = "brief"
        return result

    # ── Stage 4: draft ───────────────────────────────────────────────────────
    if not llm.configured:
        result.stopped_at = "draft"
        result.error_code = ErrorCode.LLM_NOT_CONFIGURED
        result.error_detail = (
            "No LLM provider configured. Research package and deterministic brief "
            "were produced and persisted."
        )
        logger.info("pipeline stopped: no LLM configured",
                    extra={**log_ctx, "error_code": ErrorCode.LLM_NOT_CONFIGURED})
        return result

    try:
        draft_payload, llm_response = await draft_service.generate_draft(
            brief_payload, package_dict, llm=llm, correlation_id=correlation_id
        )
    except LLMNotConfigured as exc:
        result.stopped_at = "draft"
        result.error_code = exc.code
        result.error_detail = exc.detail
        return result
    except SeoLeadError as exc:
        result.stopped_at = "draft"
        result.error_code = exc.code or ErrorCode.CONTENT_GENERATION_FAILED
        result.error_detail = exc.detail
        logger.error("draft generation failed",
                     extra={**log_ctx, "error_code": result.error_code})
        return result

    draft = ContentDraft(
        content_brief_id=brief.id,
        provider=llm_response.provider,
        model=llm_response.model,
        title=draft_payload["title"],
        body=draft_payload["body"],
        meta_title=draft_payload["meta_title"],
        meta_description=draft_payload["meta_description"],
        status=ContentStatus.DRAFT_CREATED.value,
        usage=llm_response.usage.model_dump(),
        latency_ms=llm_response.latency_ms,
    )
    session.add(draft)
    brief.status = ContentStatus.DRAFT_CREATED.value
    await session.commit()
    result.content_draft_id = draft.id

    # ── Stage 5: QA ──────────────────────────────────────────────────────────
    existing_titles = (
        await session.execute(
            select(ContentDraft.title).where(ContentDraft.id != draft.id)
        )
    ).scalars().all()

    deterministic = qa_service.run_deterministic_qa(
        draft_payload, brief_payload, package_dict, profile,
        existing_titles=existing_titles,
    )
    det_review = QAReview(
        content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value, **deterministic
    )
    session.add(det_review)
    await session.flush()
    result.qa_review_ids.append(det_review.id)

    advisory = await qa_service.run_llm_qa(
        draft_payload, brief_payload, llm=llm, correlation_id=correlation_id
    )
    llm_review = QAReview(
        content_draft_id=draft.id, qa_type=QAType.LLM_ASSISTED.value, **advisory
    )
    session.add(llm_review)
    await session.flush()
    result.qa_review_ids.append(llm_review.id)

    # Only the deterministic layer decides. The advisory layer never blocks.
    qa_passed = not deterministic["blocking_issues"]
    draft.status = (
        ContentStatus.QA_PASSED.value if qa_passed else ContentStatus.QA_FAILED.value
    )
    result.qa_status = deterministic["status"]

    # ── Stage 6: approval gate ───────────────────────────────────────────────
    # Created regardless of QA outcome, and always PENDING. QA success is not
    # approval; a human still has to look.
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
            f"{len(deterministic['blocking_issues'])} blocking QA issue(s)"
        )

    logger.info("pipeline complete", extra={**log_ctx, "status": result.qa_status,
                                            "draft_id": str(draft.id)})
    return result
