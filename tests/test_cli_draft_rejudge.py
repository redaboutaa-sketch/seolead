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

    async def _run(draft_id: str) -> tuple[int, dict]:
        code = await cmd_qa_rejudge(argparse.Namespace(id=draft_id))
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
