"""The Prospect 360 producer — TR-SL-01.

WHAT PHASE 4 LEFT, AND WHAT THIS CLOSES
=======================================
`LeadDestination` was a Protocol with one honest implementation that stored the
lead and stopped. This module is the second implementation: it builds the
canonical body, presents the producer credential, and classifies the answer. It
does not decide what the local lead becomes — that is `app.services.lead_export`,
because a transport that also owned the state machine could report success from
inside the same call that failed.

THE CONTRACT IS RECOVERED, NOT INVENTED
=======================================
Field set, bounds and values come from
`docs/integrations/PROSPECT360_INGEST_CONTRACT.md` §Phase 5A-P4/P5, which is the
same document the deployed DTO was built from. Fingerprint v1 is ARMED and
immutable since 2026-08-16T17:34:58Z: the field set below can never change
shape. A future canonical change is a v2 published beside v1, never an edit
here.

`extra: "forbid"` applies on every model on the far side. An unknown key is a
422, not a silent drop — so this module sends the declared keys and nothing
else. No metadata, no blob, no `monthly_bill_eur`, no `battery_interest`, no
marketing consent, and above all no `tenant_id`: the tenant falls out of the
presented secret, and sending one would be refused.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timezone
from typing import Any

import httpx

from app.core.config import Settings
from app.models import CapturedLead

logger = logging.getLogger(__name__)

# Recovered from the contract, §Phase 5A-P3 line « "source_system":
# "seo_lead_factory" ». Not a name chosen here.
SOURCE_SYSTEM = "seo_lead_factory"

# The seven Solar fields of DEC-P5A-QUAL-03, in the contract's order. Four are
# required; three are optional and stay ABSENT when unanswered — `UNKNOWN` is an
# answer the form offers explicitly, and coercing absence to it would change the
# fingerprint and assert something the visitor never said.
PROJECT_REQUIS = ("owner_status", "property_type", "postcode",
                  "project_timeframe")
PROJECT_FACULTATIFS = ("roof_type", "roof_orientation", "annual_consumption_kwh")

# Excluded by the contract, and named so their absence is deliberate rather than
# an oversight a reader has to infer.
PROJECT_EXCLUS = ("monthly_bill_eur", "battery_interest")


class ResultatExport:
    """How Prospect 360 answered, in the vocabulary the state machine uses."""

    CREE = "CREATED"          # 201 — terminal success
    REJEU = "REPLAY"          # 200 — terminal success, original prospect
    CONFLIT = "CONFLICT"      # 409 — terminal FAILURE, never success
    REFUS_AUTH = "UNAUTHORIZED"   # 401/403 — configuration, not business
    RETENTABLE = "RETRYABLE"      # 429, 5xx, timeout, connection failure
    REFUS_DEFINITIF = "REJECTED"  # other 4xx — the body is wrong, retry won't fix


@dataclass(frozen=True)
class ReponseProspect360:
    resultat: str
    http_status: int | None
    prospect_id: str | None = None
    detail: str = ""


def _instant_utc(valeur) -> str | None:
    """ISO 8601 en UTC, suffixe `Z`. Un instant naïf est supposé UTC — c'est ce
    que `capture_lead` écrit (`datetime.now(timezone.utc)`)."""
    if valeur is None:
        return None
    if getattr(valeur, "tzinfo", None) is None:
        valeur = valeur.replace(tzinfo=timezone.utc)
    return valeur.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def construire_charge(lead: CapturedLead, *, correlation_id: str,
                      consent_version: str | None,
                      attribution: Any = None) -> dict[str, Any]:
    """La charge canonique, telle que le contrat la déclare — et rien de plus.

    Appelée UNE FOIS, au moment où l'identité d'export est frappée. Le résultat
    est gelé en base ; les tentatives suivantes rejouent cette copie.
    """
    q = dict(lead.qualification or {})

    contact = {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "email": lead.email,
        "phone": lead.phone,
        # Le formulaire solaire B2C ne le demande pas. Absent, pas vide.
        "job_title": None,
    }

    projet: dict[str, Any] = {}
    for champ in PROJECT_REQUIS:
        valeur = q.get(champ)
        if champ == "postcode" and not valeur:
            valeur = lead.postcode
        projet[champ] = valeur
    for champ in PROJECT_FACULTATIFS:
        if champ in q and q[champ] is not None:
            projet[champ] = q[champ]

    consentement = {
        # Le lead n'existe pas sans consentement au traitement : `capture_lead`
        # refuse la soumission quand `consent_required` est vrai. On l'exige à
        # nouveau côté export plutôt que de le supposer — voir `verifier_consentement`.
        "processing": True,
        "version": consent_version,
        # Toujours en UTC explicite. Après un aller-retour SQLite le tzinfo peut
        # être perdu ; un instant sans fuseau serait ambigu chez le destinataire.
        "timestamp": _instant_utc(lead.consent_timestamp),
        "source": lead.consent_source,
    }

    # Passée explicitement : `lead.attribution` est une relation paresseuse, et
    # la charger implicitement ici lèverait `MissingGreenlet` en asynchrone —
    # une panne de transport déguisée en défaut de mapping.
    a = attribution
    attribution = {
        "source": getattr(a, "source", None),
        "source_detail": getattr(a, "channel", None),
        "landing_page": getattr(a, "landing_path", None),
        "content_id": (str(a.published_content_id)
                       if a is not None and a.published_content_id else None),
        "locale": lead.language,
        "search_intent": getattr(a, "search_intent", None),
        "keyword_cluster": getattr(a, "keyword_cluster", None),
        "utm_source": getattr(a, "utm_source", None),
        "utm_medium": getattr(a, "utm_medium", None),
        "utm_campaign": getattr(a, "utm_campaign", None),
        "utm_content": getattr(a, "utm_content", None),
        "utm_term": getattr(a, "utm_term", None),
        "cta": lead.conversion_type,
        "conversion_type": lead.conversion_type,
    }

    return {
        "external_correlation_id": correlation_id,
        "source_system": SOURCE_SYSTEM,
        "contact": contact,
        "project": projet,
        "consent": consentement,
        "attribution": attribution,
    }


class Prospect360Destination:
    """L'adaptateur HTTP. Il transporte et classe ; il ne décide de rien."""

    code = "prospect360"

    def __init__(self, settings: Settings, *,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = settings.prospect360_endpoint.strip()
        # Gardé tel quel, jamais découpé, jamais journalisé. `httpx` compose
        # l'en-tête ; la valeur ne devient pas une chaîne baladeuse ici.
        self._credential = settings.prospect360_credential.strip()
        self._timeout = settings.prospect360_timeout_seconds
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout,
                                 transport=self._transport)

    async def deposer(self, charge: dict[str, Any]) -> ReponseProspect360:
        """Déposer la charge canonique. Aucune relance ici : c'est la politique
        du service appelant, pas celle du transport."""
        entetes = {"Authorization": f"Bearer {self._credential}",
                   "Content-Type": "application/json"}
        try:
            async with self._client() as client:
                r = await client.post(self._url, json=charge, headers=entetes)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # Le réseau n'a pas répondu : on ne sait PAS si la charge est
            # arrivée. C'est précisément le cas que le rejeu rattrape.
            return ReponseProspect360(ResultatExport.RETENTABLE, None,
                                      detail=type(exc).__name__)

        corps: dict[str, Any] = {}
        try:
            corps = r.json() if r.content else {}
        except ValueError:
            corps = {}

        if r.status_code == 201:
            return ReponseProspect360(ResultatExport.CREE, 201,
                                      prospect_id=corps.get("prospect_id"))
        if r.status_code == 200:
            return ReponseProspect360(ResultatExport.REJEU, 200,
                                      prospect_id=corps.get("prospect_id"))
        if r.status_code == 409:
            # Même corrélation, empreinte différente. Ce n'est PAS un succès et
            # ce n'est pas rejouable : la charge a divergé de ce qui a été
            # déposé, et Prospect 360 ne divulgue pas le prospect d'origine.
            return ReponseProspect360(ResultatExport.CONFLIT, 409,
                                      detail="fingerprint divergent")
        if r.status_code in (401, 403):
            return ReponseProspect360(ResultatExport.REFUS_AUTH, r.status_code)
        if r.status_code == 429 or 500 <= r.status_code < 600:
            return ReponseProspect360(ResultatExport.RETENTABLE, r.status_code)
        return ReponseProspect360(ResultatExport.REFUS_DEFINITIF, r.status_code)
