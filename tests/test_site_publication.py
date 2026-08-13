"""Phase 4 — the publication gate, content sanitization and the site DTO.

The gate is the whole point of this file. Three independent conditions must hold
before content may be staged, and a fourth before it is live. Every test here
exists because a single missing check would put unapproved or unsafe content in
front of a visitor, and no amount of care in the frontend can undo that.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.enums import (ApprovalState, ContentType, PublicationState,
                            QALayer, QAStatus, QAType, SearchIntent)
from app.models import (Approval, ContentBrief, ContentDraft, PublishedContent,
                        QAReview, ResearchPackage, ResearchRun, SeedKeyword,
                        Site, Vertical)
from app.site.config import InvalidSite, SiteConfig, available_sites, load_site
from app.site.content_sanitizer import (contains_external_link, parse_sections,
                                        section_text, strip_unsafe)
from app.site.publication import (PublicationRefused, can_transition,
                                  evaluate_gate, publish_content, stage_content,
                                  to_dto)

PRICE_BODY = """# Prix des panneaux solaires en Belgique

En Belgique, le prix varie selon plusieurs facteurs. Voici les prix observés :

- **Entre 4.000 € et 14.000 € TVAC** pour une installation de **3 à 10 kWc**.
- **Entre 320 € et 430 € par m²** pour une installation complète.
- **Le panneau seul** coûte entre **130 € et 170 €/m²**.
- Un **budget de 7.000 € à 9.500 €** pour une installation de **5 à 6 kWc**.
- Un panneau de **400 Wc** coûte environ **220 € à 280 €**.

## Ce qui fait varier le prix

La taille du système, le type de panneaux et l'état de la toiture.

## Prochaines étapes

