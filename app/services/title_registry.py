"""Which existing titles a new draft may collide with.

DUPLICATE_TITLE guards against keyword cannibalisation: two pages of the same
site competing for one query, splitting their own ranking. That is a real
failure and the guard stays blocking.

But cannibalisation needs **two URLs**, and two drafts of the same seed keyword
never have two. The slug comes from the keyword — `recommended_slug =
slugify(query)`, and staging falls back to it — so every draft for
`rentabilité panneaux solaires Belgique` resolves to
`/rentabilite-panneaux-solaires-belgique`. A second draft for that keyword does
not compete with the first: it replaces it.

Comparing against every draft ever written, keyword included, made the pipeline
unrepeatable. The writer is seeded with the brief's `working_title`, so a rerun
converges on the same title and collides with its own predecessor. The live
consequence, on 2026-08-30: three drafts for one keyword, identical titles, all
undecided, each blocking the next. Two paid runs were spent discovering that the
guard was firing on the pipeline itself.

What still blocks, and must: a draft whose title matches one from a DIFFERENT
keyword. That is two queries converging on one page — the thing the guard exists
for.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ContentStatus
from app.models import ContentBrief, ContentDraft, ResearchPackage


def _keyword_of(draft_id_column):
    """Keyword behind a draft: draft → brief → package → keyword."""
    return (
        select(ResearchPackage.keyword_id)
        .join(ContentBrief,
              ContentBrief.research_package_id == ResearchPackage.id)
        .join(ContentDraft, ContentDraft.content_brief_id == ContentBrief.id)
        .where(ContentDraft.id == draft_id_column)
    )


async def competing_titles_for_keyword(session: AsyncSession, keyword_id,
                                       *, exclude_draft_id=None) -> list[str]:
    """Titles a draft of `keyword_id` could cannibalise.

    Takes the keyword rather than the draft, because the gate now runs before
    the draft is persisted: a candidate that is refused and re-emitted never
    reaches the table, and a title check that needs a row could not see it.

    Excludes REJECTED drafts — that state is terminal, so such a draft can never
    reach publication and can never compete — and every draft of this keyword,
    which shares its slug.
    """
    stmt = (
        select(ContentDraft.title)
        .join(ContentBrief, ContentBrief.id == ContentDraft.content_brief_id)
        .join(ResearchPackage,
              ResearchPackage.id == ContentBrief.research_package_id)
        .where(ContentDraft.status != ContentStatus.REJECTED.value)
        .where(ResearchPackage.keyword_id != keyword_id)
    )
    if exclude_draft_id is not None:
        stmt = stmt.where(ContentDraft.id != exclude_draft_id)
    rows = await session.execute(stmt)
    return [t for t in rows.scalars().all() if t]


async def competing_titles(session: AsyncSession,
                           draft: ContentDraft) -> list[str]:
    """The same question asked of an already-persisted draft."""
    return await competing_titles_for_keyword(
        session, _keyword_of(draft.id).scalar_subquery(),
        exclude_draft_id=draft.id)
