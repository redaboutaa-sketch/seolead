"""The writer's stage, on its own: draft, judge, re-emit at most twice, persist.

Extracted from `pipeline_v2` on 2026-09-03 for one reason. The revision of the
payback article regenerated everything — SERP, web research, five official
searches — to obtain one more draft, and each regeneration produced a new
package on which the proposed-research resolution had to be recorded again.
The research was fine; the draft was not. This module lets an operator ask
the writer again against a package that already exists, under the same
gates, for the price of the writer's call alone.

Nothing here decides anything a person should: the outcome is a draft with
its QA rows and a PENDING approval, exactly what the pipeline produced.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalState, ContentStatus, QALayer, QAType
from app.core.errors import ErrorCode, LLMNotConfigured, SeoLeadError
from app.models import Approval, ContentBrief, ContentDraft, QAReview
from app.providers.llm.base import LLMProvider
from app.services import (draft_retry, draft_service, factual_qa_v2,
                          package_builder_v3, qa_service, title_registry)
from app.services.provider_usage import UsageRecorder
from app.site.offer import offer_for_vertical
from app.verticals.profile import VerticalProfile


@dataclass
class DraftOutcome:
    draft: ContentDraft | None = None
    attempts: list[dict] = field(default_factory=list)
    qa_review_ids: list[uuid.UUID] = field(default_factory=list)
    factual: dict = field(default_factory=dict)
    seo: dict = field(default_factory=dict)
    advisory: dict = field(default_factory=dict)
    approval: Approval | None = None
    qa_passed: bool = False
    kept_attempt: int | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "content_draft_id": str(self.draft.id) if self.draft else None,
            "kept_attempt": self.kept_attempt,
            "draft_status": self.draft.status if self.draft else None,
            "approval_id": str(self.approval.id) if self.approval else None,
            "approval_state": self.approval.state if self.approval else None,
            "qa_review_ids": [str(i) for i in self.qa_review_ids],
            "factual_qa": {"status": self.factual.get("status"),
                           "score": self.factual.get("score"),
                           "blocking": len(self.factual.get("blocking_issues", [])),
                           "blocking_codes": sorted({
                               str(f.get("code"))
                               for f in self.factual.get("blocking_issues", [])})},
            "seo_qa": {"status": self.seo.get("status"),
                       "score": self.seo.get("score"),
                       "blocking": len(self.seo.get("blocking_issues", []))},
            "advisory_qa": {"status": self.advisory.get("status"),
                            "findings": len(self.advisory.get("findings", [])),
                            "blocking": len(self.advisory.get("blocking_issues", []))},
            "draft_attempts": self.attempts,
            "qa_passed": self.qa_passed,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def choose_best(candidates: list[dict]) -> dict:
    """The attempt to keep: fewest blocking findings, then the fewest that
    no rewrite could answer, then the latest (it carried the most findings
    and is the writer's most informed answer)."""
    if not candidates:
        raise ValueError("no draft attempt to choose from")

    def key(c: dict) -> tuple[int, int, int]:
        codes = draft_retry.codes(c["blocking"])
        unanswerable = sum(1 for code in codes if code in draft_retry.NOT_RETRIABLE)
        return (len(c["blocking"]), unanswerable, -c["attempt"])

    return min(candidates, key=key)


async def write_and_judge(
    session: AsyncSession, *, brief: ContentBrief, brief_payload: dict,
    package_payload: dict, profile: VerticalProfile, llm: LLMProvider,
    usage: UsageRecorder, correlation_id: str, keyword_id: uuid.UUID,
    vertical_code: str,
) -> DraftOutcome:
    """Draft against a brief and its package, judge, persist the kept draft."""
    outcome = DraftOutcome()

    # The writer sees supported claims, unresolved facts and forbidden topics —
    # never a rejected source and never a raw page excerpt.
    writer_view = package_builder_v3.writer_payload(package_payload,
                                                    allow_partial=False)

    # The gates run here, in memory, before anything is persisted. A refused
    # draft is not a refused run: everything expensive is already bought and
    # unchanged, so what gets re-emitted is the writer's call alone, carrying
    # the findings that refused it. See `draft_retry` for what may not be
    # retried and why.
    existing_titles = await title_registry.competing_titles_for_keyword(
        session, keyword_id)
    # The first-party offer registry of this vertical's site: which figures a
    # draft may present as OUR offer. None reads as an empty registry —
    # fail-closed — never as permission.
    offer = offer_for_vertical(vertical_code)
    previous_findings: list[dict] | None = None
    candidates: list[dict] = []

    for attempt in range(1, draft_retry.MAX_ATTEMPTS + 1):
        try:
            draft_payload, llm_response = await draft_service.generate_draft(
                brief_payload, {**package_payload, "writer_view": writer_view},
                llm=llm, correlation_id=correlation_id,
                previous_findings=previous_findings)
        except (LLMNotConfigured, SeoLeadError) as exc:
            outcome.error_code = exc.code or ErrorCode.CONTENT_GENERATION_FAILED
            outcome.error_detail = exc.detail
            return outcome

        usage.record(provider=llm_response.provider, operation="draft",
                     correlation_id=correlation_id, requests=1,
                     units=llm_response.usage.total_tokens,
                     cost_usd=None, cost_is_actual=False,
                     duration_ms=llm_response.latency_ms)

        factual = factual_qa_v2.run_factual_qa_v2(draft_payload, package_payload,
                                                  profile)
        seo = qa_service.run_seo_qa_v2(draft_payload, brief_payload,
                                       package_payload, profile,
                                       existing_titles=existing_titles,
                                       offer=offer)
        blocking_now = factual["blocking_issues"] + seo["blocking_issues"]
        decision = draft_retry.decide(blocking_now, attempt=attempt)
        outcome.attempts.append({**decision.as_dict(),
                                 "factual_score": factual["score"],
                                 "seo_score": seo["score"],
                                 "provider": llm_response.provider})
        candidates.append({"attempt": attempt, "draft": draft_payload,
                           "response": llm_response, "factual": factual,
                           "seo": seo, "blocking": blocking_now})
        if not decision.retry:
            break
        previous_findings = draft_retry.carried(blocking_now)

    # ── The draft that is kept is the best one, not the last one ─────────
    # Measured 2026-09-03 (regenerate on brief 29ec0a0b): attempt 2 was one
    # SEO finding away from passing, attempt 3 collapsed (SEO 15, an
    # AMBIGUOUS_MATCH), and attempt 3 was what got persisted, because the
    # loop kept whatever it ended on. The history of every attempt still
    # rides along in DRAFT_ATTEMPTS.
    kept = choose_best(candidates)
    draft_payload, llm_response = kept["draft"], kept["response"]
    factual, seo = kept["factual"], kept["seo"]
    outcome.kept_attempt = kept["attempt"]

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
    outcome.draft = draft

    # Already judged above, once per attempt. What is persisted is the verdict
    # on the draft that was kept, plus the history of what was discarded.
    factual_row = QAReview(
        content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
        layer=QALayer.FACTUAL.value,
        status=factual["status"], score=factual["score"],
        findings=factual["findings"] + [
            {"code": "CLAIM_LEDGER", "message": "atomic claim ledger",
             "blocking": False, "detail": "",
             "ledger": factual["claim_ledger"]},
            # The discarded attempts leave no row of their own, so the count
            # and the reason live here. Without it a re-emitted run is
            # indistinguishable from a first-time pass.
            {"code": "DRAFT_ATTEMPTS",
             "message": (f"{len(outcome.attempts)} draft call(s); kept "
                         f"attempt {outcome.kept_attempt}; "
                         f"{outcome.attempts[-1]['reason']}"),
             "blocking": False, "detail": "",
             "kept_attempt": outcome.kept_attempt,
             "attempts": outcome.attempts}],
        blocking_issues=factual["blocking_issues"], revision=1,
        engine_version=factual_qa_v2.ENGINE_VERSION)
    session.add(factual_row)
    await session.flush()
    outcome.qa_review_ids.append(factual_row.id)
    outcome.factual = factual

    seo_row = QAReview(
        content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
        layer=QALayer.SEO.value, status=seo["status"], score=seo["score"],
        # Same pattern as CLAIM_LEDGER above: the offer-registry version this
        # verdict was judged against rides along as an informational entry, so
        # the row stays traceable after the registry moves on.
        findings=seo["findings"] + [
            {"code": "OFFER_REGISTRY",
             "message": (f"judged against offer registry "
                         f"{seo['offer_registry']['version']}"),
             "blocking": False, "detail": "",
             "offer_registry": seo["offer_registry"]}],
        blocking_issues=seo["blocking_issues"], revision=1,
        engine_version=qa_service.ENGINE_VERSION)
    session.add(seo_row)
    await session.flush()
    outcome.qa_review_ids.append(seo_row.id)
    outcome.seo = seo

    # The model-assisted reviewer sees what is sourced, so it can only report
    # as unsupported what the ledger does not carry.
    advisory = await qa_service.run_llm_qa(
        draft_payload, brief_payload, llm=llm, correlation_id=correlation_id,
        sourced_claims=list(writer_view.get("supported_claims") or []))
    advisory_row = QAReview(content_draft_id=draft.id,
                            qa_type=QAType.LLM_ASSISTED.value,
                            layer=QALayer.ADVISORY.value, **advisory)
    session.add(advisory_row)
    await session.flush()
    outcome.qa_review_ids.append(advisory_row.id)
    outcome.advisory = advisory

    # The model-assisted reviewer blocks on SUBSIDY, ROI and GRID_RULE at
    # severity high (2026-09-03). It said « needs more data or references »
    # about profitability without public support on draft 8a1f6e46, and the
    # draft went to approval as QA_PASSED because nothing it said counted.
    qa_passed = not (factual["blocking_issues"] or seo["blocking_issues"]
                     or advisory["blocking_issues"])
    outcome.qa_passed = qa_passed
    draft.status = (ContentStatus.QA_PASSED.value if qa_passed
                    else ContentStatus.QA_FAILED.value)

    # ── The approval gate: a PENDING row, never more ──────────────────────
    approval = Approval(content_draft_id=draft.id,
                        state=ApprovalState.PENDING.value)
    session.add(approval)
    if qa_passed:
        draft.status = ContentStatus.PENDING_APPROVAL.value
    await session.commit()
    outcome.approval = approval

    if not qa_passed:
        outcome.error_code = ErrorCode.QA_FAILED
        outcome.error_detail = (
            f"{len(factual['blocking_issues'])} factual, "
            f"{len(seo['blocking_issues'])} SEO and "
            f"{len(advisory['blocking_issues'])} model-assisted blocking issue(s)")
    return outcome
