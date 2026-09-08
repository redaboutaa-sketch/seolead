"""Republier une page lancée en douceur, pour lever son `noindex` (2026-09-08).

LE CAS RÉEL
===========
`/prix-panneaux-solaires-belgique` a été approuvée et publiée le 2026-08-31,
pendant que le site entier était `noindex`. La publication gèle cet état dans
l'instantané (`snapshot.noindex = not config.is_indexable`), et un instantané
publié ne peut plus évoluer que vers l'archivage. Le site est indexable depuis,
mais la page reste invisible pour Google : au 2026-09-06, sur 70 impressions
mesurées, aucune requête contenant « prix ». La page la plus proche d'un lead
est la seule que Google a interdiction de montrer.

Pour la republier il faut passer la porte, et la porte exige une approbation
qui NOMME le rendu. L'approbation d'août ne nomme rien (la colonne n'existait
pas). La porte dit donc « re-approve with --fingerprint »… et cette instruction
était inatteignable, parce que `APPROVED` était un état terminal complet.

Ce fichier prouve les deux moitiés : le blocage tel qu'il était, et le chemin
tel qu'il est maintenant — ré-affirmer l'approbation sur l'empreinte du rendu
courant, sans perdre la décision d'origine.
"""
from __future__ import annotations

import pytest

from app.core.enums import ApprovalState, PublicationState
from app.models import Approval
from app.services import approval_service
from app.site.config import load_site
from app.site.publication import (compute_fingerprint, evaluate_gate,
                                  publish_content, stage_content)
from tests.fixtures.article_8a1f6e46 import REVISED_BODY
from tests.test_lot_c_gardes import (CLAIMS_WITH_EVIDENCE, _case,  # noqa: F401
                                     _deterministic_pass, _pending, solar_site)


async def _legacy_case(session, solar_site):
    """Une page telle qu'août l'a laissée : approuvée sans empreinte, QA
    passée, recherches résolues."""
    draft, brief, package = await _case(session, solar_site, body=REVISED_BODY,
                                        claims=CLAIMS_WITH_EVIDENCE)
    pending, _ = await _pending(session, package)
    package.authoritative_research = {"resolution": [
        {"query": q, "status": "EXECUTED"} for q in pending]}
    await _deterministic_pass(session, draft)
    approval = Approval(content_draft_id=draft.id,
                        state=ApprovalState.APPROVED.value,
                        decided_by="owner", render_fingerprint=None)
    session.add(approval)
    await session.flush()
    return draft, brief, package, approval


class TestLeBlocageQueLaPorteNommait:

    @pytest.mark.asyncio
    async def test_une_approbation_sans_empreinte_ne_publie_pas(
            self, session, solar_site):
        draft, *_ = await _legacy_case(session, solar_site)
        gate = await evaluate_gate(session, draft)
        assert not gate.passed
        assert gate.approved is True, "la décision humaine existe bien"
        assert gate.approved_render is False
        assert any("names no render fingerprint" in r for r in gate.reasons)

    def test_le_remede_que_la_porte_nomme_existe(self):
        """La porte dit « re-approve with --fingerprint ». Si `APPROVED` était
        terminal, elle demanderait l'impossible."""
        assert approval_service.can_transition(ApprovalState.APPROVED,
                                               ApprovalState.APPROVED)

    def test_une_approbation_ne_devient_jamais_un_refus(self):
        assert not approval_service.can_transition(ApprovalState.APPROVED,
                                                   ApprovalState.REJECTED)
        assert not approval_service.can_transition(ApprovalState.APPROVED,
                                                   ApprovalState.NEEDS_REVISION)


