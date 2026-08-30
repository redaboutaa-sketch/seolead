"""Persistence and database constraints.

The constraints are the last line of defence: application code can be bypassed by
a script, a migration or a future refactor, but a CHECK constraint holds for
everyone. These tests confirm the guarantees are actually in the schema rather
than only in the services that normally write to it.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import (ApprovalState, AuthorityRequirement,
                            ClaimCategory, EvidenceStatus,
                            FreshnessRequirement, Observability,
                            SourceState)
from app.models import (Approval, ContentBrief, ContentDraft, ResearchEvidence,
                        ResearchPackage, ResearchRun, ResearchSource, SeedKeyword,
                        Site, Vertical)


async def _vertical(session) -> Vertical:
    vertical = Vertical(code="X_TEST", name="X", market="BE", default_language="fr")
    session.add(vertical)
    await session.commit()
    return vertical


async def _run(session, vertical, *, key: str = "k1") -> ResearchRun:
    keyword = SeedKeyword(vertical_id=vertical.id, query="q", normalized_query="q",
                          language="fr", market="BE")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="last30days", status="SUCCEEDED",
                      idempotency_key=key, correlation_id="c1")
    session.add(run)
    await session.commit()
    return run


class TestSiteDomain:
    async def test_domain_may_be_null(self, session):
        """Phase 2 has no domain and must not require one."""
        vertical = await _vertical(session)
        session.add(Site(vertical_id=vertical.id, name="Pilot", domain=None,
                         market="BE", default_language="fr"))
        await session.commit()

    async def test_domain_is_unique_when_present(self, session):
        vertical = await _vertical(session)
        session.add(Site(vertical_id=vertical.id, name="A", domain="example.be",
                         market="BE", default_language="fr"))
        await session.commit()
        session.add(Site(vertical_id=vertical.id, name="B", domain="example.be",
                         market="BE", default_language="fr"))
        with pytest.raises(IntegrityError):
            await session.commit()


class TestSeedKeywordScope:
    async def test_the_same_seed_cannot_be_registered_twice(self, session):
        vertical = await _vertical(session)
        for _ in range(2):
            session.add(SeedKeyword(vertical_id=vertical.id, query="Prix",
                                    normalized_query="prix", language="fr",
                                    market="BE"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_the_same_query_in_another_language_is_a_different_seed(self,
                                                                          session):
        vertical = await _vertical(session)
        session.add(SeedKeyword(vertical_id=vertical.id, query="prix",
                                normalized_query="prix", language="fr", market="BE"))
        session.add(SeedKeyword(vertical_id=vertical.id, query="prix",
                                normalized_query="prix", language="nl", market="BE"))
        await session.commit()


class TestResearchConstraints:
    async def test_idempotency_key_is_unique(self, session):
        vertical = await _vertical(session)
        await _run(session, vertical, key="dup")
        with pytest.raises(IntegrityError):
            await _run(session, vertical, key="dup")

    @pytest.mark.parametrize("state", [s.value for s in SourceState])
    async def test_every_upstream_state_is_storable(self, session, state):
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        session.add(ResearchSource(research_run_id=run.id, source_type="web",
                                   status=state))
        await session.commit()

    async def test_an_invented_source_state_is_refused(self, session):
        """A normalizer bug that widens the vocabulary must fail loudly."""
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        session.add(ResearchSource(research_run_id=run.id, source_type="web",
                                   status="probably-fine"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_evidence_requires_a_valid_observability(self, session):
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        source = ResearchSource(research_run_id=run.id, source_type="web", status="ok")
        session.add(source)
        await session.flush()
        session.add(ResearchEvidence(research_source_id=source.id, fact="f",
                                     evidence_type="reported",
                                     observability="PROBABLY_TRUE"))
        with pytest.raises(IntegrityError):
            await session.commit()

    @pytest.mark.parametrize("value", [o.value for o in Observability])
    async def test_the_three_observability_values_are_storable(self, session, value):
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        source = ResearchSource(research_run_id=run.id, source_type="web", status="ok")
        session.add(source)
        await session.flush()
        session.add(ResearchEvidence(research_source_id=source.id, fact="f",
                                     evidence_type="reported", observability=value))
        await session.commit()

    @pytest.mark.parametrize("category", [c.value for c in ClaimCategory])
    async def test_every_claim_category_the_classifier_can_emit_is_storable(
            self, session, category):
        """The regression this class of test exists for.

        `TARIFF`, `GRID_FEE`, `MARKET_AVERAGE` and `OBSERVED_PRICE_RANGE` were
        added to `ClaimCategory` across Phases 3.2–3.4 and never added to the
        CHECK in migration 0003. A live v2 run classifying a price claim as
        `OBSERVED_PRICE_RANGE` died mid-flush against PostgreSQL — the first run
        able to reach evidence persistence, because DataForSEO had refused every
        earlier SERP call. No test could catch it: those CHECKs lived only in
        the migration, and the test schema is built from the models.
        """
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        source = ResearchSource(research_run_id=run.id, source_type="web",
                                status="ok")
        session.add(source)
        await session.flush()
        session.add(ResearchEvidence(
            research_source_id=source.id, fact="f", evidence_type="atomic_claim",
            observability="ESTIMATED", claim_category=category))
        await session.commit()

    async def test_an_invented_claim_category_is_refused(self, session):
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        source = ResearchSource(research_run_id=run.id, source_type="web",
                                status="ok")
        session.add(source)
        await session.flush()
        session.add(ResearchEvidence(
            research_source_id=source.id, fact="f", evidence_type="atomic_claim",
            observability="ESTIMATED", claim_category="PROBABLY_A_PRICE"))
        with pytest.raises(IntegrityError):
            await session.commit()

    def test_the_migration_allowlist_matches_the_enum(self):
        """The guard against a third drift.

        Migration 0009 spells its list out on purpose — a migration that
        followed a live enum would change meaning on replay. That literal is
        therefore compared here instead: adding a `ClaimCategory` without a
        migration turns this red, which is the whole point.
        """
        import importlib.util
        from pathlib import Path

        chemin = Path(__file__).resolve().parents[1] / "migrations" / "versions" \
            / "0009_claim_category_check.py"
        spec = importlib.util.spec_from_file_location("m0009", chemin)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert set(module.CLAIM_CATEGORIES) == {c.value for c in ClaimCategory}, (
            "migration 0009 and ClaimCategory disagree: a category the "
            "classifier can emit would be refused by the database at write time")

    @pytest.mark.parametrize("enum, column", [
        (EvidenceStatus, "evidence_status"),
        (AuthorityRequirement, "authority_requirement"),
        (FreshnessRequirement, "freshness_requirement"),
    ])
    async def test_the_other_claim_vocabularies_are_storable_in_full(
            self, session, enum, column):
        """The three sibling allowlists were measured in sync when 0009 was
        written. They are pinned here so they stay that way."""
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        source = ResearchSource(research_run_id=run.id, source_type="web",
                                status="ok")
        session.add(source)
        await session.flush()
        for value in enum:
            session.add(ResearchEvidence(
                research_source_id=source.id, fact="f",
                evidence_type="atomic_claim", observability="ESTIMATED",
                **{column: value.value}))
        await session.commit()

    async def test_published_at_may_be_null(self, session):
        """An unknown publication date must be storable as unknown."""
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        session.add(ResearchSource(research_run_id=run.id, source_type="web",
                                   status="ok", url="https://example.invalid/x",
                                   published_at=None))
        await session.commit()


async def _draft(session) -> ContentDraft:
    vertical = await _vertical(session)
    run = await _run(session, vertical)
    package = ResearchPackage(keyword_id=run.keyword_id, research_run_id=run.id,
                              query="q", market="BE", language="fr",
                              intent="COMMERCIAL")
    session.add(package)
    await session.flush()
    brief = ContentBrief(research_package_id=package.id, content_type="GUIDE",
                         primary_query="q", search_intent="COMMERCIAL",
                         target_audience="a", objective="o",
                         recommended_title="t", recommended_slug="t")
    session.add(brief)
    await session.flush()
    draft = ContentDraft(content_brief_id=brief.id, provider="stub", model="m",
                         title="t", body="b")
    session.add(draft)
    await session.commit()
    return draft


class TestContentConstraints:
    async def test_invalid_content_type_is_refused(self, session):
        vertical = await _vertical(session)
        run = await _run(session, vertical)
        package = ResearchPackage(keyword_id=run.keyword_id, research_run_id=run.id,
                                  query="q", market="BE", language="fr",
                                  intent="COMMERCIAL")
        session.add(package)
        await session.flush()
        session.add(ContentBrief(research_package_id=package.id,
                                 content_type="BLOG_POST_ISH", primary_query="q",
                                 search_intent="COMMERCIAL", target_audience="a",
                                 objective="o", recommended_title="t",
                                 recommended_slug="t"))
        with pytest.raises(IntegrityError):
            await session.commit()


class TestApprovalConstraints:
    async def test_a_draft_has_at_most_one_approval_history(self, session):
        """Without this, a rejection could be overwritten by inserting a second,
        approving row."""
        draft = await _draft(session)
        session.add(Approval(content_draft_id=draft.id,
                             state=ApprovalState.REJECTED.value))
        await session.commit()
        session.add(Approval(content_draft_id=draft.id,
                             state=ApprovalState.APPROVED.value))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_an_invented_approval_state_is_refused(self, session):
        draft = await _draft(session)
        session.add(Approval(content_draft_id=draft.id, state="AUTO_APPROVED"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async def test_approval_defaults_to_pending(self, session):
        draft = await _draft(session)
        approval = Approval(content_draft_id=draft.id)
        session.add(approval)
        await session.commit()
        assert approval.state == ApprovalState.PENDING.value
        assert approval.decided_by is None
