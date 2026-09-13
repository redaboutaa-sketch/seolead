"""La veille de régression (2026-09-13).

CE QU'ELLE AURAIT ATTRAPÉ
=========================
« 1 € – 12 € par watt-crête » et « 10 000 € » pour une source qui dit 6 000 à
10 000 € sont restés en ligne du 13 août au 10 septembre. Les gardes ne
s'exécutent qu'au moment du jugement : une page franchie reste franchie, même
quand la règle qui l'a jugée a changé sept fois depuis.

Ces tests construisent ce cas — un instantané qui a gelé une ancienne lecture
pendant que le lecteur, lui, a été corrigé — et vérifient que la veille le
nomme. Puis ils vérifient ce qu'elle NE fait pas : elle n'écrit rien.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.enums import PublicationState
from app.models import Approval, PublishedContent
from app.services.regression_watch import (CONSTAT_DERIVE, CONSTAT_ORPHELIN,
                                           CONSTAT_PORTE, veiller)
from app.site.config import load_site
from app.site.publication import (compute_fingerprint, publish_content,
                                  stage_content)
from tests.fixtures.article_8a1f6e46 import REVISED_BODY
from tests.test_lot_c_gardes import (CLAIMS_WITH_EVIDENCE, _case,  # noqa: F401
                                     _deterministic_pass, _pending, solar_site)

KIT_3KWC = ("Globalement, pour un kit dont la puissance est de 3kWc, prévoyez "
            "un budget entre 6.000 et 10.000 € tout compris.")

# Ce que le brief avait gelé le jour où il a été écrit : la borne haute seule,
# parce que seule elle portait le symbole €.
LECTURE_D_AOUT = {
    "claim": KIT_3KWC, "category": "OBSERVED_PRICE_RANGE",
    "qualification": "a figure this source reports",
    "amounts": [10000], "currency": "EUR", "basis": "TOTAL",
    "vat_status": "UNKNOWN", "system_size_kwp": [3.0],
    "battery_included": None, "installation_included": True, "is_range": False,
}


async def _publier(session, solar_site, *, avec_reponse_prix: bool = False):
    """Une page vivante, passée par la porte comme n'importe quelle autre."""
    draft, brief, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE)
    if avec_reponse_prix:
        brief.core_answer_evidence = {
            "answers": [{"claim": KIT_3KWC, "category": "OBSERVED_PRICE_RANGE",
                         "qualification": "a figure this source reports",
                         "price_context": {"amounts": [10000], "currency": "EUR",
                                           "basis": "TOTAL", "is_range": False}}],
            "observed_range": None}
    pending, _ = await _pending(session, package)
    package.authoritative_research = {"resolution": [
        {"query": q, "status": "EXECUTED"} for q in pending]}
    await _deterministic_pass(session, draft)
    await session.flush()
    fingerprint, _ = await compute_fingerprint(session, draft)
    session.add(Approval(content_draft_id=draft.id, state="APPROVED",
                         decided_by="owner", render_fingerprint=fingerprint))
    await session.flush()
    config = load_site("solar_be")
    snapshot = await stage_content(session, draft=draft, brief=brief,
                                   site=solar_site, config=config)
    snapshot = await publish_content(session, snapshot=snapshot, config=config)
    return draft, brief, snapshot


@pytest.mark.asyncio
class TestUnePageSaine:

    async def test_rien_a_signaler(self, session, solar_site):
        await _publier(session, solar_site)
        rapport = await veiller(session, site_id=solar_site.id)
        assert rapport.ok
        assert rapport.checked == 1
        assert rapport.as_dict()["status"] == "CLEAN"

    async def test_une_page_ecrite_a_la_main_n_est_pas_re_jugee(
            self, session, solar_site):
        """Pas de brouillon derrière elle : il n'y a rien à re-juger, et la
        compter comme un constat noierait les vrais."""
        session.add(PublishedContent(
            site_id=solar_site.id, content_draft_id=None, locale="fr",
            slug="confidentialite", version=1, content_type="LEGAL",
            state=PublicationState.PUBLISHED.value, title="Confidentialité",
            sections=[], price_evidence={}, cta={}, qa_provenance={},
            noindex=False))
        await session.flush()
        rapport = await veiller(session, site_id=solar_site.id)
        assert rapport.ok
        assert rapport.unwatched == ["confidentialite"]
        assert rapport.checked == 0