@pytest.mark.asyncio
class TestLaReapprobationOuvreLaPorte:

    async def test_reaffirmer_sur_l_empreinte_courante_fait_passer_la_porte(
            self, session, solar_site):
        draft, brief, package, approval = await _legacy_case(session, solar_site)
        fingerprint, _ = await compute_fingerprint(session, draft)

        approval.render_fingerprint = fingerprint
        approval.decided_by = "owner"
        await session.flush()

        gate = await evaluate_gate(session, draft)
        assert gate.approved_render is True
        assert gate.passed, gate.reasons

    async def test_une_empreinte_perimee_ne_passe_pas(self, session, solar_site):
        """Ré-approuver ne contourne rien : l'empreinte doit être celle du
        rendu tel qu'il est, pas celle d'une version antérieure."""
        draft, brief, package, approval = await _legacy_case(session, solar_site)
        approval.render_fingerprint = "0" * 64
        await session.flush()
        gate = await evaluate_gate(session, draft)
        assert gate.approved_render is False
        assert not gate.passed


@pytest.mark.asyncio
class TestLeNoindexEstLeveParLaRepublication:

    async def test_la_page_relancee_en_douceur_redevient_indexable(
            self, session, solar_site):
        """Le cœur du sujet : republier recalcule `noindex` depuis l'état
        COURANT du site, et l'ancien instantané est archivé, jamais servi en
        double."""
        draft, brief, package, approval = await _legacy_case(session, solar_site)
        config = load_site("solar_be")
        assert config.is_indexable, "le site est indexable depuis le 2026-08-31"

        fingerprint, _ = await compute_fingerprint(session, draft)
        approval.render_fingerprint = fingerprint
        await session.flush()

        # L'instantané du lancement en douceur : publié, mais noindex.
        soft = await stage_content(session, draft=draft, brief=brief,
                                   site=solar_site, config=config)
        soft.noindex = True
        soft.state = PublicationState.PUBLISHED.value
        await session.flush()

        # La republication, sur le même brouillon et le même rendu.
        neuf = await stage_content(session, draft=draft, brief=brief,
                                   site=solar_site, config=config)
        neuf = await publish_content(session, snapshot=neuf, config=config)

        assert neuf.noindex is False, "la page est enfin indexable"
        assert neuf.version > soft.version
        await session.refresh(soft)
        assert soft.state == PublicationState.ARCHIVED.value

    async def test_le_rendu_republie_est_celui_qui_a_ete_approuve(
            self, session, solar_site):
        """Lever un `noindex` ne réécrit pas la page : l'empreinte du rendu est
        la même avant et après, et c'est bien celle que l'approbation nomme."""
        draft, brief, package, approval = await _legacy_case(session, solar_site)
        config = load_site("solar_be")
        fingerprint, _ = await compute_fingerprint(session, draft)
        approval.render_fingerprint = fingerprint
        await session.flush()

        snapshot = await stage_content(session, draft=draft, brief=brief,
                                       site=solar_site, config=config)
        await publish_content(session, snapshot=snapshot, config=config)

        apres, _ = await compute_fingerprint(session, draft)
        assert apres == fingerprint == approval.render_fingerprint


@pytest.mark.asyncio
class TestLHistoriqueDeDecision:

    async def test_la_decision_superseded_est_conservee(self, session,
                                                        solar_site):
        """Ré-approuver écrase les champs de décision — la table n'a qu'une
        ligne par brouillon. Ce qui serait détruit est empilé d'abord."""
        from datetime import datetime, timezone

        draft, brief, package, approval = await _legacy_case(session, solar_site)
        approval.decided_at = datetime(2026, 8, 31, tzinfo=timezone.utc)
        approval.note = "approbation du lancement"
        await session.flush()
        assert approval.history == []

        # Ce que le CLI fait avant d'écraser.
        approval.history = [*(approval.history or []), {
            "state": approval.state, "decided_by": approval.decided_by,
            "decided_at": approval.decided_at.isoformat(),
            "note": approval.note,
            "render_fingerprint": approval.render_fingerprint,
            "superseded_at": "2026-09-08T10:00:00+00:00"}]
        fingerprint, _ = await compute_fingerprint(session, draft)
        approval.render_fingerprint = fingerprint
        approval.note = "exposition à l'indexation"
        await session.flush()

        assert len(approval.history) == 1
        ancienne = approval.history[0]
        assert ancienne["render_fingerprint"] is None, "août ne nommait rien"
        assert ancienne["decided_at"].startswith("2026-08-31")
        assert ancienne["note"] == "approbation du lancement"
        assert approval.render_fingerprint == fingerprint
