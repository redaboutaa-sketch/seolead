"""Internal API — pipeline trigger, inspection, approval.

Every route here is behind `require_internal_key`. Nothing on this router may be
made public: the approval endpoints decide whether content is fit to publish, and
an unauthenticated approval is worse than no approval gate at all.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (get_community_provider, get_llm, get_research_provider,
                          get_search_provider, get_web_provider,
                          require_internal_key)
from app.core.enums import ApprovalState
from app.core.errors import InvalidVertical, SeoLeadError
from app.db.session import get_session
from app.core.config import Settings, get_settings
from app.models import (Approval, ContentBrief, ContentDraft, ProviderUsage,
                        QAReview, ResearchPackage, ResearchRun, SeoOpportunity,
                        SerpQuestionRow, SerpResultRow, SerpSnapshotRow)
from app.providers.llm.base import LLMProvider
from app.providers.research.base import ResearchProvider
from app.services import approval_service
from app.services.pipeline import run_pipeline
from app.services.pipeline_v2 import run_pipeline_v2
from app.services.research_cache import freshness_policy
from app.verticals.profile import available_profiles

router = APIRouter(prefix="/internal/v1", tags=["internal"],
                   dependencies=[Depends(require_internal_key)])


class ResearchJobRequest(BaseModel):
    vertical: str = Field(..., min_length=2, max_length=64)
    query: str = Field(..., min_length=3, max_length=300)
    market: str | None = Field(None, max_length=8)
    language: str | None = Field(None, max_length=8)
    correlation_id: str | None = Field(None, max_length=64)
    stop_after: str | None = Field(None, pattern="^(package|brief)$")
    device: str = Field("desktop", pattern="^(desktop|mobile)$")
    # Bypass the freshness cache and pay for fresh research.
    force_refresh: bool = False
    # Override the vertical's community-research policy for this job only.
    force_community: bool | None = None
    # v2 is the Phase 3 pipeline (SERP + relevance gate). v1 is the Phase 2 path,
    # kept so a vertical with no SERP budget can still produce a brief.
    engine: str = Field("v2", pattern="^(v1|v2)$")

    @field_validator("vertical")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("query")
    @classmethod
    def _clean_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("query contains no usable characters")
        return cleaned


class ApprovalDecision(BaseModel):
    decided_by: str = Field(..., min_length=1, max_length=128)
    note: str | None = Field(None, max_length=2000)


@router.get("/verticals")
async def list_verticals() -> dict:
    return {"profiles": available_profiles()}


@router.post("/research-jobs", status_code=status.HTTP_201_CREATED)
async def create_research_job(
    payload: ResearchJobRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    research: ResearchProvider = Depends(get_research_provider),
    search: object = Depends(get_search_provider),
    web: ResearchProvider = Depends(get_web_provider),
    community: ResearchProvider = Depends(get_community_provider),
    llm: LLMProvider = Depends(get_llm),
) -> dict:
    """Run the bounded pipeline synchronously and return every artefact id.

    Synchronous on purpose: an operator who triggered a job wants the ids, not a
    polling loop.
    """
    try:
        if payload.engine == "v1":
            result = await run_pipeline(
                session, vertical_code=payload.vertical, query=payload.query,
                market=payload.market, language=payload.language,
                research_provider=research, llm=llm,
                correlation_id=payload.correlation_id,
                stop_after=payload.stop_after,
            )
        else:
            result = await run_pipeline_v2(
                session, settings=settings, vertical_code=payload.vertical,
                query=payload.query, market=payload.market,
                language=payload.language, device=payload.device,
                search_provider=search, web_provider=web,
                community_provider=community, llm=llm,
                correlation_id=payload.correlation_id,
                force_refresh=payload.force_refresh,
                force_community=payload.force_community,
                stop_after=payload.stop_after,
            )
    except InvalidVertical as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"code": exc.code, "message": exc.detail}) from exc
    except SeoLeadError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail={"code": exc.code, "message": exc.detail}) from exc

    return result.as_dict()


@router.get("/credentials")
async def credential_status(settings: Settings = Depends(get_settings)) -> dict:
    """CONFIGURED / NOT_CONFIGURED per provider.

    Statuses only — no value, no prefix, no length. A report that leaks four
    characters of a key is still a leak.
    """
    return {"credentials": settings.credential_report(),
            "freshness_policy": freshness_policy(settings)}


@router.get("/research-packages/{package_id}/rejected")
async def get_rejected_evidence(
    package_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    """Every source the relevance gate threw away, and why.

    This endpoint exists because Phase 2 could not answer "why was this source
    dropped", which is the first question asked whenever the gate misbehaves.
    """
    package = await session.get(ResearchPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "package_id": str(package.id),
        "query": package.query,
        "eligible_count": len(package.eligible_evidence or []),
        "rejected_count": len(package.rejected_evidence or []),
        "rejected": [
            {
                "ref": r.get("ref"), "provider": r.get("provider"),
                "url": r.get("url"), "title": r.get("title"),
                "status": r.get("rejection_status"),
                "reason": r.get("rejection_reason"),
                "relevance": r.get("relevance"),
                "source_quality": r.get("source_quality"),
            }
            for r in (package.rejected_evidence or [])
        ],
    }


@router.get("/serp-snapshots/{snapshot_id}")
async def get_serp_snapshot(
    snapshot_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    snapshot = await session.get(SerpSnapshotRow, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="not found")
    results = (await session.execute(
        select(SerpResultRow).where(SerpResultRow.serp_snapshot_id == snapshot.id)
        .order_by(SerpResultRow.rank_absolute))).scalars().all()
    questions = (await session.execute(
        select(SerpQuestionRow).where(
            SerpQuestionRow.serp_snapshot_id == snapshot.id))).scalars().all()
    return {
        "id": str(snapshot.id), "provider": snapshot.provider,
        "query": snapshot.query, "location": snapshot.location_name,
        "language": snapshot.language_code, "device": snapshot.device,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "organic_count": snapshot.organic_count,
        "provider_cost_usd": snapshot.provider_cost_usd,
        "analysis": snapshot.analysis,
        "organic": [
            {"rank": r.rank_group or r.rank_absolute, "domain": r.domain,
             "url": r.url, "title": r.title, "shape": r.shape}
            for r in results
        ],
        "questions": [{"kind": q.kind, "text": q.text} for q in questions],
    }


@router.get("/opportunities/{opportunity_id}")
async def get_opportunity(
    opportunity_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    opportunity = await session.get(SeoOpportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": str(opportunity.id), "overall_score": opportunity.overall_score,
        "confidence": opportunity.confidence,
        "version": opportunity.score_version,
        "components": opportunity.components,
        "missing_inputs": opportunity.missing_inputs,
        "interpretation": ("Prioritisation heuristic, not a prediction. Confidence "
                           "is the share of scoring weight actually measured."),
    }


@router.get("/usage/{correlation_id}")
async def get_usage(
    correlation_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    rows = (await session.execute(
        select(ProviderUsage).where(
            ProviderUsage.correlation_id == correlation_id[:64]))).scalars().all()
    known = [r.cost_usd for r in rows if r.cost_usd is not None]
    return {
        "correlation_id": correlation_id,
        "events": [
            {"provider": r.provider, "operation": r.operation,
             "requests": r.requests, "units": r.units, "cost_usd": r.cost_usd,
             "cost_is_actual": r.cost_is_actual, "duration_ms": r.duration_ms}
            for r in rows
        ],
        # None, not 0.0: a job whose providers report no cost has an unknown
        # spend, not a free one.
        "total_cost_usd": round(sum(known), 6) if known else None,
        "unpriced_events": sum(1 for r in rows if r.cost_usd is None),
    }


@router.get("/research-packages/{package_id}")
async def get_research_package(
    package_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    package = await session.get(ResearchPackage, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": str(package.id),
        "query": package.query,
        "market": package.market,
        "language": package.language,
        "intent": package.intent,
        "summary": package.summary,
        "confidence_summary": package.confidence_summary,
        "facts": package.facts,
        "sources": package.sources,
        "user_questions": package.user_questions,
        "unresolved_questions": package.unresolved_questions,
        "provider_provenance": package.provider_provenance,
    }


@router.get("/research-runs/{run_id}")
async def get_research_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    run = await session.get(ResearchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": str(run.id), "provider": run.provider, "status": run.status,
        "error_code": run.error_code, "duration_ms": run.duration_ms,
        "engine_commit": run.engine_commit, "engine_version": run.engine_version,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/briefs/{brief_id}")
async def get_brief(
    brief_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    brief = await session.get(ContentBrief, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": str(brief.id),
        "research_package_id": str(brief.research_package_id),
        "content_type": brief.content_type,
        "search_intent": brief.search_intent,
        "primary_query": brief.primary_query,
        "recommended_title": brief.recommended_title,
        "recommended_slug": brief.recommended_slug,
        "target_audience": brief.target_audience,
        "objective": brief.objective,
        "outline": brief.outline,
        "key_questions": brief.key_questions,
        "required_facts": brief.required_facts,
        "required_sources": brief.required_sources,
        "cautionary_claims": brief.cautionary_claims,
        "cta_strategy": brief.cta_strategy,
        "missing_information": brief.missing_information,
        "generated_by": brief.generated_by,
        "status": brief.status,
    }


@router.get("/drafts/{draft_id}")
async def get_draft(
    draft_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    draft = await session.get(ContentDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="not found")

    reviews = (
        await session.execute(
            select(QAReview).where(QAReview.content_draft_id == draft.id)
        )
    ).scalars().all()
    approval = (
        await session.execute(
            select(Approval).where(Approval.content_draft_id == draft.id)
        )
    ).scalar_one_or_none()

    return {
        "id": str(draft.id),
        "content_brief_id": str(draft.content_brief_id),
        "provider": draft.provider, "model": draft.model,
        "title": draft.title, "meta_title": draft.meta_title,
        "meta_description": draft.meta_description, "body": draft.body,
        "status": draft.status, "usage": draft.usage,
        "latency_ms": draft.latency_ms,
        "qa_reviews": [
            {"id": str(r.id), "qa_type": r.qa_type, "status": r.status,
             "score": r.score, "findings": r.findings,
             "blocking_issues": r.blocking_issues}
            for r in reviews
        ],
        "approval": (
            {"id": str(approval.id), "state": approval.state,
             "decided_by": approval.decided_by,
             "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
             "note": approval.note}
            if approval else None
        ),
    }


@router.get("/drafts")
async def list_pending_drafts(
    session: AsyncSession = Depends(get_session)
) -> dict:
    """The operator's queue: everything still awaiting a human decision."""
    rows = (
        await session.execute(
            select(ContentDraft, Approval)
            .join(Approval, Approval.content_draft_id == ContentDraft.id)
            .where(Approval.state.in_(
                [ApprovalState.PENDING.value, ApprovalState.NEEDS_REVISION.value]
            ))
            .order_by(ContentDraft.created_at.desc())
            .limit(100)
        )
    ).all()
    return {"drafts": [
        {"draft_id": str(d.id), "title": d.title, "status": d.status,
         "approval_state": a.state,
         "created_at": d.created_at.isoformat() if d.created_at else None}
        for d, a in rows
    ]}