@pytest.mark.asyncio
class TestLaDerive:

    async def test_un_instantane_qui_a_gele_une_ancienne_lecture(
            self, session, solar_site):
        """Le cas réel : la page sert « 10 000 € », les règles d'aujourd'hui
        liraient « 6 000 € – 10 000 € » depuis la MÊME phrase."""
        draft, brief, snapshot = await _publier(session, solar_site,
                                                avec_reponse_prix=True)
        # L'instantané tel qu'août l'a gelé, pendant que le lecteur a changé.
        snapshot.price_evidence = {**(snapshot.price_evidence or {}),
                                   "answers": [LECTURE_D_AOUT]}
        await session.flush()

        rapport = await veiller(session, site_id=solar_site.id)
        assert not rapport.ok
        derives = [c for c in rapport.findings if c.kind == CONSTAT_DERIVE]
        assert len(derives) == 1
        assert derives[0].slug == snapshot.slug
        assert derives[0].version == snapshot.version
        assert "règles d'aujourd'hui" in derives[0].detail

    async def test_le_rendu_servi_et_le_rendu_attendu_sont_nommes(
            self, session, solar_site):
        draft, brief, snapshot = await _publier(session, solar_site,
                                                avec_reponse_prix=True)
        snapshot.title = "Un titre que personne n'a approuvé"
        await session.flush()
        rapport = await veiller(session, site_id=solar_site.id)
        detail = [c for c in rapport.findings if c.kind == CONSTAT_DERIVE][0].detail
        # Les deux empreintes sont citées : un opérateur doit pouvoir les
        # retrouver sans relire le code.
        assert detail.count("…") >= 2


@pytest.mark.asyncio
class TestLaPorte:

    async def test_une_page_qui_ne_passerait_plus_est_signalee(
            self, session, solar_site):
        """Une approbation qui ne nomme plus le rendu courant : exactement
        l'état de toutes les pages approuvées avant le 2026-09-03."""
        draft, brief, snapshot = await _publier(session, solar_site)
        approval = (await session.execute(
            select(Approval).where(
                Approval.content_draft_id == draft.id))).scalar_one()
        approval.render_fingerprint = None
        await session.flush()

        rapport = await veiller(session, site_id=solar_site.id)
        portes = [c for c in rapport.findings if c.kind == CONSTAT_PORTE]
        assert len(portes) == 1
        assert "ne passerait plus la porte" in portes[0].detail
        assert "fingerprint" in portes[0].detail

    async def test_une_page_sans_brouillon_est_orpheline(self, session,
                                                         solar_site):
        draft, brief, snapshot = await _publier(session, solar_site)
        snapshot.content_draft_id = None
        await session.flush()
        # Un instantané dont le brouillon a disparu n'est pas « non surveillé » :
        # il a été produit par le pipeline et ne peut plus l'être.
        snapshot.content_draft_id = draft.id
        await session.delete(draft)
        await session.flush()
        rapport = await veiller(session, site_id=solar_site.id)
        assert [c.kind for c in rapport.findings] == [CONSTAT_ORPHELIN]


@pytest.mark.asyncio
class TestCeQueLaVeilleNeFaitPas:

    async def test_elle_ne_regarde_que_les_pages_vivantes(self, session,
                                                          solar_site):
        draft, brief, snapshot = await _publier(session, solar_site)
        snapshot.state = PublicationState.ARCHIVED.value
        await session.flush()
        rapport = await veiller(session, site_id=solar_site.id)
        assert rapport.checked == 0 and rapport.ok

    async def test_elle_n_ecrit_rien(self, session, solar_site):
        draft, brief, snapshot = await _publier(session, solar_site,
                                                avec_reponse_prix=True)
        snapshot.price_evidence = {**(snapshot.price_evidence or {}),
                                   "answers": [LECTURE_D_AOUT]}
        await session.flush()
        avant = (snapshot.state, snapshot.noindex, snapshot.version,
                 list(snapshot.price_evidence["answers"]))

        rapport = await veiller(session, site_id=solar_site.id)
        assert not rapport.ok, "le cas doit bien être une dérive"

        await session.refresh(snapshot)
        assert (snapshot.state, snapshot.noindex, snapshot.version,
                list(snapshot.price_evidence["answers"])) == avant
