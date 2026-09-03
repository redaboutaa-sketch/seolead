"""Tranche structurelle (lot C, 2026-09-03) — six gardes et une règle.

Le cas d'épreuve est l'article `8a1f6e46` tel qu'il a été publié le 2026-08-31
(`tests/fixtures/article_8a1f6e46.py`, repris au caractère près des rapports
de l'hôte). La règle du propriétaire pour chaque garde :

    elle doit ÉCHOUER sur cette version et PASSER sur la version révisée.
    Une garde qui passe sur les deux ne prouve rien.

Chaque classe ci-dessous porte donc au moins une paire de tests : le rendu
publié, le rendu révisé. Là où une garde ne mord PAS sur l'article publié
avec les données réelles du paquet (la couverture numérique, C.3 : chaque
chiffre de l'article existe dans une affirmation étayée — c'est la fraîcheur
et l'arbitrage qui le condamnent, pas la couverture), le test le dit et
prouve la garde sur la mutation la plus proche de l'article.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.core.enums import (ApprovalState, ContentType, QALayer, QAStatus,
                            QAType, SearchIntent)
from app.models import (Approval, ContentBrief, ContentDraft, QAReview,
                        ResearchPackage, ResearchRun, SeedKeyword, Site,
                        Vertical)
from app.services import factual_qa_v2, qa_service, research_planner
from app.services.factual_qa_v2 import (_ASSERTED, _MATCH_MARGIN, _RIVAL,
                                        _arbitrate, _match_strength,
                                        explain_arbitration, risky_segments,
                                        run_factual_qa_v2)
from app.services.research_planner import (abandon_query,
                                           plan_authoritative_research,
                                           record_resolution,
                                           unresolved_queries)
from app.site.config import load_site
from app.site.publication import (PublicationRefused, compute_fingerprint,
                                  evaluate_gate, render_sources, stage_content,
                                  to_dto)
from tests.fixtures.article_8a1f6e46 import (
    CLAIM_FAMILY_5000, CLAIM_PROSUMER_MECHANISM, CLAIM_REVERSE_METER_2030,
    CLAIM_ROI_5_TO_7_SPECIALIST, CLAIM_ROI_UNDER_7,
    CLAIM_YIELD_7_3_TO_8_4_OFFICIAL, PUBLISHED_BODY, PUBLISHED_CLAIMS,
    REVISED_BODY, REVISED_SENTENCE_A, SENTENCE_A, SENTENCE_B, SENTENCE_C)

# ─── Outils ──────────────────────────────────────────────────────────────────

def _run(body, claims, profile):
    return run_factual_qa_v2(
        {"title": "Rentabilité des panneaux solaires en Belgique", "body": body,
         "meta_title": "t", "meta_description": "d"},
        {"claims": claims}, profile)


def _codes(verdict):
    return [f["code"] for f in verdict["findings"]]


def _findings(verdict, code):
    return [f for f in verdict["findings"] if f["code"] == code]


SUPPORTED = [c for c in PUBLISHED_CLAIMS if c["evidence_status"] == "SUPPORTED"]

# Les preuves derrière deux affirmations, telles que le paquet les porte :
# URL, qualité, région, date. La page n'en montre jamais l'URL.
OFFICIAL_EVIDENCE = {
    "url": "https://energie.wallonie.be/fr/rentabilite-du-photovoltaique.html",
    "source_quality": "OFFICIAL", "supports": True, "region": "BE-WAL",
    "authority_type": "REGIONAL_ENERGY_ADMINISTRATION",
    "published_at": None, "effective_from": None,
    "freshness_status": "UNDATED_CURRENT",
}
COMMERCIAL_EVIDENCE = {
    "url": "https://www.un-installateur-concurrent.be/blog/famille-4-personnes",
    "source_quality": "COMMERCIAL", "supports": True, "region": "BE",
    "authority_type": None, "published_at": "2024-03-01T00:00:00+00:00",
    "effective_from": None, "freshness_status": "OBSERVED",
}
CLAIMS_WITH_EVIDENCE = [
    {**CLAIM_YIELD_7_3_TO_8_4_OFFICIAL, "evidence": [OFFICIAL_EVIDENCE]},
    {**CLAIM_FAMILY_5000, "evidence": [COMMERCIAL_EVIDENCE]},
    {**CLAIM_REVERSE_METER_2030, "evidence": [OFFICIAL_EVIDENCE]},
    CLAIM_ROI_5_TO_7_SPECIALIST, CLAIM_PROSUMER_MECHANISM, CLAIM_ROI_UNDER_7,
]


# ─── C.1 — arbitrage par couverture des segments à risque ────────────────────

class TestArbitrationCoversRiskySegments:
    def test_the_published_sentence_is_now_asserted_not_absolved(self):
        """Paires 1–3 du rapport --explain : verdict RIVAL le 2026-08-30.
        Le rival étayé parle du mécanisme du tarif prosumer et ne porte pas
        « 5 ans ». Il ne peut plus absoudre la phrase."""
        verdict, rival = _arbitrate(SENTENCE_A, CLAIM_ROI_UNDER_7, SUPPORTED)
        assert verdict == _ASSERTED
        assert rival is None or factual_qa_v2.covers(rival, {"5"})

    def test_whole_sentence_similarity_would_still_absolve_it(self):
        """La preuve que la garde mord là où l'ancienne passait : jugée sur la
        ressemblance de phrase entière, la lecture prosumer gagne d'une marge
        supérieure au seuil d'arbitrage — c'est le verdict publié."""
        rival = _match_strength(SENTENCE_A, CLAIM_PROSUMER_MECHANISM)
        contested = _match_strength(SENTENCE_A, CLAIM_ROI_UNDER_7)
        assert rival - contested > _MATCH_MARGIN

    def test_a_rival_that_carries_the_figures_still_wins(self):
        """Paires 4–5 : la phrase sur la famille de 4 personnes / 5000 kWh est
        portée par une affirmation étayée qui énonce les deux chiffres. Là,
        l'arbitrage avait raison et doit le rester."""
        verdict, rival = _arbitrate(SENTENCE_B, CLAIM_ROI_UNDER_7, SUPPORTED)
        assert verdict == _RIVAL
        assert rival is CLAIM_FAMILY_5000

    def test_risky_segments_are_figures_durations_percentages_and_dated_rules(self):
        assert risky_segments(SENTENCE_A) == {"5"}
        assert risky_segments(SENTENCE_B) == {"4", "5000"}
        assert risky_segments(SENTENCE_C) == {"2023", "2030"}
        assert risky_segments("entre 7 et 11 ans") == {"7", "11"}

    def test_explain_shows_which_figure_excluded_the_nearest_reading(self, solar_profile):
        report = explain_arbitration(
            {"title": "t", "body": SENTENCE_A, "meta_title": "t",
             "meta_description": "d"},
            {"claims": PUBLISHED_CLAIMS}, solar_profile)
        rows = [r for r in report if r["risky_segments"] == ["5"]]
        assert rows, report
        assert any(r["nearest_excluded_for"] == ["5"] for r in rows)

    def test_published_fails_revised_passes(self, solar_profile):
        published = _run(PUBLISHED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" in _codes(published)
        assert published["status"] == "FAILED"
        revised = _run(REVISED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "HIGH_RISK_CLAIM_ASSERTED" not in _codes(revised)
        assert revised["status"] == "PASSED", revised["findings"]


# ─── C.2 — le relecteur assisté bloque sur SUBSIDY / ROI / GRID_RULE ─────────

# La constatation réelle du relecteur assisté sur le brouillon 8a1f6e46, sans
# catégorie (le champ n'existait pas), sévérité high, jamais bloquante.
LEGACY_FINDING = {
    "code": "UNSUPPORTED_CLAIM", "severity": "high", "blocking": False,
    "message": ("The claim that installations in Wallonia remain profitable "
                "without public support needs more data or references to "
                "support it, as it may mislead readers."),
}


class TestLlmHighSeverityBlocksOnLegalCategories:
    def test_the_real_finding_on_8a1f6e46_now_blocks(self):
        assert qa_service.llm_finding_blocks(LEGACY_FINDING) is True

    def test_categorised_findings(self):
        assert qa_service.llm_finding_blocks(
            {"severity": "high", "category": "ROI", "message": "x"}) is True
        assert qa_service.llm_finding_blocks(
            {"severity": "high", "category": "SUBSIDY", "message": "x"}) is True
        assert qa_service.llm_finding_blocks(
            {"severity": "high", "category": "GRID_RULE", "message": "x"}) is True
        assert qa_service.llm_finding_blocks(
            {"severity": "high", "category": "OTHER",
             "message": "rentabilité"}) is False
        assert qa_service.llm_finding_blocks(
            {"severity": "medium", "category": "ROI", "message": "x"}) is False

    def test_a_high_finding_about_style_stays_advisory(self):
        assert qa_service.llm_finding_blocks(
            {"severity": "high",
             "message": "The introduction repeats the title twice."}) is False


# ─── C.3 — couverture numérique et canari d'extraction ───────────────────────

class TestNumericCoverage:
    def test_every_figure_of_the_published_article_exists_in_a_supported_claim(
            self, solar_profile):
        """Dit explicitement : cette garde seule n'aurait PAS arrêté 8a1f6e46.
        Le « 5 » de « 5 ans » existe dans une affirmation étayée (« 5 à 7
        ans », source spécialiste non datée). Ce sont C.1 et C.4 qui
        condamnent la phrase ; C.3 condamne un chiffre que rien ne porte."""
        verdict = _run(PUBLISHED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict)
        assert "NUMERIC_EXTRACTION_FAILED" not in _codes(verdict)

    def test_the_published_sentence_fails_once_no_supported_claim_carries_its_figure(
            self, solar_profile):
        """La mutation la plus proche de l'article : le même « 5 ans », sans
        l'affirmation spécialiste qui porte un 5. Le chiffre est inventé."""
        claims = [c for c in PUBLISHED_CLAIMS if c is not CLAIM_ROI_5_TO_7_SPECIALIST]
        verdict = _run(PUBLISHED_BODY, claims, solar_profile)
        hits = _findings(verdict, "NUMBER_WITHOUT_SOURCE")
        assert hits and any(SENTENCE_A[:60] in f["detail"] for f in hits)
        assert all(f["blocking"] for f in hits)

    def test_the_revised_article_passes_with_the_same_claims(self, solar_profile):
        claims = [c for c in PUBLISHED_CLAIMS if c is not CLAIM_ROI_5_TO_7_SPECIALIST]
        verdict = _run(REVISED_BODY, claims, solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict)

    def test_an_explicit_calculation_carries_its_own_figures(self, solar_profile):
        body = "Production annuelle : (1.000 kWh X 5 kWe) = 5.000 kWh."
        verdict = _run(body, PUBLISHED_CLAIMS, solar_profile)
        assert "NUMBER_WITHOUT_SOURCE" not in _codes(verdict)

    def test_canary_fails_when_digits_exist_but_nothing_is_extracted(
            self, solar_profile, monkeypatch):
        """Un extracteur qui ne lit plus rien ne certifie rien. Le test échoue
        quand l'extraction ne trouve aucun nombre dans un corps qui en a."""
        monkeypatch.setattr(factual_qa_v2, "risky_segments", lambda text: set())
        monkeypatch.setattr(factual_qa_v2, "_numbers", lambda text: [])
        verdict = _run(PUBLISHED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "NUMERIC_EXTRACTION_FAILED" in _codes(verdict)
        assert verdict["status"] == "FAILED"

    def test_canary_is_silent_on_a_body_without_digits(self, solar_profile):
        verdict = _run("Le soleil brille sur la Wallonie.", PUBLISHED_CLAIMS,
                       solar_profile)
        assert "NUMERIC_EXTRACTION_FAILED" not in _codes(verdict)


# ─── C.4 — fraîcheur obligatoire sur toute affirmation de rentabilité ────────

class TestRoiNeedsDatedSupport:
    def test_published_fails(self, solar_profile):
        verdict = _run(PUBLISHED_BODY, PUBLISHED_CLAIMS, solar_profile)
        hits = _findings(verdict, "ROI_WITHOUT_DATED_SOURCE")
        assert hits and any(SENTENCE_A[:60] in f["detail"] for f in hits)

    def test_the_category_of_the_matched_claim_does_not_matter(self, solar_profile):
        """« rentabilisation en 5 à 7 ans » est classée GENERAL par le
        classifieur ; ce que la phrase affirme se lit dans la phrase."""
        assert CLAIM_ROI_5_TO_7_SPECIALIST["category"] == "GENERAL"
        assert CLAIM_ROI_5_TO_7_SPECIALIST["has_dated_support"] is False
        body = "En Belgique, l'installation est rentabilisée en 5 à 7 ans."
        verdict = _run(body, [CLAIM_ROI_5_TO_7_SPECIALIST], solar_profile)
        assert "ROI_WITHOUT_DATED_SOURCE" in _codes(verdict)

    def test_revised_passes_on_the_dated_official_figure(self, solar_profile):
        verdict = _run(REVISED_BODY, PUBLISHED_CLAIMS, solar_profile)
        assert "ROI_WITHOUT_DATED_SOURCE" not in _codes(verdict), verdict["findings"]
        # The sentence is ROI-shaped and its figures are carried by a claim
        # whose support is dated: exactly the shape the rule admits.
        assert factual_qa_v2._ROI_SHAPE.search(REVISED_SENTENCE_A)


# ─── Base : un brouillon, son paquet, sa porte ───────────────────────────────

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


async def _case(session, site: Site, *, body: str, claims: list[dict],
                authoritative_research: dict | None = None):
    keyword = SeedKeyword(vertical_id=site.vertical_id, site_id=site.id,
                          query="rentabilité panneaux solaires Belgique",
                          normalized_query="rentabilite panneaux solaires belgique",
                          market="BE", language="fr")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily",
                      status="SUCCEEDED", idempotency_key=str(uuid.uuid4()),
                      correlation_id="test")
    session.add(run)
    await session.flush()
    package = ResearchPackage(
        keyword_id=keyword.id, research_run_id=run.id, version=1,
        package_version=4, query="rentabilité panneaux solaires Belgique",
        market="BE", language="fr", intent="INFORMATIONAL",
        summary="fixture 8a1f6e46", facts=claims,
        authoritative_research=authoritative_research)
    session.add(package)
    await session.flush()
    brief = ContentBrief(
        research_package_id=package.id, content_type=ContentType.ARTICLE.value,
        primary_query="rentabilité panneaux solaires Belgique",
        search_intent=SearchIntent.INFORMATIONAL.value,
        target_audience="propriétaires", objective="leads",
        recommended_title="Rentabilité des panneaux solaires en Belgique",
        recommended_slug="rentabilite-panneaux-solaires-belgique",
        outline=[], key_questions=[], required_facts=[], required_sources=[],
        cautionary_claims=[], cta_strategy={"code": "quote_request"},
        missing_information=[], core_question=None,
        core_answer_status="NOT_A_PRICE_QUESTION",
        core_answer_evidence={"answers": [], "observed_range": None},
        must_answer_directly=False)
    session.add(brief)
    await session.flush()
    draft = ContentDraft(content_brief_id=brief.id, provider="openai",
                         model="gpt-4o-mini",
                         title="Rentabilité des panneaux solaires en Belgique",
                         body=body, meta_title="Rentabilité panneaux solaires",
                         meta_description="Ce que disent les sources.")
    session.add(draft)
    await session.flush()
    return draft, brief, package


async def _deterministic_pass(session, draft):
    for layer in (QALayer.FACTUAL, QALayer.SEO):
        session.add(QAReview(content_draft_id=draft.id,
                             qa_type=QAType.DETERMINISTIC.value,
                             layer=layer.value, status=QAStatus.PASSED.value,
                             score=100, findings=[], blocking_issues=[]))
    await session.flush()


async def _approve(session, draft, *, fingerprint):
    session.add(Approval(content_draft_id=draft.id,
                         state=ApprovalState.APPROVED.value, decided_by="owner",
                         render_fingerprint=fingerprint))
    await session.flush()


async def _advisory(session, draft, findings):
    session.add(QAReview(content_draft_id=draft.id,
                         qa_type=QAType.LLM_ASSISTED.value,
                         layer=QALayer.ADVISORY.value,
                         status=QAStatus.PASSED.value, score=None,
                         findings=findings, blocking_issues=[]))
    await session.flush()


def _resolved(query: str) -> dict:
    return {"resolution": [{"query": query, "status": "EXECUTED",
                            "returned": 3, "accepted": 1}]}


# ─── C.2 à la porte : la ligne du relecteur assisté ──────────────────────────

@pytest.mark.asyncio
class TestGateAdvisory:
    async def test_the_legacy_row_of_8a1f6e46_blocks_the_gate(self, session,
                                                             solar_site):
        draft, _, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE)
        await _deterministic_pass(session, draft)
        await _advisory(session, draft, [LEGACY_FINDING])
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        gate = await evaluate_gate(session, draft)
        assert gate.advisory_qa is False
        assert gate.passed is False
        assert any("model-assisted QA" in r for r in gate.reasons)

    async def test_a_clean_advisory_row_passes(self, session, solar_site):
        draft, _, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE)
        await _deterministic_pass(session, draft)
        await _advisory(session, draft, [
            {"code": "STYLE", "severity": "low", "category": "OTHER",
             "message": "The conclusion could be shorter.", "blocking": False}])
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        gate = await evaluate_gate(session, draft)
        assert gate.advisory_qa is True
        assert not [r for r in gate.reasons if "model-assisted" in r]