Demandez une estimation adaptée à votre situation.
"""

PRICE_ANSWERS = [
    {"claim": "Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à 10 kWc.",
     "category": "OBSERVED_PRICE_RANGE",
     "qualification": "a figure this source reports",
     "sources": ["https://www.energy-village.be/panneaux-photovoltaiques-prix"],
     "price_context": {"amounts": [4000, 14000], "currency": "EUR",
                       "basis": "TOTAL", "vat_status": "INCLUDED",
                       "system_size_kwp": [3, 10], "battery_included": None,
                       "installation_included": True, "is_range": True,
                       "usable": True}},
    {"claim": "Le panneau seul revient à 130 € – 170 €/m².",
     "category": "OBSERVED_PRICE_RANGE",
     "qualification": "a figure this source reports",
     "sources": ["https://www.energy-village.be/panneaux-photovoltaiques-prix"],
     "price_context": {"amounts": [130, 170], "currency": "EUR",
                       "basis": "PER_M2", "vat_status": "UNKNOWN",
                       "system_size_kwp": [], "battery_included": None,
                       "installation_included": None, "is_range": True,
                       "usable": True}},
]


@pytest_asyncio.fixture
async def solar_site(session) -> Site:
    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    site = Site(vertical_id=vertical.id, name="solar_be", domain=None, market="BE",
                default_language="fr", status="PLANNED")
    session.add(site)
    await session.flush()
    return site


async def _make_draft(session, site: Site, *, body: str = PRICE_BODY,
                      answers: list[dict] | None = None) -> tuple[ContentDraft,
                                                                  ContentBrief]:
    keyword = SeedKeyword(vertical_id=site.vertical_id, site_id=site.id,
                          query="prix panneaux solaires Belgique",
                          normalized_query="prix panneaux solaires belgique",
                          market="BE", language="fr")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily",
                      status="SUCCEEDED", idempotency_key=str(uuid.uuid4()),
                      correlation_id="test")
    session.add(run)
    await session.flush()
    package = ResearchPackage(keyword_id=keyword.id, research_run_id=run.id,
                              version=1, package_version=4,
                              query="prix panneaux solaires Belgique",
                              market="BE", language="fr", intent="COMMERCIAL",
                              summary="test package")
    session.add(package)
    await session.flush()
    brief = ContentBrief(
        research_package_id=package.id, content_type=ContentType.LANDING_PAGE.value,
        primary_query="prix panneaux solaires Belgique",
        search_intent=SearchIntent.COMMERCIAL.value,
        target_audience="propriétaires", objective="leads",
        recommended_title="Prix des panneaux solaires en Belgique",
        recommended_slug="prix-panneaux-solaires",
        outline=[], key_questions=[], required_facts=[], required_sources=[],
        cautionary_claims=[], cta_strategy={"code": "quote_request"},
        missing_information=[],
        core_question="prix panneaux solaires Belgique",
        core_answer_status="EVIDENCE_AVAILABLE",
        core_answer_evidence={"answers": answers if answers is not None
                              else PRICE_ANSWERS, "observed_range": None},
        must_answer_directly=True)
    draft = ContentDraft(content_brief_id=brief.id, provider="openai",
                         model="gpt-4o-mini", title="Prix des panneaux solaires",
                         body=body, meta_title="Prix panneaux solaires",
                         meta_description="Prix relevés en Belgique.")
    session.add(brief)
    await session.flush()
    draft.content_brief_id = brief.id
    session.add(draft)
    await session.flush()
    return draft, brief


async def _add_qa(session, draft: ContentDraft, *, factual_pass: bool = True,
                  seo_pass: bool = True) -> None:
    session.add(QAReview(
        content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
        layer=QALayer.FACTUAL.value,
        status=QAStatus.PASSED.value if factual_pass else QAStatus.FAILED.value,
        score=100 if factual_pass else 60,
        findings=[] if factual_pass else [
            {"code": "UNSUPPORTED_DRAFT_CLAIM", "blocking": True}],
        blocking_issues=[] if factual_pass else [
            {"code": "UNSUPPORTED_DRAFT_CLAIM", "blocking": True}]))
    session.add(QAReview(
        content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
        layer=QALayer.SEO.value,
        status=QAStatus.PASSED.value if seo_pass else QAStatus.FAILED.value,
        score=100 if seo_pass else 60,
        findings=[{"code": "SERP_CONTENT_GAP", "blocking": False}] if seo_pass
        else [{"code": "NO_QUANTIFIED_ANSWER", "blocking": True}],
        blocking_issues=[] if seo_pass else [
            {"code": "NO_QUANTIFIED_ANSWER", "blocking": True}]))
    await session.flush()


async def _approve(session, draft: ContentDraft,
                   state: ApprovalState = ApprovalState.APPROVED) -> None:
    session.add(Approval(content_draft_id=draft.id, state=state.value,
                         decided_by="owner" if state != ApprovalState.PENDING
                         else None))
    await session.flush()


# ─── The gate ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPublicationGate:
    async def test_a_draft_with_no_qa_and_no_approval_cannot_stage(self, session,
                                                                    solar_site):
        draft, brief = await _make_draft(session, solar_site)
        config = load_site("solar_be")
        with pytest.raises(PublicationRefused):
            await stage_content(session, draft=draft, brief=brief, site=solar_site,
                                config=config)

    async def test_failed_qa_cannot_stage_even_when_approved(self, session,
                                                              solar_site):
        """The dangerous case: a human approved it and QA says it is wrong."""
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft, seo_pass=False)
        await _approve(session, draft)

        gate = await evaluate_gate(session, draft)
        assert gate.seo_qa is False
        assert gate.approved is True
        assert gate.passed is False
        with pytest.raises(PublicationRefused, match="SEO QA"):
            await stage_content(session, draft=draft, brief=brief, site=solar_site,
                                config=load_site("solar_be"))

    async def test_qa_passing_is_not_permission_to_publish(self, session,
                                                           solar_site):
        """Both QA layers green, approval still PENDING. Must refuse."""
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft, ApprovalState.PENDING)

        gate = await evaluate_gate(session, draft)
        assert gate.factual_qa and gate.seo_qa
        assert gate.approved is False
        assert "PENDING" in " ".join(gate.reasons)
        with pytest.raises(PublicationRefused):
            await stage_content(session, draft=draft, brief=brief, site=solar_site,
                                config=load_site("solar_be"))

    async def test_approved_and_qa_clean_may_stage(self, session, solar_site):
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft)

        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=load_site("solar_be"))
        assert snapshot.state == PublicationState.STAGED.value
        assert snapshot.version == 1
        assert snapshot.noindex is True, "a staged page is never indexable"
        assert snapshot.sections, "the snapshot must carry its own content"

    async def test_a_draft_carrying_a_link_cannot_stage(self, session, solar_site):
        """Phase 3.3 shipped an outbound competitor link. It cannot come back."""
        body = PRICE_BODY + "\nVoir [ce comparateur](https://autre-installateur.be).\n"
        draft, brief = await _make_draft(session, solar_site, body=body)
        await _add_qa(session, draft)
        await _approve(session, draft)

        with pytest.raises(PublicationRefused, match="outbound link"):
            await stage_content(session, draft=draft, brief=brief, site=solar_site,
                                config=load_site("solar_be"))

    async def test_staging_does_not_publish(self, session, solar_site):
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft)
        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=load_site("solar_be"))

        # The site has no domain and is staging, so publication is impossible.
        with pytest.raises(PublicationRefused, match="not publishable"):
            await publish_content(session, snapshot=snapshot,
                                  config=load_site("solar_be"))
        assert snapshot.state == PublicationState.STAGED.value

    async def test_publishing_requires_an_explicit_action_on_a_live_site(
            self, session, solar_site):
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft)
        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=load_site("solar_be"))

        launched = load_site("solar_be").model_copy(deep=True)
        launched.domain = "example.be"
        launched.staging = False
        launched.seo.allow_indexing = True
        assert launched.is_indexable

        await publish_content(session, snapshot=snapshot, config=launched)
        assert snapshot.state == PublicationState.PUBLISHED.value
        assert snapshot.noindex is False

    async def test_versions_are_preserved_and_only_one_is_live(self, session,
                                                                solar_site):
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft)
        config = load_site("solar_be")
        first = await stage_content(session, draft=draft, brief=brief,
                                    site=solar_site, config=config)
        second = await stage_content(session, draft=draft, brief=brief,
                                     site=solar_site, config=config)
        assert (first.version, second.version) == (1, 2)

        launched = config.model_copy(deep=True)
        launched.domain, launched.staging = "example.be", False
        launched.seo.allow_indexing = True
        await publish_content(session, snapshot=first, config=launched)
        await publish_content(session, snapshot=second, config=launched)
        await session.flush()

        live = (await session.execute(
            select(PublishedContent).where(
                PublishedContent.state == PublicationState.PUBLISHED.value)
        )).scalars().all()
        assert len(live) == 1 and live[0].version == 2
        assert first.state == PublicationState.ARCHIVED.value, \
            "the superseded version is archived, not deleted"


class TestTransitionTable:
    def test_transitions_refuse_shortcuts(self):
        assert not can_transition(PublicationState.DRAFT, PublicationState.PUBLISHED)
        assert not can_transition(PublicationState.PENDING_APPROVAL,
                                  PublicationState.STAGED)
        assert not can_transition(PublicationState.APPROVED,
                                  PublicationState.PUBLISHED), \
            "approved content still has to be staged first"
        assert can_transition(PublicationState.STAGED, PublicationState.PUBLISHED)
        assert not can_transition(PublicationState.ARCHIVED,
                                  PublicationState.PUBLISHED)


@pytest.mark.asyncio
class TestQALayerDiscrimination:
    async def test_two_clean_reviews_are_told_apart_by_their_layer(
            self, session, solar_site):
        """The defect the gate found on the first real staging attempt.

        Both reviews passed with no findings, the classifier inferred layers from
        finding codes, and a draft with a passing SEO review was reported as
        having none. A clean review is exactly the case an inference cannot cover.
        """
        draft, _ = await _make_draft(session, solar_site)
        for layer in (QALayer.FACTUAL, QALayer.SEO):
            session.add(QAReview(
                content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
                layer=layer.value, status=QAStatus.PASSED.value, score=100,
                findings=[], blocking_issues=[]))
        await session.flush()

        gate = await evaluate_gate(session, draft)
        assert gate.factual_qa is True
        assert gate.seo_qa is True
        assert gate.reasons == ["no human approval recorded"]

    async def test_a_legacy_row_with_no_layer_is_still_classified(
            self, session, solar_site):
        """Phase 3 rows carry no layer and must remain readable."""
        draft, _ = await _make_draft(session, solar_site)
        session.add(QAReview(
            content_draft_id=draft.id, qa_type=QAType.DETERMINISTIC.value,
            layer=None, status=QAStatus.PASSED.value, score=100,
            findings=[{"code": "SERP_CONTENT_GAP", "blocking": False}],
            blocking_issues=[]))
        await session.flush()

        gate = await evaluate_gate(session, draft)
        assert gate.seo_qa is True, "a legacy SEO review must still count as one"
        assert gate.factual_qa is False


# ─── Rendering the price page ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPricePageRendering:
    async def _stage(self, session, site) -> PublishedContent:
        draft, brief = await _make_draft(session, site)
        await _add_qa(session, draft)
        await _approve(session, draft)
        return await stage_content(session, draft=draft, brief=brief, site=site,
                                   config=load_site("solar_be"))

    async def test_five_evidence_backed_statements_survive_to_the_dto(
            self, session, solar_site):
        snapshot = await self._stage(session, solar_site)
        dto = to_dto(snapshot, load_site("solar_be"))
        text = section_text(dto["sections"])

        for figure in ("4.000 €", "14.000 €", "320 € et 430 €", "130 € et 170 €",
                       "7.000 € à 9.500 €"):
            assert figure in text, f"lost quantified statement: {figure}"

    async def test_the_dto_carries_no_source_urls(self, session, solar_site):
        """Sources are recorded; they are not shipped to the browser.

        The only URL the DTO may contain is the page's own canonical. Every other
        `http` in the payload would be an evidence source, and Phase 3.3 shipped a
        competitor link the one time content carried its own references.
        """
        snapshot = await self._stage(session, solar_site)
        config = load_site("solar_be")
        dto = to_dto(snapshot, config)

        assert "energy-village.be" not in str(dto)
        canonical = dto["meta"]["canonical_url"]
        assert canonical.startswith("https://monprojetsolaire.be/")
        # Remove the one permitted URL, then assert nothing else looks like one.
        remainder = str(dto).replace(canonical, "")
        assert "http" not in remainder

    async def test_unknown_vat_is_carried_not_generalised(self, session,
                                                           solar_site):
        snapshot = await self._stage(session, solar_site)
        answers = snapshot.price_evidence["answers"]
        statuses = {a["vat_status"] for a in answers}
        assert statuses == {"INCLUDED", "UNKNOWN"}, \
            "a per-figure VAT status must survive into the snapshot"

    async def test_the_snapshot_is_a_copy_not_a_live_view(self, session,
                                                           solar_site):
        """Editing the draft afterwards must not change the approved page."""
        draft, brief = await _make_draft(session, solar_site)
        await _add_qa(session, draft)
        await _approve(session, draft)
        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=load_site("solar_be"))
        original = section_text(snapshot.sections)

        draft.body = "# Something else entirely\n\nAucun prix.\n"
        await session.flush()
        assert section_text(snapshot.sections) == original

    async def test_the_dto_has_no_field_for_qa_internals(self, session,
                                                          solar_site):
        snapshot = await self._stage(session, solar_site)
        dto = to_dto(snapshot, load_site("solar_be"))
        assert "qa_provenance" not in dto
        assert set(dto) == {"slug", "locale", "type", "search_intent", "title",
                            "meta", "sections", "price_evidence", "cta",
                            "version", "state", "updated_at"}


# ─── Sanitization ────────────────────────────────────────────────────────────

class TestContentSanitization:
    @pytest.mark.parametrize("payload", [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "<iframe src='https://evil.example'></iframe>",
        "<a href=\"javascript:alert(1)\">clic</a>",
        "<svg/onload=alert(1)>",
        "&lt;script&gt;alert(1)&lt;/script&gt;",
        "<style>body{display:none}</style>",
    ])
    def test_executable_and_embeddable_markup_is_removed(self, payload):
        cleaned = strip_unsafe(payload)
        for fragment in ("<script", "<iframe", "<svg", "<style", "onerror=",
                         "javascript:", "&lt;script"):
            assert fragment not in cleaned.lower()

    def test_sections_never_carry_raw_html(self):
        sections = parse_sections(
            "# Titre\n\nTexte <script>alert(1)</script> et <b>gras</b>.\n")
        rendered = str(sections)
        assert "<script" not in rendered
        assert "<b>" not in rendered

    def test_links_are_flattened_to_their_label(self):
        sections = parse_sections("Voir [ce comparateur](https://autre.be) ici.\n")
        text = section_text(sections)
        assert "ce comparateur" in text
        assert "autre.be" not in text
        assert not contains_external_link(text)

    def test_bare_urls_are_removed(self):
        sections = parse_sections("Plus d'infos sur https://autre-installateur.be !\n")
        assert "autre-installateur" not in section_text(sections)

    def test_a_price_list_is_recognised_as_one(self):
        sections = parse_sections(
            "- **Entre 4.000 € et 14.000 € TVAC** pour 3 à 10 kWc.\n"
            "- **320 € à 430 € par m²** pour une installation complète.\n")
        assert sections[0]["type"] == "price_list"

    def test_a_prose_list_is_not_a_price_list(self):
        sections = parse_sections(
            "- La taille du système compte.\n- L'orientation compte aussi.\n")
        assert sections[0]["type"] == "list"


# ─── Site configuration ──────────────────────────────────────────────────────

class TestSiteConfiguration:
    def test_solar_be_has_its_domain_and_is_still_not_indexable(self):
        """The domain arriving must not, on its own, make the site indexable.

        This is why indexability is three conditions. Owning an address and being
        ready to be found at it are different decisions.
        """
        config = load_site("solar_be")
        assert config.domain == "monprojetsolaire.be"
        assert config.seo.canonical_origin == "https://monprojetsolaire.be"
        assert config.staging is True
        assert config.seo.allow_indexing is False
        assert config.is_indexable is False

    def test_a_staging_site_may_not_enable_indexing(self):
        raw = load_site("solar_be").model_dump()
        raw["seo"]["allow_indexing"] = True
        with pytest.raises(ValueError, match="may not allow indexing"):
            SiteConfig(**raw)

    def test_a_site_with_no_domain_may_not_leave_staging(self):
        raw = load_site("solar_be").model_dump()
        raw["domain"] = None
        raw["staging"] = False
        raw["seo"] = {**raw["seo"], "canonical_origin": None}
        with pytest.raises(ValueError, match="nowhere for it to be published"):
            SiteConfig(**raw)

    def test_indexability_needs_all_three_conditions(self):
        base = load_site("solar_be").model_dump()
        base.update(staging=False)
        base["seo"] = {**base["seo"], "allow_indexing": True}
        assert SiteConfig(**base).is_indexable is True
        # Each variant removes exactly one of the three conditions. `domain: None`
        # forces staging back on, because the validator refuses the alternative.
        for override in ({"domain": None, "staging": True,
                          "seo": {**base["seo"], "allow_indexing": False}},
                         {"seo": {**base["seo"], "allow_indexing": False}}):
            variant = {**base, **override}
            assert SiteConfig(**variant).is_indexable is False

    def test_unsupplied_contact_and_legal_stay_empty_not_invented(self):
        """The brand is now real. Everything the owner has NOT supplied is not."""
        config = load_site("solar_be")
        assert config.brand_name == "Mon Projet Solaire"
        assert config.brand_name_is_placeholder is False
        assert config.contact.company_name is None
        assert config.contact.phone is None
        assert config.legal.reviewed is False, \
            "no generated legal text may be presented as reviewed"

    def test_an_unknown_site_is_refused(self):
        with pytest.raises(InvalidSite):
            load_site("no_such_site")

    def test_multi_vertical_isolation(self):
        """A second site over a different vertical loads through the same code."""
        assert {"solar_be", "demo_generic"} <= set(available_sites())
        generic = load_site("demo_generic")
        assert generic.vertical == "TEST_GENERIC"
        assert generic.market == "FR" and generic.default_language == "en"
        # Nothing solar leaked into the generic site.
        blob = str(generic.model_dump()).lower()
        for term in ("panneau", "solaire", "kwc", "belgique"):
            assert term not in blob