async def _decide(
    session: AsyncSession, draft_id: uuid.UUID, target: ApprovalState,
    payload: ApprovalDecision,
) -> dict:
    from datetime import datetime, timezone

    approval = (
        await session.execute(
            select(Approval).where(Approval.content_draft_id == draft_id)
        )
    ).scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="no approval record for this draft")

    current = ApprovalState(approval.state)
    try:
        approval_service.assert_transition(current, target)
    except approval_service.InvalidTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_TRANSITION", "message": str(exc),
                    "current_state": current.value},
        ) from exc

    approval.state = target.value
    approval.decided_by = payload.decided_by
    approval.decided_at = datetime.now(timezone.utc)
    approval.note = payload.note

    draft = await session.get(ContentDraft, draft_id)
    if draft is not None:
        draft.status = approval_service.draft_status_for(target).value

    await session.commit()
    return {"draft_id": str(draft_id), "approval_state": approval.state,
            "decided_by": approval.decided_by,
            "publishable": approval_service.is_publishable(target)}


@router.post("/content/{draft_id}/approve")
async def approve(draft_id: uuid.UUID, payload: ApprovalDecision,
                  session: AsyncSession = Depends(get_session)) -> dict:
    return await _decide(session, draft_id, ApprovalState.APPROVED, payload)


@router.post("/content/{draft_id}/reject")
async def reject(draft_id: uuid.UUID, payload: ApprovalDecision,
                 session: AsyncSession = Depends(get_session)) -> dict:
    return await _decide(session, draft_id, ApprovalState.REJECTED, payload)


@router.post("/content/{draft_id}/request-revision")
async def request_revision(draft_id: uuid.UUID, payload: ApprovalDecision,
                           session: AsyncSession = Depends(get_session)) -> dict:
    return await _decide(session, draft_id, ApprovalState.NEEDS_REVISION, payload)
