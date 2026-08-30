"""`draft rejudge` — put a stored draft back through the gates, for nothing.

The gates changed after draft 8a1f6e46 was produced. Asking what the same draft
costs today must not mean buying its research again: the SERP, the sources and
the model call are already paid for, and re-running them would also change the
subject. So the command reads the sealed draft, brief and package, and re-runs
the two deterministic gates over them — nothing bought, nothing written.
"""
from __future__ import annotations

import argparse
import uuid

import pytest
from sqlalchemy import select

from app.cli import cmd_qa_rejudge
from app.core.enums import QAType
from app.models import (ContentBrief, ContentDraft, QAReview, ResearchPackage,
                        ResearchRun, SeedKeyword, Vertical)
from app.verticals.profile import load_profile

pytestmark = pytest.mark.asyncio


SUPPORTED = ("La prime régionale atteint 1500 euros pour une installation "
             "résidentielle.")
UNSUPPORTED = ("La prime régionale atteint 1500 euros pour une installation "
               "photovoltaïque.")

FACTS = [
    {"claim": SUPPORTED, "category": "SUBSIDY", "claim_risk": "HIGH",
     "evidence_status": "SUPPORTED", "region": "BE", "reason": "official"},
    {"claim": UNSUPPORTED, "category": "SUBSIDY", "claim_risk": "HIGH",
     "evidence_status": "UNSUPPORTED", "region": "BE", "reason": "no source"},
]


async def _sealed_draft(session, *, body: str, stored_blocking: list[dict]):
    profile = load_profile("SOLAR_BE")
    vertical = Vertical(code=profile.code, name=profile.name,
                        market=profile.market,
                        default_language=profile.default_language, active=True)
    session.add(vertical)
    await session.flush()
    keyword = SeedKeyword(vertical_id=vertical.id,
                          query="prime panneaux solaires belgique",
                          normalized_query="prime panneaux solaires belgique",
                          language="fr", market="BE", status="RESEARCHED")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily",
                      status="SUCCEEDED", idempotency_key=uuid.uuid4().hex,
                      correlation_id="t")
    session.add(run)
    await session.flush()
    package = ResearchPackage(keyword_id=keyword.id, research_run_id=run.id,
                              query=keyword.query, market="BE", language="fr",
                              intent="COMMERCIAL", facts=FACTS)
    session.add(package)
    await session.flush()
    brief = ContentBrief(
        research_package_id=package.id, content_type="ARTICLE",
        primary_query=keyword.query, search_intent="COMMERCIAL",
        target_audience="propriétaires", objective="informer",
        recommended_title="Prime panneaux solaires",
        recommended_slug="prime-panneaux-solaires",
        required_facts=[{"fact": SUPPORTED, "source_ref": "s1"}],
        required_sources=[{"url": "https://energie.wallonie.be/a"}])
    session.add(brief)
    await session.flush()
    draft = ContentDraft(content_brief_id=brief.id, provider="openai",
                         model="gpt-4o-mini", title="Prime panneaux solaires",
                         body=body, meta_title="Prime panneaux solaires",
                         meta_description="Ce que vaut la prime.",
                         status="QA_FAILED")
    session.add(draft)
    await session.flush()
    session.add(QAReview(content_draft_id=draft.id,
                         qa_type=QAType.DETERMINISTIC.value, layer="FACTUAL",
                         status="FAILED", score=100, findings=stored_blocking,
                         blocking_issues=stored_blocking))
    await session.commit()
    return draft, package


@pytest.fixture
def rejudge(monkeypatch, session):
    import app.cli as cli

    class _Maker:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *exc):
                    return False
            return _Ctx()

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _Maker())
    captured: list[dict] = []
    monkeypatch.setattr(cli, "_emit", lambda payload: captured.append(payload))

    async def _run(draft_id: str, *, explain: bool = False,
                   apply: bool = False,
                   reason: str | None = None) -> tuple[int, dict]:
        code = await cmd_qa_rejudge(argparse.Namespace(
            id=draft_id, explain=explain, apply=apply, reason=reason))
        return code, captured[-1]

    return _run


OLD_FINDING = {"code": "HIGH_RISK_CLAIM_ASSERTED",
               "message": "the draft asserts a HIGH-risk SUBSIDY claim",
               "blocking": True, "detail": UNSUPPORTED}


class TestRejudge:
    async def test_it_reports_the_new_blocking_count_beside_the_old_one(
            self, session, rejudge):
        """The whole point: what this draft costs at the gate today.

        The body restates the SUPPORTED claim. Under the matcher as it was, it
        was blocked for the unsupported twin it also resembles; the stored review
        is kept so the two counts can be read side by side.
        """
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        code, report = await rejudge(str(draft.id))

        assert report["when_sealed"][0]["blocking"] == 1
        assert report["when_sealed"][0]["blocking_codes"] == {
            "HIGH_RISK_CLAIM_ASSERTED": 1}
        factual = next(g for g in report["now"] if g["gate"] == "FACTUAL")
        assert factual["blocking"] == 0
        assert factual["blocking_codes"] == {}

    async def test_a_draft_that_really_asserts_it_is_still_blocked(
            self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=UNSUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        code, report = await rejudge(str(draft.id))
        factual = next(g for g in report["now"] if g["gate"] == "FACTUAL")
        assert factual["blocking_codes"]["HIGH_RISK_CLAIM_ASSERTED"] == 1
        assert report["blocking_total"] >= 1
        assert code != 0, "a blocked draft must not report success"

    async def test_every_blocking_finding_is_named(self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=UNSUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id))
        assert len(report["blocking_detail"]) == report["blocking_total"]
        assert all({"gate", "code", "message"} <= set(f)
                   for f in report["blocking_detail"])

    async def test_it_writes_nothing(self, session, rejudge):
        """A re-judgement that rewrites its subject is not a measurement."""
        draft, package = await _sealed_draft(session, body=UNSUPPORTED,
                                             stored_blocking=[OLD_FINDING])
        before = (draft.status, draft.body, len(package.facts))
        await rejudge(str(draft.id))
        await session.refresh(draft)
        await session.refresh(package)
        assert (draft.status, draft.body, len(package.facts)) == before
        reviews = (await session.execute(
            QAReview.__table__.select().where(
                QAReview.__table__.c.content_draft_id == draft.id))).all()
        assert len(reviews) == 1, "no QA row may be added by a re-judgement"

    async def test_an_unknown_draft_is_an_error_not_a_crash(self, session,
                                                            rejudge):
        code, report = await rejudge(str(uuid.uuid4()))
        assert code != 0
        assert report == {"error": "not found"}