# ─── C.5 — recherche proposée : lancée ou abandonnée, jamais « proposée » ────

class TestResearchResolution:
    def _plan(self, solar_profile):
        return plan_authoritative_research(
            topic="rentabilité panneaux solaires Belgique", market="BE",
            unresolved=research_planner.as_evaluated(PUBLISHED_CLAIMS,
                                                     solar_profile),
            profile=solar_profile)

    def test_the_package_of_8a1f6e46_proposes_searches(self, solar_profile):
        plan = self._plan(solar_profile)
        assert not plan.is_empty, plan.skipped_reason

    def test_a_proposed_search_is_pending_until_executed_or_abandoned(
            self, solar_profile):
        plan = self._plan(solar_profile)
        pending = unresolved_queries(plan, None)
        assert [q["query"] for q in pending] == [q.query for q in plan.queries]

    def test_execution_resolves_by_query_text(self, solar_profile):
        plan = self._plan(solar_profile)
        package = type("P", (), {"authoritative_research": None})()
        first = plan.queries[0].query
        record_resolution(package, plan, {
            "queries_executed": [{"query": first, "category": "SUBSIDY",
                                  "returned": 3, "accepted": 1}],
            "accepted": [{"query": first, "name": "Portail wallon de l'énergie",
                          "domain": "energie.wallonie.be",
                          "authority_type": "REGIONAL_ENERGY_ADMINISTRATION",
                          "region": "BE-WAL", "status": "UNDATED_CURRENT"}],
        }, by="test")
        remaining = [q["query"] for q in unresolved_queries(
            plan, package.authoritative_research)]
        assert first not in remaining
        assert len(remaining) == len(plan.queries) - 1
        recorded = package.authoritative_research["resolution"][0]
        assert recorded["status"] == "EXECUTED"
        assert recorded["sources"][0]["name"] == "Portail wallon de l'énergie"
        assert "url" not in recorded["sources"][0]

    def test_abandonment_needs_a_reason(self, solar_profile):
        plan = self._plan(solar_profile)
        package = type("P", (), {"authoritative_research": None})()
        query = plan.queries[0].query
        with pytest.raises(ValueError):
            abandon_query(package, query, reason="   ", by="owner")
        # A record that says ABANDONED with no reason resolves nothing.
        assert unresolved_queries(plan, {"resolution": [
            {"query": query, "status": "ABANDONED", "reason": ""}]})
        abandon_query(package, query, reason="Bruxelles hors périmètre de la page",
                      by="owner")
        assert query not in [q["query"] for q in unresolved_queries(
            plan, package.authoritative_research)]


