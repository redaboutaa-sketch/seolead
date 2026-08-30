"""DUPLICATE_TITLE — what a new draft may actually cannibalise.

The guard is real: two pages of one site competing for the same query split
their own ranking. But cannibalisation needs two URLs, and two drafts of one
seed keyword never have two — the slug comes from the keyword.

On 2026-08-30 the guard fired on the pipeline itself. Three drafts for
`rentabilité panneaux solaires Belgique`, identical titles, all undecided, each
blocking the next. Two paid runs went into discovering that.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.enums import ContentStatus
from app.models import (ContentBrief, ContentDraft, ResearchPackage,
                        ResearchRun, SeedKeyword, Vertical)
from app.services.title_registry import competing_titles
from app.verticals.profile import load_profile

pytestmark = pytest.mark.asyncio

TITLE = "Guide Complet sur la Rentabilité des Panneaux Solaires en Belgique"


async def _vertical(session) -> Vertical:
    profile = load_profile("SOLAR_BE")
    vertical = Vertical(code=profile.code, name=profile.name,
                        market=profile.market,
                        default_language=profile.default_language, active=True)
    session.add(vertical)
    await session.flush()
    return vertical


async def _draft(session, vertical, *, query: str, title: str,
                 status: str = ContentStatus.QA_FAILED.value) -> ContentDraft:
    keyword = (await session.execute(
        __import__("sqlalchemy").select(SeedKeyword).where(
            SeedKeyword.normalized_query == query)
    )).scalar_one_or_none()
    if keyword is None:
        keyword = SeedKeyword(vertical_id=vertical.id, query=query,
                              normalized_query=query, language="fr",
                              market="BE", status="RESEARCHED")
        session.add(keyword)
        await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily",
                      status="SUCCEEDED", idempotency_key=uuid.uuid4().hex,
                      correlation_id="t")
    session.add(run)
    await session.flush()
    package = ResearchPackage(keyword_id=keyword.id, research_run_id=run.id,
                              query=query, market="BE", language="fr",
                              intent="INFORMATIONAL")
    session.add(package)
    await session.flush()
    brief = ContentBrief(research_package_id=package.id, content_type="GUIDE",
                         primary_query=query, search_intent="INFORMATIONAL",
                         target_audience="a", objective="o",
                         recommended_title=title, recommended_slug="s")
    session.add(brief)
    await session.flush()
    draft = ContentDraft(content_brief_id=brief.id, provider="stub", model="m",
                         title=title, body="b", status=status)
    session.add(draft)
    await session.commit()
    return draft


class TestSameKeywordDoesNotCollide:
    async def test_a_rerun_no_longer_collides_with_its_own_predecessor(self,
                                                                       session):
        """The live deadlock of 2026-08-30, in three lines."""
        vertical = await _vertical(session)
        await _draft(session, vertical, query="rentabilite panneaux solaires belgique",
                     title=TITLE)
        replacement = await _draft(
            session, vertical, query="rentabilite panneaux solaires belgique",
            title=TITLE)
        assert await competing_titles(session, replacement) == []

    async def test_three_undecided_drafts_of_one_keyword_still_do_not_collide(
            self, session):
        """The state `content pending` actually showed."""
        vertical = await _vertical(session)
        for _ in range(2):
            await _draft(session, vertical,
                         query="rentabilite panneaux solaires belgique",
                         title=TITLE)
        newest = await _draft(session, vertical,
                              query="rentabilite panneaux solaires belgique",
                              title=TITLE)
        assert await competing_titles(session, newest) == []

    async def test_an_approved_predecessor_of_the_same_keyword_does_not_block(
            self, session):
        """APPROVED is terminal, so this draft can never be disposed of.

        Under the old rule it would have reserved its title forever, and no
        replacement for its own keyword could ever be published.
        """
        vertical = await _vertical(session)
        await _draft(session, vertical,
                     query="rentabilite panneaux solaires belgique", title=TITLE,
                     status=ContentStatus.APPROVED.value)
        replacement = await _draft(
            session, vertical, query="rentabilite panneaux solaires belgique",
            title=TITLE)
        assert await competing_titles(session, replacement) == []


class TestAnotherKeywordStillCollides:
    async def test_a_different_keyword_with_the_same_title_still_blocks(self,
                                                                        session):
        """The cannibalisation the guard exists for: two queries, one page."""
        vertical = await _vertical(session)
        await _draft(session, vertical, query="prix panneaux solaires belgique",
                     title=TITLE)
        newcomer = await _draft(
            session, vertical, query="rentabilite panneaux solaires belgique",
            title=TITLE)
        assert await competing_titles(session, newcomer) == [TITLE]

    async def test_a_rejected_draft_of_another_keyword_is_still_excluded(self,
                                                                         session):
        """REJECTED is terminal — it can never reach publication (PR #12)."""
        vertical = await _vertical(session)
        await _draft(session, vertical, query="prix panneaux solaires belgique",
                     title=TITLE, status=ContentStatus.REJECTED.value)
        newcomer = await _draft(
            session, vertical, query="rentabilite panneaux solaires belgique",
            title=TITLE)
        assert await competing_titles(session, newcomer) == []

    async def test_an_unrelated_title_never_appears(self, session):
        vertical = await _vertical(session)
        await _draft(session, vertical, query="prix panneaux solaires belgique",
                     title="Combien coûte une installation solaire")
        newcomer = await _draft(
            session, vertical, query="rentabilite panneaux solaires belgique",
            title=TITLE)
        assert await competing_titles(session, newcomer) == [
            "Combien coûte une installation solaire"]
