"""Exporting a captured lead to Prospect 360 — TR-SL-01.

WHY THE STATE MACHINE LIVES HERE AND NOT IN THE ADAPTER
=======================================================
The adapter transports and classifies. This module decides what the local lead
becomes. Keeping them apart is what makes « la requête a réussi » and « le lead
est exporté » two separate claims: the second requires the first AND a durable
local write, and the gap between them is a real failure window that has its own
test.

THE ORDER OF WRITES IS THE WHOLE DESIGN
=======================================
    1. mint the export identity and FREEZE the canonical payload   ← committed
    2. attempt the deposit
    3. record the outcome                                          ← committed

Step 1 commits before any HTTP. If the process dies at step 2, the next run
replays the SAME correlation and the SAME frozen payload, and Prospect 360
answers `200 REPLAY` with the original prospect. Nothing is lost and nothing is
duplicated.

Rebuilding the payload at step 2 would break this: the lead row can have moved,
and same-correlation-different-fingerprint is a `409`, not a replay.

WHAT NEVER HAPPENS HERE
=======================
`EXPORTED` is never written on anything but a verified `201` or `200`. A `409`
is not success and never becomes one. No correlation is ever regenerated — not
on timeout, not on conflict, not on 401.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LeadState
from app.models import CapturedLead, LeadAttribution, LeadConsent
from app.site.config import SiteConfig
from app.site.prospect360_contract_v2 import (ContratV2Invalide,
                                              route_est_v2,
                                              valider_charge_v2,
                                              version_de_charge)
from app.site.prospect360_destination import (Prospect360Destination,
                                              ResultatExport,
                                              construire_charge_v2)

logger = logging.getLogger(__name__)

# Prefixe lisible dans les deux systèmes. La partie aléatoire est un uuid4 : la
# corrélation doit être unique par dépôt, pas devinable.
PREFIXE_CORRELATION = "sl"


class ExportRefuse(Exception):
    """L'export ne peut pas être tenté — pas un échec de transport."""


@dataclass(frozen=True)
class ResultatTentative:
    lead_id: str
    correlation_id: str
    resultat: str
    etat: str
    prospect_id: str | None = None
    http_status: int | None = None


def verifier_consentement(config: SiteConfig) -> None:
    """Le contrat exige `consent.processing = true`. On le PROUVE, on ne le suppose pas.

    `capture_lead` refuse une soumission sans consentement au traitement quand
    `consent_required` est vrai. Sur un site où il serait faux, l'existence du
    lead ne prouverait plus rien, et envoyer `processing: true` serait une
    affirmation fausse sur une personne réelle. On refuse plutôt d'exporter.
    """
    if not config.conversion.consent_required:
        raise ExportRefuse(
            "consent_required is false for this site: the captured lead does "
            "not prove processing consent, and `consent.processing: true` "
            "would be an assertion nobody made")


def verifier_campagne(config: SiteConfig) -> None:
    """`attribution.campaign` est requis par le contrat v2. Sans identifiant
    configuré, on refuse de frapper une identité : une charge gelée sans
    campagne ferait 422 à chaque tentative, pour toujours."""
    if not (config.export.prospect360_campaign or "").strip():
        raise ExportRefuse(
            "export.prospect360_campaign is not configured for this site: the "
            "v2 contract requires attribution.campaign, and a frozen payload "
            "without it would be refused on every attempt")


def verifier_route(destination: Prospect360Destination) -> None:
    """Le producteur émet le contrat v2 ; la route configurée doit le nommer.
    Une URL v1 recevrait des charges v2 et répondrait 422 — à chaque lead."""
    if not route_est_v2(destination.url):
        raise ExportRefuse(
            "PROSPECT360_INGEST_URL does not name the v2 route "
            "(/api/v2/lead-ingest): the producer emits contract v2 and would "
            "be refused on a v1 route")