@pytest.mark.asyncio
class TestGateResearchResolution:
    async def test_the_published_package_blocks_the_gate(self, session, solar_site):
        """Paquet f9534a41 : cinq recherches proposées, aucune lancée, rien
        d'enregistré. Sous la porte d'aujourd'hui, l'article ne passe pas."""
        draft, _, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE,
                                        authoritative_research=None)
        await _deterministic_pass(session, draft)
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        gate = await evaluate_gate(session, draft)
        assert gate.research_resolved is False
        assert gate.passed is False
        assert any("proposed authoritative search" in r for r in gate.reasons)

    async def test_executed_and_abandoned_searches_open_the_gate(
            self, session, solar_site, solar_profile):
        plan = plan_authoritative_research(
            topic="rentabilité panneaux solaires Belgique", market="BE",
            unresolved=research_planner.as_evaluated(CLAIMS_WITH_EVIDENCE,
                                                     solar_profile),
            profile=solar_profile)
        assert not plan.is_empty
        record = {"resolution": []}
        for index, planned in enumerate(plan.queries):
            record["resolution"].append(
                {"query": planned.query, "status": "EXECUTED", "accepted": 1}
                if index % 2 == 0 else
                {"query": planned.query, "status": "ABANDONED",
                 "reason": "hors périmètre de la page", "by": "owner"})
        draft, _, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE,
                                        authoritative_research=record)
        await _deterministic_pass(session, draft)
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        gate = await evaluate_gate(session, draft)
        assert gate.research_resolved is True, gate.reasons
        assert gate.passed is True, gate.reasons


