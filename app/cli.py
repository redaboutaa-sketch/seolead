"""Operator CLI.

The CLI is the primary Phase 2 interface. It talks to the database directly rather
than to the HTTP API, so an operator can run the pipeline and approve content on a
box where the API is not exposed at all — which is the intended deployment.

    seolead seed
    seolead research run --vertical SOLAR_BE --query "..." --market BE --language fr
    seolead package show <id>
    seolead brief show <id>
    seolead draft show <id>
    seolead content pending
    seolead content approve <draft-id> --by "name" [--note "..."]
    seolead content reject <draft-id> --by "name"
    seolead content request-revision <draft-id> --by "name"
    seolead health

    seolead site seed [--site solar_be]
    seolead site list
    seolead site preview <slug> [--site solar_be] [--locale fr]
    seolead content list --status APPROVED
    seolead content stage <draft-id> [--site solar_be] [--locale fr] [--slug ...]
    seolead content publish <published-content-id>
    seolead leads list [--status PENDING_EXPORT]
    seolead leads export [--limit 50] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import ApprovalState
from app.core.errors import SeoLeadError
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.models import (Approval, CapturedLead, ContentBrief, ContentDraft,
                        LeadAttribution, ProviderUsage, PublishedContent,
                        QAReview, ResearchPackage, SeedKeyword, SeoOpportunity,
                        Site, SerpQuestionRow, SerpResultRow, SerpSnapshotRow,
                        Vertical)
from app.providers.llm.registry import get_llm_provider
from app.providers.research.last30days import Last30DaysProvider
from app.providers.research.tavily import TavilyResearchProvider
from app.providers.search.dataforseo import DataForSEOProvider
from app.providers.search.location import supported_contexts
from app.services import approval_service
from app.services.authoritative_research import execute_plan
from app.services.authority_registry import build_registry
from app.services.pipeline import run_pipeline
from app.services.claim_policy import requirements_for
from app.services.pipeline_v2 import _as_evaluated, run_pipeline_v2
from app.services.provider_usage import UsageRecorder
from app.services.research_planner import plan_authoritative_research
from app.services.research_cache import freshness_policy
from app.services.region import detect_region
from app.verticals.profile import available_profiles, load_profile

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2      # ran correctly, but stopped at a gate (QA / no LLM)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


# ─── Commands ────────────────────────────────────────────────────────────────

async def cmd_seed(args: argparse.Namespace) -> int:
    """Idempotent. Re-running never duplicates a vertical or a site."""
    async with get_sessionmaker()() as session:
        created = []
        for code in (args.vertical or ["SOLAR_BE"]):
            profile = load_profile(code)
            existing = (
                await session.execute(select(Vertical).where(Vertical.code == code))
            ).scalar_one_or_none()
            if existing is None:
                vertical = Vertical(
                    code=profile.code, name=profile.name, market=profile.market,
                    default_language=profile.default_language, active=True,
                )
                session.add(vertical)
                await session.flush()
                created.append(f"vertical:{code}")
            else:
                vertical = existing

            site_name = f"{profile.name} SEO Pilot"
            site = (
                await session.execute(
                    select(Site).where(Site.vertical_id == vertical.id,
                                       Site.name == site_name)
                )
            ).scalar_one_or_none()
            if site is None:
                session.add(Site(
                    vertical_id=vertical.id, name=site_name,
                    domain=None,            # No domain in Phase 2, and none needed.
                    market=profile.market,
                    default_language=profile.default_language,
                ))
                created.append(f"site:{site_name}")
        await session.commit()
    _emit({"seeded": created or "nothing to do (already present)"})
    return EXIT_OK


async def cmd_research_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        try:
            if args.engine == "v1":
                result = await run_pipeline(
                    session, vertical_code=args.vertical.upper(), query=args.query,
                    market=args.market, language=args.language,
                    research_provider=Last30DaysProvider(settings),
                    llm=get_llm_provider(settings), stop_after=args.stop_after,
                )
            else:
                result = await run_pipeline_v2(
                    session, settings=settings,
                    vertical_code=args.vertical.upper(), query=args.query,
                    market=args.market, language=args.language,
                    device=args.device,
                    search_provider=DataForSEOProvider(settings),
                    web_provider=TavilyResearchProvider(settings),
                    community_provider=Last30DaysProvider(settings),
                    llm=get_llm_provider(settings),
                    force_refresh=args.force_refresh,
                    force_community=args.force_community,
                    stop_after=args.stop_after,
                    authoritative=getattr(args, "authoritative", True),
                )
        except SeoLeadError as exc:
            _emit({"error_code": exc.code, "detail": exc.detail})
            return EXIT_ERROR

    _emit(result.as_dict())
    if result.error_code:
        return EXIT_BLOCKED
    return EXIT_OK


async def cmd_authoritative_run(args: argparse.Namespace) -> int:
    """Execute the authoritative plan for an existing ResearchPackage.

    Enriches the package in place rather than starting a new job: the commercial
    evidence has already been paid for, and only the official gap needs filling.
    """
    settings = get_settings()
    async with get_sessionmaker()() as session:
        package = await session.get(ResearchPackage, uuid.UUID(args.package_id))
        if package is None:
            _emit({"error": "package not found"})
            return EXIT_ERROR

        keyword = await session.get(SeedKeyword, package.keyword_id)
        profile = load_profile(
            (await session.get(Vertical, keyword.vertical_id)).code)
        registry = build_registry(profile)

        unresolved = _as_evaluated(package.facts or [], profile)
        plan = plan_authoritative_research(
            topic=package.query, market=package.market, unresolved=unresolved,
            profile=profile)

        if args.plan_only or plan.is_empty:
            _emit({"package_id": str(package.id), "query": package.query,
                   "unresolved_high_risk": len(unresolved),
                   "plan": plan.as_dict(),
                   "executed": False})
            return EXIT_OK if not plan.is_empty else EXIT_BLOCKED

        usage = UsageRecorder()
        run = await execute_plan(
            plan, profile=profile, registry=registry,
            web_provider=TavilyResearchProvider(settings, usage=usage),
            market=package.market, language=package.language,
            correlation_id=f"authoritative-{package.id.hex[:16]}", usage=usage)

        _emit({"package_id": str(package.id), "query": package.query,
               "unresolved_high_risk_before": len(unresolved),
               "plan": plan.as_dict(), "run": run.as_dict(),
               "provider_usage": usage.summary()})
    return EXIT_OK


async def cmd_credentials(args: argparse.Namespace) -> int:
    """Report CONFIGURED / NOT_CONFIGURED. Never a value, never a prefix."""
    settings = get_settings()
    report = settings.credential_report()
    _emit({
        "credentials": report,
        "ready_for_live_test": all(
            report[k] == "CONFIGURED" for k in ("DATAFORSEO", "TAVILY", "OPENAI")
        ),
        "search_contexts": supported_contexts(),
        "freshness_policy": freshness_policy(settings),
    })
    return EXIT_OK


async def cmd_package_rejected(args: argparse.Namespace) -> int:
    """Show what the relevance gate threw away, and why."""
    async with get_sessionmaker()() as session:
        package = await session.get(ResearchPackage, uuid.UUID(args.id))
        if package is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        _emit({
            "package_id": str(package.id), "query": package.query,
            "eligible_count": len(package.eligible_evidence or []),
            "rejected_count": len(package.rejected_evidence or []),
            "rejected": [
                {"ref": r.get("ref"), "provider": r.get("provider"),
                 "title": r.get("title"), "url": r.get("url"),
                 "status": r.get("rejection_status"),
                 "reason": r.get("rejection_reason")}
                for r in (package.rejected_evidence or [])
            ],
        })
    return EXIT_OK


async def cmd_package_replay(args: argparse.Namespace) -> int:
    """Re-classify a sealed package's claims against the CURRENT policy.

    Read-only and free: no provider is called, nothing is written, the package is
    not modified. It answers one question — how many of these claims were being
    held to a requirement they inherited from a mislabelling?

    What it CANNOT answer is whether a claim is now supported. Evidence status
    depends on the passages of every eligible source, and a sealed package keeps
    only the passage that matched each claim, not the corpus. Re-deciding support
    needs a live run. Reporting a support count from here would be an invention,
    so this command reports the labels and says so.
    """
    async with get_sessionmaker()() as session:
        package = await session.get(ResearchPackage, uuid.UUID(args.id))
        if package is None:
            _emit({"error": "not found"})
            return EXIT_ERROR

        keyword = await session.get(SeedKeyword, package.keyword_id)
        profile = load_profile(
            (await session.get(Vertical, keyword.vertical_id)).code)

        def label(value) -> str:
            """`ClaimRequirements` mixes enum members and plain strings."""
            return getattr(value, "value", value)

        changed: list[dict] = []
        before_risk: dict[str, int] = {}
        after_risk: dict[str, int] = {}
        before_category: dict[str, int] = {}
        after_category: dict[str, int] = {}

        for fact in package.facts or []:
            text = fact.get("claim") or ""
            if not text:
                continue
            stored_category = fact.get("category")
            stored_risk = fact.get("claim_risk")
            stored_region = fact.get("claim_region") or fact.get("region")

            requirements = requirements_for(text, profile)
            region = detect_region(text).region
            category, risk = label(requirements.category), label(requirements.risk)

            before_risk[str(stored_risk)] = before_risk.get(str(stored_risk), 0) + 1
            after_risk[risk] = after_risk.get(risk, 0) + 1
            before_category[str(stored_category)] = \
                before_category.get(str(stored_category), 0) + 1
            after_category[category] = after_category.get(category, 0) + 1

            if (category != stored_category or risk != stored_risk
                    or (stored_region and region.value != stored_region)):
                changed.append({
                    "claim": text[:160],
                    "category": {"before": stored_category, "after": category},
                    "risk": {"before": stored_risk, "after": risk},
                    "region": {"before": stored_region, "after": region.value},
                    "min_corroborating_sources":
                        requirements.min_corroborating_sources,
                    "authority": label(requirements.authority),
                    "evidence_status_when_sealed": fact.get("evidence_status"),
                })

        _emit({
            "package_id": str(package.id), "query": package.query,
            "claims": len(package.facts or []),
            "reclassified": len(changed),
            "risk": {"before": before_risk, "after": after_risk},
            "category": {"before": before_category, "after": after_category},
            "changed": changed,
            "note": ("Labels only. Evidence status cannot be recomputed from a "
                     "sealed package — it needs the full passage corpus, which "
                     "is not kept. Run the pipeline to re-decide support."),
        })
    return EXIT_OK


async def cmd_serp_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        snapshot = await session.get(SerpSnapshotRow, uuid.UUID(args.id))
        if snapshot is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        results = (await session.execute(
            select(SerpResultRow)
            .where(SerpResultRow.serp_snapshot_id == snapshot.id)
            .order_by(SerpResultRow.rank_absolute))).scalars().all()
        questions = (await session.execute(
            select(SerpQuestionRow).where(
                SerpQuestionRow.serp_snapshot_id == snapshot.id))).scalars().all()
        _emit({
            "id": str(snapshot.id), "query": snapshot.query,
            "location": snapshot.location_name, "language": snapshot.language_code,
            "device": snapshot.device,
            "retrieved_at": snapshot.retrieved_at.isoformat(),
            "organic_count": snapshot.organic_count,
            "provider_cost_usd": snapshot.provider_cost_usd,
            "analysis": snapshot.analysis,
            "organic": [{"rank": r.rank_group or r.rank_absolute,
                         "domain": r.domain, "title": r.title, "url": r.url}
                        for r in results],
            "questions": [{"kind": q.kind, "text": q.text} for q in questions],
        })
    return EXIT_OK


async def cmd_opportunity_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        opportunity = await session.get(SeoOpportunity, uuid.UUID(args.id))
        if opportunity is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        _emit({
            "id": str(opportunity.id), "overall_score": opportunity.overall_score,
            "confidence": opportunity.confidence,
            "version": opportunity.score_version,
            "components": opportunity.components,
            "missing_inputs": opportunity.missing_inputs,
        })
    return EXIT_OK


async def cmd_usage_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        rows = (await session.execute(
            select(ProviderUsage).where(
                ProviderUsage.correlation_id == args.correlation_id[:64])
        )).scalars().all()
    known = [r.cost_usd for r in rows if r.cost_usd is not None]
    _emit({
        "correlation_id": args.correlation_id,
        "events": [{"provider": r.provider, "operation": r.operation,
                    "requests": r.requests, "units": r.units,
                    "cost_usd": r.cost_usd, "cost_is_actual": r.cost_is_actual,
                    "duration_ms": r.duration_ms} for r in rows],
        "total_cost_usd": round(sum(known), 6) if known else None,
        "unpriced_events": sum(1 for r in rows if r.cost_usd is None),
    })
    return EXIT_OK


async def cmd_package_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        package = await session.get(ResearchPackage, uuid.UUID(args.id))
        if package is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        _emit({
            "id": str(package.id), "query": package.query, "intent": package.intent,
            "market": package.market, "language": package.language,
            "confidence_summary": package.confidence_summary,
            "facts": package.facts, "sources": package.sources,
            "unresolved_questions": package.unresolved_questions,
            "provider_provenance": package.provider_provenance,
        })
    return EXIT_OK


async def cmd_brief_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        brief = await session.get(ContentBrief, uuid.UUID(args.id))
        if brief is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        _emit({
            "id": str(brief.id), "content_type": brief.content_type,
            "search_intent": brief.search_intent,
            "recommended_title": brief.recommended_title,
            "recommended_slug": brief.recommended_slug,
            "outline": brief.outline, "required_facts": brief.required_facts,
            "required_sources": brief.required_sources,
            "cautionary_claims": brief.cautionary_claims,
            "cta_strategy": brief.cta_strategy,
            "missing_information": brief.missing_information,
            "generated_by": brief.generated_by, "status": brief.status,
        })
    return EXIT_OK


async def cmd_draft_show(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        draft = await session.get(ContentDraft, uuid.UUID(args.id))
        if draft is None:
            _emit({"error": "not found"})
            return EXIT_ERROR
        reviews = (
            await session.execute(
                select(QAReview).where(QAReview.content_draft_id == draft.id))
        ).scalars().all()
        approval = (
            await session.execute(
                select(Approval).where(Approval.content_draft_id == draft.id))
        ).scalar_one_or_none()
        payload = {
            "id": str(draft.id), "title": draft.title, "status": draft.status,
            "provider": draft.provider, "model": draft.model,
            "meta_title": draft.meta_title,
            "meta_description": draft.meta_description,
            "usage": draft.usage, "latency_ms": draft.latency_ms,
            "qa": [{"type": r.qa_type, "status": r.status, "score": r.score,
                    "blocking_issues": r.blocking_issues, "findings": r.findings}
                   for r in reviews],
            "approval_state": approval.state if approval else None,
        }
        if args.body:
            payload["body"] = draft.body
        _emit(payload)
    return EXIT_OK


async def cmd_content_pending(args: argparse.Namespace) -> int:
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(ContentDraft, Approval)
                .join(Approval, Approval.content_draft_id == ContentDraft.id)
                .where(Approval.state.in_([ApprovalState.PENDING.value,
                                           ApprovalState.NEEDS_REVISION.value]))
                .order_by(ContentDraft.created_at.desc()).limit(100)
            )
        ).all()
    _emit({"pending": [
        {"draft_id": str(d.id), "title": d.title, "draft_status": d.status,
         "approval_state": a.state} for d, a in rows
    ]})
    return EXIT_OK


async def _decide(draft_id: str, target: ApprovalState, by: str,
                  note: str | None) -> int:
    async with get_sessionmaker()() as session:
        approval = (
            await session.execute(
                select(Approval).where(
                    Approval.content_draft_id == uuid.UUID(draft_id)))
        ).scalar_one_or_none()
        if approval is None:
            _emit({"error": "no approval record for this draft"})
            return EXIT_ERROR

        current = ApprovalState(approval.state)
        try:
            approval_service.assert_transition(current, target)
        except approval_service.InvalidTransition as exc:
            _emit({"error": "INVALID_TRANSITION", "detail": str(exc),
                   "current_state": current.value})
            return EXIT_ERROR

        approval.state = target.value
        approval.decided_by = by
        approval.decided_at = datetime.now(timezone.utc)
        approval.note = note
        draft = await session.get(ContentDraft, uuid.UUID(draft_id))
        if draft is not None:
            draft.status = approval_service.draft_status_for(target).value
        await session.commit()

        _emit({"draft_id": draft_id, "approval_state": target.value,
               "decided_by": by,
               "publishable": approval_service.is_publishable(target)})
    return EXIT_OK


async def cmd_approve(args: argparse.Namespace) -> int:
    return await _decide(args.id, ApprovalState.APPROVED, args.by, args.note)


async def cmd_reject(args: argparse.Namespace) -> int:
    return await _decide(args.id, ApprovalState.REJECTED, args.by, args.note)


async def cmd_request_revision(args: argparse.Namespace) -> int:
    return await _decide(args.id, ApprovalState.NEEDS_REVISION, args.by, args.note)


# ─── Site and publication ────────────────────────────────────────────────────

async def _resolve_site(session, config):
    """The `site` row backing a site config, or None.

    Named after the site_id rather than the brand, because the brand is a
    placeholder that will change and the site_id is the stable key.
    """
    vertical = (await session.execute(
        select(Vertical).where(Vertical.code == config.vertical)
    )).scalar_one_or_none()
    if vertical is None:
        return None
    return (await session.execute(
        select(Site).where(Site.vertical_id == vertical.id,
                           Site.name == config.site_id)
    )).scalar_one_or_none()


async def cmd_site_seed(args: argparse.Namespace) -> int:
    """Create the `site` row for a site config. Idempotent."""
    from app.site.config import load_site

    config = load_site(args.site)
    async with get_sessionmaker()() as session:
        vertical = (await session.execute(
            select(Vertical).where(Vertical.code == config.vertical)
        )).scalar_one_or_none()
        if vertical is None:
            _emit({"error": f"vertical {config.vertical} is not seeded; "
                            f"run `seolead seed --vertical {config.vertical}`"})
            return EXIT_ERROR

        site = await _resolve_site(session, config)
        created = site is None
        if created:
            site = Site(vertical_id=vertical.id, name=config.site_id,
                        domain=config.domain, market=config.market,
                        default_language=config.default_language,
                        status="PLANNED" if config.staging else "ACTIVE")
            session.add(site)
            await session.commit()
    _emit({"site_id": config.site_id, "row_id": str(site.id), "created": created,
           "staging": config.staging, "indexable": config.is_indexable})
    return EXIT_OK


async def cmd_site_list(args: argparse.Namespace) -> int:
    from app.site.config import available_sites, load_site

    sites = []
    for site_id in available_sites():
        config = load_site(site_id)
        sites.append({"site_id": config.site_id, "vertical": config.vertical,
                      "brand_name": config.brand_name,
                      "brand_is_placeholder": config.brand_name_is_placeholder,
                      "domain": config.domain, "staging": config.staging,
                      "indexable": config.is_indexable,
                      "languages": config.supported_languages})
    _emit({"sites": sites})
    return EXIT_OK


async def cmd_site_preview(args: argparse.Namespace) -> int:
    """Render the DTO the staging site would receive for one slug."""
    from app.site.config import load_site
    from app.site.publication import to_dto

    config = load_site(args.site)
    locale = args.locale or config.default_language
    async with get_sessionmaker()() as session:
        site = await _resolve_site(session, config)
        if site is None:
            _emit({"error": f"site {config.site_id} is not seeded"})
            return EXIT_ERROR
        row = (await session.execute(
            select(PublishedContent).where(
                PublishedContent.site_id == site.id,
                PublishedContent.locale == locale,
                PublishedContent.slug == args.slug)
            .order_by(PublishedContent.version.desc())
        )).scalars().first()
    if row is None:
        _emit({"error": f"no content at {locale}/{args.slug}"})
        return EXIT_ERROR
    _emit(to_dto(row, config))
    return EXIT_OK


async def cmd_site_preview_draft(args: argparse.Namespace) -> int:
    """Render an unapproved draft for review. Writes nothing."""
    from app.site.config import load_site
    from app.site.publication import draft_preview_dto, evaluate_gate

    config = load_site(args.site)
    async with get_sessionmaker()() as session:
        draft = (await session.execute(
            select(ContentDraft).where(ContentDraft.id == uuid.UUID(args.draft_id))
        )).scalar_one_or_none()
        if draft is None:
            _emit({"error": "no such draft"})
            return EXIT_ERROR
        brief = (await session.execute(
            select(ContentBrief).where(ContentBrief.id == draft.content_brief_id)
        )).scalar_one()
        gate = await evaluate_gate(session, draft)
        payload = draft_preview_dto(draft, brief, config, gate)
    _emit(payload)
    return EXIT_OK


async def cmd_content_list(args: argparse.Namespace) -> int:
    """Drafts by approval state, with the publication gate evaluated."""
    from app.site.publication import evaluate_gate

    target = (args.status or "APPROVED").upper()
    async with get_sessionmaker()() as session:
        rows = (await session.execute(
            select(ContentDraft, Approval)
            .join(Approval, Approval.content_draft_id == ContentDraft.id)
            .where(Approval.state == target)
            .order_by(ContentDraft.created_at.desc()).limit(100)
        )).all()
        items = []
        for draft, approval in rows:
            gate = await evaluate_gate(session, draft)
            items.append({"draft_id": str(draft.id), "title": draft.title,
                          "approval_state": approval.state,
                          "words": len((draft.body or "").split()),
                          "gate": gate.as_dict()})
    _emit({"status": target, "items": items})
    return EXIT_OK


async def cmd_content_stage(args: argparse.Namespace) -> int:
    """Create a STAGED snapshot. Refuses unless every precondition holds."""
    from app.site.config import load_site
    from app.site.publication import PublicationRefused, stage_content

    config = load_site(args.site)
    async with get_sessionmaker()() as session:
        draft = (await session.execute(
            select(ContentDraft).where(ContentDraft.id == uuid.UUID(args.draft_id))
        )).scalar_one_or_none()
        if draft is None:
            _emit({"error": "no such draft"})
            return EXIT_ERROR
        brief = (await session.execute(
            select(ContentBrief).where(ContentBrief.id == draft.content_brief_id)
        )).scalar_one_or_none()
        site = await _resolve_site(session, config)
        if site is None:
            _emit({"error": f"site {config.site_id} is not seeded"})
            return EXIT_ERROR
        try:
            snapshot = await stage_content(
                session, draft=draft, brief=brief, site=site, config=config,
                locale=args.locale, slug=args.slug)
        except PublicationRefused as exc:
            _emit({"staged": False, "refused": exc.detail})
            return EXIT_ERROR
        await session.commit()
        payload = {"staged": True, "content_id": str(snapshot.id),
                   "slug": snapshot.slug, "locale": snapshot.locale,
                   "version": snapshot.version, "state": snapshot.state,
                   "noindex": snapshot.noindex,
                   "preview_path": f"/preview{snapshot.canonical_path}"}
    _emit(payload)
    return EXIT_OK


async def cmd_content_publish(args: argparse.Namespace) -> int:
    """Take a staged snapshot live. Refuses while the site is staging."""
    from app.site.config import load_site
    from app.site.publication import PublicationRefused, publish_content

    config = load_site(args.site)
    async with get_sessionmaker()() as session:
        row = (await session.execute(
            select(PublishedContent).where(
                PublishedContent.id == uuid.UUID(args.content_id))
        )).scalar_one_or_none()
        if row is None:
            _emit({"error": "no such published content"})
            return EXIT_ERROR
        try:
            await publish_content(session, snapshot=row, config=config)
        except PublicationRefused as exc:
            _emit({"published": False, "refused": exc.detail})
            return EXIT_ERROR
        await session.commit()
        payload = {"published": True, "content_id": str(row.id),
                   "state": row.state}
    _emit(payload)
    return EXIT_OK


async def cmd_leads_list(args: argparse.Namespace) -> int:
    """Captured leads. Contact details are shown masked.

    An operator listing leads wants counts, states and attribution; the full email
    and phone are one `leads show` away and do not belong in a command that is run
    casually and pasted into a terminal log.
    """
    target = (args.status or "").upper()
    async with get_sessionmaker()() as session:
        query = select(CapturedLead, LeadAttribution).outerjoin(
            LeadAttribution,
            LeadAttribution.captured_lead_id == CapturedLead.id)
        if target:
            query = query.where(CapturedLead.state == target)
        rows = (await session.execute(
            query.order_by(CapturedLead.created_at.desc()).limit(200))).all()
        items = [{
            "lead_id": str(lead.id), "state": lead.state,
            "conversion_type": lead.conversion_type,
            "email": _mask_email(lead.email),
            "has_phone": bool(lead.phone), "postcode": lead.postcode,
            "language": lead.language, "destination": lead.export_destination,
            "consent_marketing": lead.consent_marketing,
            "consent_version": lead.consent_version,
            "created_at": lead.created_at,
            "attribution": None if attribution is None else {
                "landing_path": attribution.landing_path,
                "page_path": attribution.page_path,
                "channel": attribution.channel, "source": attribution.source,
                "utm_source": attribution.utm_source,
                "utm_medium": attribution.utm_medium,
                "utm_campaign": attribution.utm_campaign,
                "cta": attribution.cta,
                "search_intent": attribution.search_intent,
            }} for lead, attribution in rows]
    _emit({"status": target or "ALL", "count": len(items), "leads": items})
    return EXIT_OK



async def cmd_leads_export(args: argparse.Namespace) -> int:
    """Déposer les leads en attente chez Prospect 360 — TR-SL-01.

    Le mécanisme d'exécution est cette commande, pas un ordonnanceur : le dépôt
    n'a pas d'autre planificateur, et en inventer un ici serait un second cadre
    à maintenir pour un besoin qu'un cron couvre.

    Sans producteur configuré, la commande le DIT et ne touche à rien. C'est
    l'état de la production aujourd'hui, et il doit rester sûr.
    """
    settings = get_settings()
    if not settings.prospect360_configured:
        _emit({"status": "NOT_CONFIGURED",
               "detail": "PROSPECT360_INGEST_URL and PROSPECT360_CREDENTIAL "
                         "are both required; nothing was attempted"})
        return EXIT_OK

    from app.services import lead_export
    from app.site.config import load_site
    from app.site.prospect360_destination import Prospect360Destination

    config = load_site("solar_be")
    destination = Prospect360Destination(settings)
    resultats = []
    async with get_sessionmaker()() as session:
        attente = await lead_export.leads_a_exporter(
            session, vertical_code="SOLAR_BE", limit=int(args.limit or 50))
        if args.dry_run:
            _emit({"status": "DRY_RUN", "pending": len(attente),
                   "lead_ids": [str(l.id) for l in attente]})
            return EXIT_OK
        for lead in attente:
            r = await lead_export.exporter_lead(
                session, lead, destination=destination, config=config,
                max_attempts=settings.prospect360_max_attempts)
            # Ni courriel, ni téléphone, ni charge : un opérateur veut savoir
            # ce qui est parti et ce qui coince.
            resultats.append({"lead_id": r.lead_id,
                              "external_correlation_id": r.correlation_id,
                              "outcome": r.resultat, "state": r.etat,
                              "http_status": r.http_status})
    _emit({"status": "DONE", "attempted": len(resultats), "results": resultats})
    return EXIT_OK


def _mask_email(email: str) -> str:
    local, _, domain = (email or "").partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}***@{domain}" if domain else "***"


async def cmd_health(args: argparse.Namespace) -> int:
    settings = get_settings()
    runner = await Last30DaysProvider(settings).health()
    database = {"ok": False}
    try:
        from sqlalchemy import text
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        database = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        database = {"ok": False, "error": type(exc).__name__}

    _emit({
        "database": database,
        "research_provider": runner,
        "llm_configured": settings.llm_configured,
        "internal_api_protected": settings.internal_api_protected,
        "vertical_profiles": available_profiles(),
    })
    return EXIT_OK if database["ok"] else EXIT_ERROR


# ─── Parser ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="seolead",
                                     description="SEO Lead Factory operator CLI")
    sub = parser.add_subparsers(dest="group", required=True)

    seed = sub.add_parser("seed", help="seed verticals and placeholder sites")
    seed.add_argument("--vertical", action="append",
                      help="vertical code (repeatable); default SOLAR_BE")
    seed.set_defaults(func=cmd_seed)

    research = sub.add_parser("research", help="research commands")
    research_sub = research.add_subparsers(dest="action", required=True)
    run = research_sub.add_parser("run", help="run the pipeline for a seed query")
    run.add_argument("--vertical", required=True)
    run.add_argument("--query", required=True)
    run.add_argument("--market")
    run.add_argument("--language")
    run.add_argument("--stop-after", dest="stop_after",
                     choices=["package", "brief"],
                     help="stop early (useful without an LLM credential)")
    run.add_argument("--no-authoritative", dest="authoritative",
                     action="store_false", default=True,
                     help="skip the targeted official-domain research pass")
    run.add_argument("--engine", choices=["v1", "v2"], default="v2",
                     help="v2 = SERP + relevance gate (default); v1 = Phase 2 path")
    run.add_argument("--device", choices=["desktop", "mobile"], default="desktop")
    run.add_argument("--force-refresh", dest="force_refresh", action="store_true",
                     help="bypass the freshness cache and pay for fresh research")
    community = run.add_mutually_exclusive_group()
    community.add_argument("--community", dest="force_community",
                           action="store_true", default=None,
                           help="force community research on for this job")
    community.add_argument("--no-community", dest="force_community",
                           action="store_false",
                           help="force community research off for this job")
    run.set_defaults(func=cmd_research_run)

    authoritative = research_sub.add_parser(
        "authoritative-run",
        help="execute targeted official-domain research for a package")
    authoritative.add_argument("--package", dest="package_id", required=True)
    authoritative.add_argument("--plan-only", action="store_true",
                               help="show the plan without spending on queries")
    authoritative.set_defaults(func=cmd_authoritative_run)

    package = sub.add_parser("package", help="research package commands")
    package_sub = package.add_subparsers(dest="action", required=True)
    package_show = package_sub.add_parser("show")
    package_show.add_argument("id")
    package_show.set_defaults(func=cmd_package_show)
    package_rejected = package_sub.add_parser(
        "rejected", help="sources the relevance gate excluded, and why")
    package_rejected.add_argument("id")
    package_rejected.set_defaults(func=cmd_package_rejected)
    package_replay = package_sub.add_parser(
        "replay", help="re-classify a sealed package's claims under the current "
                       "policy — read-only, no provider call")
    package_replay.add_argument("id")
    package_replay.set_defaults(func=cmd_package_replay)

    serp = sub.add_parser("serp", help="SERP snapshots")
    serp_sub = serp.add_subparsers(dest="action", required=True)
    serp_show = serp_sub.add_parser("show")
    serp_show.add_argument("id")
    serp_show.set_defaults(func=cmd_serp_show)

    opportunity = sub.add_parser("opportunity", help="SEO opportunity scores")
    opportunity_sub = opportunity.add_subparsers(dest="action", required=True)
    opportunity_show = opportunity_sub.add_parser("show")
    opportunity_show.add_argument("id")
    opportunity_show.set_defaults(func=cmd_opportunity_show)

    usage = sub.add_parser("usage", help="provider usage and cost for a job")
    usage.add_argument("correlation_id")
    usage.set_defaults(func=cmd_usage_show)

    credentials = sub.add_parser(
        "credentials", help="report CONFIGURED / NOT_CONFIGURED per provider")
    credentials.set_defaults(func=cmd_credentials)

    brief = sub.add_parser("brief", help="content brief commands")
    brief_sub = brief.add_subparsers(dest="action", required=True)
    brief_show = brief_sub.add_parser("show")
    brief_show.add_argument("id")
    brief_show.set_defaults(func=cmd_brief_show)

    draft = sub.add_parser("draft", help="draft commands")
    draft_sub = draft.add_subparsers(dest="action", required=True)
    draft_show = draft_sub.add_parser("show")
    draft_show.add_argument("id")
    draft_show.add_argument("--body", action="store_true", help="include the body")
    draft_show.set_defaults(func=cmd_draft_show)

    content = sub.add_parser("content", help="approval workflow")
    content_sub = content.add_subparsers(dest="action", required=True)

    pending = content_sub.add_parser("pending", help="drafts awaiting a decision")
    pending.set_defaults(func=cmd_content_pending)

    for name, func in (("approve", cmd_approve), ("reject", cmd_reject),
                       ("request-revision", cmd_request_revision)):
        cmd = content_sub.add_parser(name)
        cmd.add_argument("id")
        cmd.add_argument("--by", required=True, help="who is deciding (recorded)")
        cmd.add_argument("--note")
        cmd.set_defaults(func=func)

    # ── Site and publication ────────────────────────────────────────────────
    site_cmd = sub.add_parser("site", help="site configuration and preview")
    site_sub = site_cmd.add_subparsers(dest="site_command", required=True)

    site_seed = site_sub.add_parser("seed", help="create the site row")
    site_seed.add_argument("--site", default="solar_be")
    site_seed.set_defaults(func=cmd_site_seed)

    site_list = site_sub.add_parser("list", help="configured sites")
    site_list.set_defaults(func=cmd_site_list)

    site_preview = site_sub.add_parser(
        "preview", help="render the DTO the site would receive for one slug")
    site_preview.add_argument("slug")
    site_preview.add_argument("--site", default="solar_be")
    site_preview.add_argument("--locale", default=None)
    site_preview.set_defaults(func=cmd_site_preview)

    draft_preview = site_sub.add_parser(
        "preview-draft", help="review an unapproved draft without staging it")
    draft_preview.add_argument("draft_id")
    draft_preview.add_argument("--site", default="solar_be")
    draft_preview.set_defaults(func=cmd_site_preview_draft)

    content_list = content_sub.add_parser(
        "list", help="drafts by approval state, with the publication gate")
    content_list.add_argument("--status", default="APPROVED")
    content_list.set_defaults(func=cmd_content_list)

    content_stage = content_sub.add_parser(
        "stage", help="create a staged snapshot from an approved draft")
    content_stage.add_argument("draft_id")
    content_stage.add_argument("--site", default="solar_be")
    content_stage.add_argument("--locale", default=None)
    content_stage.add_argument("--slug", default=None)
    content_stage.set_defaults(func=cmd_content_stage)

    content_publish = content_sub.add_parser(
        "publish", help="take a staged snapshot live")
    content_publish.add_argument("content_id")
    content_publish.add_argument("--site", default="solar_be")
    content_publish.set_defaults(func=cmd_content_publish)

    leads = sub.add_parser("leads", help="captured leads")
    leads_sub = leads.add_subparsers(dest="leads_command", required=True)
    leads_list = leads_sub.add_parser("list")
    leads_list.add_argument("--status", default="")
    leads_list.set_defaults(func=cmd_leads_list)
    leads_export = leads_sub.add_parser("export")
    leads_export.add_argument("--limit", default=50)
    leads_export.add_argument("--dry-run", action="store_true")
    leads_export.set_defaults(func=cmd_leads_export)

    health_cmd = sub.add_parser("health", help="check dependencies")
    health_cmd.set_defaults(func=cmd_health)

    return parser


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = build_parser().parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