async def preparer_identite_export(session: AsyncSession, lead: CapturedLead, *,
                                   config: SiteConfig) -> str:
    """Frapper l'identité d'export UNE FOIS et geler la charge v2. Idempotent.

    Committe AVANT toute tentative HTTP : c'est ce qui rend une réponse perdue
    rattrapable par un rejeu plutôt que par un second prospect. La charge est
    validée contre le contrat figé AVANT d'être gelée : ce qui est en base
    est, par construction, une charge v2 valide.
    """
    if lead.external_correlation_id and lead.export_payload:
        return lead.external_correlation_id

    verifier_consentement(config)
    verifier_campagne(config)
    attribution = (await session.execute(
        select(LeadAttribution)
        .where(LeadAttribution.captured_lead_id == lead.id))).scalar_one_or_none()
    consents = list((await session.execute(
        select(LeadConsent)
        .where(LeadConsent.captured_lead_id == lead.id)
        .order_by(LeadConsent.consent_key))).scalars().all())
    correlation = f"{PREFIXE_CORRELATION}-{uuid.uuid4()}"
    charge = construire_charge_v2(
        lead, correlation_id=correlation, attribution=attribution,
        consents=consents,
        consent_version=lead.consent_version or config.legal.consent_version,
        market=config.market, campaign=config.export.prospect360_campaign,
        contact_type=config.export.contact_type)
    try:
        valider_charge_v2(charge)
    except ContratV2Invalide as exc:
        # Rien n'est frappé, rien n'est gelé : le lead reste tel quel.
        raise ExportRefuse(f"payload does not satisfy contract v2: {exc}") from exc
    lead.external_correlation_id = correlation
    lead.export_payload = charge
    if lead.state == LeadState.NEW.value:
        lead.state = LeadState.PENDING_EXPORT.value
    await session.flush()
    await session.commit()
    return correlation


async def exporter_lead(session: AsyncSession, lead: CapturedLead, *,
                        destination: Prospect360Destination,
                        config: SiteConfig,
                        max_attempts: int = 5) -> ResultatTentative:
    """Une tentative, puis l'écriture de son issue."""
    verifier_route(destination)
    correlation = await preparer_identite_export(session, lead, config=config)
    charge = dict(lead.export_payload or {})

    if version_de_charge(charge) != 2:
        # Une identité frappée ne change jamais de version, et la route est
        # v2 : cette charge ne sera jamais acceptée. On ne la dépose pas, on
        # ne la re-frappe pas, on le dit. Le lead reste en attente d'un regard
        # humain ; son état ne bouge pas.
        lead.export_error = ("STALE_CONTRACT: frozen payload is not contract "
                             "v2 and cannot be replayed on the v2 route")
        await session.flush()
        await session.commit()
        logger.info("lead export refused",
                    extra={"lead_id": str(lead.id),
                           "external_correlation_id": correlation,
                           "outcome": ResultatExport.CONTRAT_PERIME})
        return ResultatTentative(lead_id=str(lead.id), correlation_id=correlation,
                                 resultat=ResultatExport.CONTRAT_PERIME,
                                 etat=lead.state, http_status=None)

    reponse = await destination.deposer(charge)
    lead.export_attempts = int(lead.export_attempts or 0) + 1
    lead.export_destination = destination.code

    if reponse.resultat in (ResultatExport.CREE, ResultatExport.REJEU):
        # Le rejeu rend le prospect D'ORIGINE : c'est ce qui referme la fenêtre
        # « accepté à distance, jamais écrit ici ».
        lead.remote_prospect_id = reponse.prospect_id or lead.remote_prospect_id
        lead.state = LeadState.EXPORTED.value
        lead.exported_at = datetime.now(timezone.utc)
        lead.export_error = None
    elif reponse.resultat == ResultatExport.CONFLIT:
        # Terminal, et surtout PAS exporté. Ni relance automatique, ni nouvelle
        # corrélation : les deux transformeraient un désaccord en doublon.
        lead.state = LeadState.EXPORT_FAILED.value
        lead.export_error = "CONFLICT: same correlation, divergent fingerprint"
    elif reponse.resultat == ResultatExport.REFUS_AUTH:
        # Défaut de configuration. On s'arrête : marteler Prospect 360 avec un
        # identifiant refusé ne le rendra pas valide.
        lead.state = LeadState.EXPORT_FAILED.value
        lead.export_error = f"UNAUTHORIZED: producer credential rejected " \
                            f"({reponse.http_status})"
    elif reponse.resultat == ResultatExport.REFUS_DEFINITIF:
        lead.state = LeadState.EXPORT_FAILED.value
        lead.export_error = f"REJECTED: {reponse.http_status}"
    else:  # RETENTABLE
        if lead.export_attempts >= max_attempts:
            lead.state = LeadState.EXPORT_FAILED.value
            lead.export_error = (f"RETRY_EXHAUSTED after {lead.export_attempts} "
                                 f"attempt(s): {reponse.detail or reponse.http_status}")
        else:
            lead.state = LeadState.PENDING_EXPORT.value
            lead.export_error = (f"RETRYABLE: "
                                 f"{reponse.detail or reponse.http_status}")

    await session.flush()
    await session.commit()

    # Identifiants techniques et issue. Ni en-tête, ni identifiant, ni charge.
    logger.info("lead export attempt",
                extra={"lead_id": str(lead.id),
                       "external_correlation_id": correlation,
                       "outcome": reponse.resultat,
                       "http_status": reponse.http_status,
                       "attempt": lead.export_attempts})

    return ResultatTentative(lead_id=str(lead.id), correlation_id=correlation,
                             resultat=reponse.resultat, etat=lead.state,
                             prospect_id=lead.remote_prospect_id,
                             http_status=reponse.http_status)