# ─── B.8 — l'approbation nomme un rendu, jamais une intention ────────────────

@pytest.mark.asyncio
class TestApprovalByFingerprint:
    async def _ready(self, session, solar_site):
        draft, brief, package = await _case(session, solar_site, body=REVISED_BODY,
                                            claims=CLAIMS_WITH_EVIDENCE,
                                            authoritative_research={
                                                "resolution": []})
        # Resolve every proposed search so only the approval is at stake.
        pending, _ = await _pending(session, package)
        package.authoritative_research = {"resolution": [
            {"query": q, "status": "EXECUTED"} for q in pending]}
        await _deterministic_pass(session, draft)
        return draft, brief, package

    async def test_an_approval_without_fingerprint_is_an_intention(
            self, session, solar_site):
        """L'approbation de 8a1f6e46 : « rev 2 APPROVED », aucune empreinte."""
        draft, _, _ = await self._ready(session, solar_site)
        await _approve(session, draft, fingerprint=None)
        gate = await evaluate_gate(session, draft)
        assert gate.approved is True
        assert gate.approved_render is False
        assert gate.passed is False
        assert any("approved an intention" in r for r in gate.reasons)

    async def test_an_approval_of_the_current_render_passes(self, session,
                                                            solar_site):
        draft, _, _ = await self._ready(session, solar_site)
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        gate = await evaluate_gate(session, draft)
        assert gate.approved_render is True
        assert gate.passed is True, gate.reasons

    async def test_a_render_changed_after_approval_is_refused(self, session,
                                                              solar_site):
        draft, brief, _ = await self._ready(session, solar_site)
        fp, _ = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        draft.body = REVISED_BODY + "\n\nUne phrase de plus, relue par personne."
        await session.flush()
        gate = await evaluate_gate(session, draft)
        assert gate.approved_render is False
        assert any("is not what would be published" in r for r in gate.reasons)
        with pytest.raises(PublicationRefused):
            await stage_content(session, draft=draft, brief=brief,
                                site=solar_site, config=load_site("solar_be"))

    async def test_the_fingerprint_is_stable_and_sensitive(self, session,
                                                           solar_site):
        draft, _, package = await self._ready(session, solar_site)
        first, _ = await compute_fingerprint(session, draft)
        again, _ = await compute_fingerprint(session, draft)
        assert first == again and len(first) == 64
        draft.meta_description = "Autre description."
        assert (await compute_fingerprint(session, draft))[0] != first


