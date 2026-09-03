"""Le contrat d'ingestion v2, tel que le producteur le lit — et rien de plus.

CE QUE CE MODULE EST
====================
La destination est `POST /api/v2/lead-ingest`, modèle strict (`extra: forbid`
partout), `consents[]` non vide avec une entrée PROCESSING accordée,
`contact.contact_type` et `attribution.campaign` requis. Ces règles sont celles
que le propriétaire des deux dépôts a figées (proposition v2, addendum du
2026-08-30, et l'ordre du 2026-09-03). Elles sont écrites ici comme un
validateur, pour qu'aucune charge ne soit jamais GELÉE sans les satisfaire :
une charge v1 gelée rejouerait 422 à chaque tentative, et l'identité frappée
ne change jamais de version.

CE QUE CE MODULE N'EST PAS
==========================
Il n'est pas le DTO de la plateforme, ni son condensé golden. Le digest golden
v2 et son arming record appartiennent au dépôt de la plateforme et n'existent
dans celui-ci sous aucune forme (mesuré le 2026-09-03 : aucun
`canonical_ingest_payload`, aucun `TestGoldenV2`, aucun `fingerprint_version`
dans `app/`, `tests/`, `config/`). Seul un 201 de la plateforme prouve qu'une
charge est acceptée. Ce qui est prouvé ICI est plus modeste et suffit pour
armer le producteur : la charge gelée a la forme du contrat figé, et elle est
rejouée octet pour octet sous la même corrélation.

L'empreinte calculée ici (`empreinte_v2`) est l'identité PRODUCTEUR d'une
charge gelée : mêmes règles de canonicalisation que le contrat v1 documenté
(`sort_keys`, `separators`, `ensure_ascii=False`, `fingerprint_version` dans
la charge, `consents` triés par clé explicite). Elle sert à prouver qu'un
rejeu ne diverge pas ; elle ne prétend pas égaler le digest de la plateforme,
dont les normaliseurs (e-mail, téléphone E.164) sont les siens.

Aucun logger ici : la charge canonique contient le contact en clair.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ConsentChannel, ConsentPurpose

ROUTE_V2 = "/api/v2/lead-ingest"
FINGERPRINT_VERSION = 2
CONTACT_TYPE_B2C = "B2C"


class ContratV2Invalide(ValueError):
    """La charge ne satisfait pas le contrat figé : elle ne doit pas être gelée."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactV2(_Strict):
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    contact_type: Literal["B2C", "B2B"]


class ProjectV2(_Strict):
    """Les sept champs Solar de DEC-P5A-QUAL-03 : quatre requis, trois
    facultatifs qui restent ABSENTS quand ils n'ont pas été répondus."""
    owner_status: str = Field(min_length=1, max_length=32)
    property_type: str = Field(min_length=1, max_length=32)
    postcode: str = Field(min_length=1, max_length=16)
    project_timeframe: str = Field(min_length=1, max_length=32)
    roof_type: str | None = Field(default=None, max_length=32)
    roof_orientation: str | None = Field(default=None, max_length=32)
    annual_consumption_kwh: int | None = Field(default=None, ge=0, le=1_000_000)


class ConsentV2(_Strict):
    purpose: Literal["PROCESSING", "FOLLOWUP_CONTACT", "MARKETING",
                     "PARTNER_TRANSFER"]
    channel: Literal["PHONE", "WHATSAPP", "EMAIL", "SMS"] | None
    granted: bool
    text_version: str = Field(min_length=1, max_length=64)
    timestamp: str = Field(min_length=20, max_length=40)
    source: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _processing_is_always_granted(self) -> "ConsentV2":
        # Il n'existe aucun moyen d'envoyer `PROCESSING granted: false` : un
        # lead sans consentement au traitement n'existe pas (règle v1, gardée).
        if self.purpose == ConsentPurpose.PROCESSING.value and not self.granted:
            raise ValueError("PROCESSING consent can only be granted")
        return self


class AttributionV2(_Strict):
    source: str | None = Field(default=None, max_length=255)
    source_detail: str | None = Field(default=None, max_length=255)
    landing_page: str | None = Field(default=None, max_length=512)
    content_id: str | None = Field(default=None, max_length=64)
    # BCP-47 langue-marché : le marché vient du site, pas du visiteur.
    locale: str = Field(pattern=r"^[a-z]{2}-[A-Z]{2}$")
    search_intent: str | None = Field(default=None, max_length=32)
    keyword_cluster: str | None = Field(default=None, max_length=255)
    utm_source: str | None = Field(default=None, max_length=255)
    utm_medium: str | None = Field(default=None, max_length=255)
    utm_campaign: str | None = Field(default=None, max_length=255)
    utm_content: str | None = Field(default=None, max_length=255)
    utm_term: str | None = Field(default=None, max_length=255)
    cta: str | None = Field(default=None, max_length=64)
    conversion_type: str = Field(min_length=1, max_length=64)
    # Identifiant de campagne côté plateforme. Configuration du site, jamais
    # une entrée visiteur. Requis : sans lui la plateforme refuse (422).
    campaign: str = Field(min_length=1, max_length=255)