async def leads_a_exporter(session: AsyncSession, *, vertical_code: str,
                           limit: int = 50) -> list[CapturedLead]:
    """Ce qui attend encore. `EXPORT_FAILED` n'y figure pas : il est terminal
    pour l'automatisation et demande un regard humain."""
    resultat = await session.execute(
        select(CapturedLead)
        .where(CapturedLead.vertical_code == vertical_code)
        .where(CapturedLead.state.in_((LeadState.NEW.value,
                                       LeadState.PENDING_EXPORT.value)))
        .order_by(CapturedLead.created_at)
        .limit(limit))
    return list(resultat.scalars().all())


# ── Archiver un lead (2026-09-03) ────────────────────────────────────────────
# Un lead de test du propriétaire attend en PENDING_EXPORT et serait déposé au
# premier `leads export`. Aucune commande ne l'écartait. L'archivage est
# l'acte humain qui le sort de la sélection d'export sans l'effacer.

ETATS_ARCHIVABLES = (LeadState.NEW.value, LeadState.PENDING_EXPORT.value,
                     LeadState.EXPORT_FAILED.value, LeadState.REJECTED_SPAM.value)


@dataclass(frozen=True)
class ResultatArchivage:
    lead_id: str
    previous_state: str
    state: str
    applied: bool


async def archiver_lead(session: AsyncSession, lead: CapturedLead, *,
                        by: str, reason: str, apply: bool) -> ResultatArchivage:
    """Passer un lead en ARCHIVED — hors sélection d'export, journalisé.

    Refusé pour un lead exporté ou en cours d'export : il est déjà chez la
    destination, et l'archiver ici prétendrait le contraire. Sans `apply`,
    rien n'est écrit : la commande dit ce qu'elle ferait.
    """
    if not by.strip() or not reason.strip():
        raise ValueError("archiving needs who and why")
    if lead.state not in ETATS_ARCHIVABLES:
        raise ExportRefuse(
            f"a lead in state {lead.state} cannot be archived: it is, or is "
            f"being, exported")
    previous = lead.state
    if not apply:
        return ResultatArchivage(lead_id=str(lead.id), previous_state=previous,
                                 state=previous, applied=False)
    now = datetime.now(timezone.utc)
    lead.state = LeadState.ARCHIVED.value
    # Réaffectation complète : muter le dict en place échappe au détecteur de
    # changement de la colonne JSON. Même clé réservée que `_manual_followup`.
    lead.qualification = {**(lead.qualification or {}),
                          "_archive": {"recorded_by": by.strip(),
                                       "reason": reason.strip(),
                                       "previous_state": previous,
                                       "recorded_at": now.isoformat()}}
    await session.flush()
    await session.commit()
    logger.info("lead archived", extra={"lead_id": str(lead.id),
                                        "previous_state": previous})
    return ResultatArchivage(lead_id=str(lead.id), previous_state=previous,
                             state=lead.state, applied=True)
