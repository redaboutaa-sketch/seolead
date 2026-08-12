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
from app.models import (Approval, ContentBrief, ContentDraft, QAReview,
                        ResearchPackage, Site, Vertical)
from app.providers.llm.registry import get_llm_provider
from app.providers.research.last30days import Last30DaysProvider
from app.services import approval_service
from app.services.pipeline import run_pipeline
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
            result = await run_pipeline(
                session,
                vertical_code=args.vertical.upper(),
                query=args.query,
                market=args.market,
                language=args.language,
                research_provider=Last30DaysProvider(settings),
                llm=get_llm_provider(settings),
                stop_after=args.stop_after,
            )
        except SeoLeadError as exc:
            _emit({"error_code": exc.code, "detail": exc.detail})
            return EXIT_ERROR

    _emit(result.as_dict())
    if result.error_code:
        return EXIT_BLOCKED
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
    run.set_defaults(func=cmd_research_run)

    package = sub.add_parser("package", help="research package commands")
    package_sub = package.add_subparsers(dest="action", required=True)
    package_show = package_sub.add_parser("show")
    package_show.add_argument("id")
    package_show.set_defaults(func=cmd_package_show)

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