class ChargeV2(_Strict):
    external_correlation_id: str = Field(min_length=1, max_length=128)
    source_system: str = Field(min_length=1, max_length=64)
    contact: ContactV2
    project: ProjectV2
    consents: list[ConsentV2] = Field(min_length=1)
    attribution: AttributionV2

    @field_validator("consents")
    @classmethod
    def _one_case_per_purpose_and_channel(cls, consents: list[ConsentV2]):
        vus: set[tuple[str, str | None]] = set()
        for c in consents:
            cle = (c.purpose, c.channel)
            if cle in vus:
                raise ValueError(f"duplicate consent case {cle}")
            vus.add(cle)
        if not any(c.purpose == ConsentPurpose.PROCESSING.value and c.granted
                   for c in consents):
            raise ValueError("consents[] must carry a granted PROCESSING entry")
        return consents


def cle_de_tri(consent: dict[str, Any]) -> tuple[str, bool, str]:
    """L'ordre canonique de `consents[]` — addendum §1 : une entrée sans canal
    précède les entrées canalisées de la même finalité."""
    canal = consent.get("channel")
    return (str(consent.get("purpose")), canal is not None, canal or "")


def valider_charge_v2(charge: dict[str, Any]) -> ChargeV2:
    """Lève `ContratV2Invalide` si la charge ne peut pas être déposée en v2."""
    try:
        return ChargeV2.model_validate(charge)
    except ValueError as exc:  # pydantic.ValidationError est une ValueError
        raise ContratV2Invalide(str(exc)) from exc


def version_de_charge(charge: dict[str, Any] | None) -> int | None:
    """La version d'une charge gelée, lue sur sa forme : le v1 porte un bloc
    `consent`, le v2 un tableau `consents`. Le corps ne porte aucun champ de
    version (addendum §3), donc la forme est le seul témoin."""
    if not charge:
        return None
    if "consents" in charge and "consent" not in charge:
        return 2
    if "consent" in charge and "consents" not in charge:
        return 1
    return None


def route_est_v2(url: str | None) -> bool:
    """Le discriminant du contrat est l'URL (addendum §3)."""
    chemin = urlsplit((url or "").strip()).path.rstrip("/")
    return chemin.endswith(ROUTE_V2)


_OPTIONNELS_CONTACT = ("first_name", "last_name", "phone", "job_title")
_OPTIONNELS_PROJET = ("roof_type", "roof_orientation", "annual_consumption_kwh")
_OPTIONNELS_ATTRIBUTION = ("source", "source_detail", "landing_page",
                           "content_id", "search_intent", "keyword_cluster",
                           "utm_source", "utm_medium", "utm_campaign",
                           "utm_content", "utm_term", "cta")


def _vide_vers_none(valeur: Any) -> Any:
    # Absent ≡ null ≡ "" pour les optionnels — trois orthographes d'un même
    # « je n'ai pas cette valeur » ne font pas trois empreintes.
    return None if valeur == "" else valeur


def canonical_ingest_payload_v2(charge: dict[str, Any]) -> bytes:
    """La charge v2 sous forme canonique : jeu de clés fixe, optionnels
    explicitement `null`, `consents` triés par clé explicite,
    `fingerprint_version` dans la charge. Jamais éditée : une nouvelle règle
    est une fonction `_v3` à côté."""
    valide = valider_charge_v2(charge)
    contact = {k: _vide_vers_none(getattr(valide.contact, k))
               for k in ("first_name", "last_name", "email", "phone",
                         "job_title", "contact_type")}
    projet = {k: _vide_vers_none(getattr(valide.project, k))
              for k in ("owner_status", "property_type", "postcode",
                        "project_timeframe", *_OPTIONNELS_PROJET)}
    consents = sorted(
        ({"purpose": c.purpose, "channel": c.channel, "granted": c.granted,
          "text_version": c.text_version, "timestamp": c.timestamp,
          "source": _vide_vers_none(c.source)} for c in valide.consents),
        key=cle_de_tri)
    attribution = {k: _vide_vers_none(getattr(valide.attribution, k))
                   for k in (*_OPTIONNELS_ATTRIBUTION, "locale",
                             "conversion_type", "campaign")}
    canonique = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "external_correlation_id": valide.external_correlation_id,
        "source_system": valide.source_system,
        "contact": contact, "project": projet, "consents": consents,
        "attribution": attribution,
    }
    return json.dumps(canonique, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def empreinte_v2(charge: dict[str, Any]) -> str:
    """SHA-256 hexadécimal (64 caractères) de la charge canonique v2."""
    return hashlib.sha256(canonical_ingest_payload_v2(charge)).hexdigest()