class TestExplain:
    """Off by default, because a count is what the command is usually asked for.

    On, it answers the question the count cannot: whether the arbitration is
    still deciding anything. Read-only either way — no provider, no write.
    """

    async def test_it_is_absent_unless_asked_for(self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id))
        assert "arbitration" not in report

    async def test_it_shows_the_two_readings_and_the_gap(self, session,
                                                         rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id), explain=True)
        arbitration = report["arbitration"]
        assert arbitration["consulted"] == 1
        pair = arbitration["pairs"][0]
        assert pair["contested_claim"] and pair["supported_claim"]
        assert pair["gap"] >= 0
        assert pair["margin"] == 0.05

    async def test_it_separates_what_still_blocks_from_what_no_longer_does(
            self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=UNSUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id), explain=True)
        assert report["arbitration"]["blocks_now"] == 1

    async def test_asking_for_it_does_not_change_the_verdict(self, session,
                                                             rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, plain = await rejudge(str(draft.id))
        _, explained = await rejudge(str(draft.id), explain=True)
        assert plain["now"] == explained["now"]
        assert plain["blocking_total"] == explained["blocking_total"]


class TestApplyAppends:
    """A verdict is a dated fact: it is added, never corrected.

    The row saying draft 8a1f6e46 failed on 2026-08-30 is true of that day.
    Editing it would destroy the only evidence that the matcher ever
    misattributed anything, and would leave the trail asserting something that
    was never true — that this draft always passed.
    """

    async def _rows(self, session, draft):
        # `populate_existing`: the rows were expired by the commit inside the
        # command, and reading an expired attribute outside the greenlet is an
        # error rather than a lazy load.
        result = await session.execute(
            select(QAReview).where(QAReview.content_draft_id == draft.id)
            .execution_options(populate_existing=True))
        return result.scalars().all()

    async def test_the_sealed_verdict_survives_untouched(self, session,
                                                         rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        sealed = (await self._rows(session, draft))[0]
        before = (sealed.id, sealed.status, list(sealed.blocking_issues),
                  sealed.revision)

        await rejudge(str(draft.id), apply=True)

        kept = next(r for r in await self._rows(session, draft)
                    if r.id == before[0])
        assert (kept.id, kept.status, list(kept.blocking_issues),
                kept.revision) == before

    async def test_the_new_verdict_is_a_higher_revision(self, session,
                                                        rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id), apply=True)

        factual = next(a for a in report["applied"] if a["gate"] == "FACTUAL")
        assert factual["revision"] == 2
        assert factual["status"] == "PASSED"
        assert factual["supersedes"], "it must name what it supersedes"

        rows = [r for r in await self._rows(session, draft)
                if r.layer == "FACTUAL"]
        assert sorted(r.revision for r in rows) == [1, 2]

    async def test_it_records_what_judged_it_and_why(self, session, rejudge):
        """Provenance, or the new verdict is an unexplained reversal."""
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        await rejudge(str(draft.id), apply=True,
                      reason="matcher arbitration shipped")

        newest = max((r for r in await self._rows(session, draft)
                      if r.layer == "FACTUAL"), key=lambda r: r.revision)
        assert newest.engine_version.startswith("factual_qa_v2/arbitration-")
        assert newest.verdict_reason == "matcher arbitration shipped"
        assert newest.created_at is not None

    async def test_nothing_is_written_without_the_flag(self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        await rejudge(str(draft.id))
        assert len(await self._rows(session, draft)) == 1

    async def test_a_refusal_is_recorded_too(self, session, rejudge):
        """A verdict that still refuses is a fact with a date on it as well.

        Recording only the passes would make the trail a record of successes.
        """
        draft, _ = await _sealed_draft(session, body=UNSUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        _, report = await rejudge(str(draft.id), apply=True)
        factual = next(a for a in report["applied"] if a["gate"] == "FACTUAL")
        assert factual["status"] == "FAILED"
        assert factual["blocking"] >= 1

    async def test_a_second_application_keeps_climbing(self, session, rejudge):
        draft, _ = await _sealed_draft(session, body=SUPPORTED,
                                       stored_blocking=[OLD_FINDING])
        await rejudge(str(draft.id), apply=True)
        _, report = await rejudge(str(draft.id), apply=True)
        assert next(a for a in report["applied"]
                    if a["gate"] == "FACTUAL")["revision"] == 3