async def _pending(session, package):
    from app.site.publication import _pending_searches
    pending, reason = await _pending_searches(session, package)
    return [q["query"] for q in pending], reason


# ─── B.7 — les sources sont rendues, sans URL ────────────────────────────────

class TestRenderedSources:
    def test_the_published_page_had_no_source_to_show(self):
        """Avec les affirmations telles que le paquet les portait pour les
        chiffres publiés : rien d'officiel derrière « 5 ans »."""
        sources = render_sources(SENTENCE_A, CLAIMS_WITH_EVIDENCE)
        assert sources == []

    def test_the_revised_page_shows_its_sources_with_their_figures(self):
        sources = render_sources(REVISED_BODY, CLAIMS_WITH_EVIDENCE)
        assert sources, "the revised body states sourced figures"
        official = [s for s in sources if s["tier"] == "OFFICIAL"]
        assert official and official[0]["name"] == "energie.wallonie.be"
        assert {"7,3%", "8,4%"} <= set(official[0]["figures"])
        assert official[0]["region"] == "BE-WAL"
        assert official[0]["date"] is None
        assert official[0]["freshness"] == "UNDATED_CURRENT"

    def test_a_commercial_source_is_described_never_named(self):
        sources = render_sources(REVISED_BODY, CLAIMS_WITH_EVIDENCE)
        commercial = [s for s in sources if s["tier"] == "COMMERCIAL"]
        assert commercial and commercial[0]["name"] is None
        assert commercial[0]["date"] == "2024-03-01"
        assert any("5000 kWh" in f for f in commercial[0]["figures"])

    def test_no_entry_carries_a_url_or_a_claim_identifier(self):
        for entry in render_sources(REVISED_BODY, CLAIMS_WITH_EVIDENCE):
            assert "url" not in entry and "source_ref" not in entry
            assert "concurrent" not in str(entry)
            assert "http" not in str(entry)

    def test_official_sources_come_first(self):
        tiers = [s["tier"] for s in render_sources(REVISED_BODY,
                                                   CLAIMS_WITH_EVIDENCE)]
        assert tiers == sorted(tiers, key=lambda t: t != "OFFICIAL")


@pytest.mark.asyncio
class TestSourcesTravelWithTheSnapshot:
    async def test_staged_snapshot_freezes_its_sources_and_the_dto_shows_them(
            self, session, solar_site):
        draft, brief, package = await _case(session, solar_site, body=REVISED_BODY,
                                            claims=CLAIMS_WITH_EVIDENCE)
        pending, _ = await _pending(session, package)
        package.authoritative_research = {"resolution": [
            {"query": q, "status": "EXECUTED"} for q in pending]}
        await _deterministic_pass(session, draft)
        fp, sources = await compute_fingerprint(session, draft)
        await _approve(session, draft, fingerprint=fp)
        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=load_site("solar_be"))
        assert snapshot.sources == sources
        dto = to_dto(snapshot, load_site("solar_be"))
        assert dto["sources"] == sources
        assert "http" not in str(dto["sources"])
        assert dto["fingerprint"] if "fingerprint" in dto else True
