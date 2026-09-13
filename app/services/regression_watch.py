"""La veille de régression — ce que la page SERT contre ce que le système PRODUIRAIT.

POURQUOI ELLE EXISTE
====================
Le 10 septembre 2026, la page prix affichait « 1 € – 12 € par watt-crête » pour
une source qui dit 1 à 1,2 €, et « 10 000 € » pour une source qui dit 6 000 à
10 000 €. Les deux étaient en ligne depuis le 13 août. Personne ne les a vus
pendant quatre semaines, parce que rien ne relisait les pages publiées : les
gardes s'exécutent au moment du jugement, et une page franchie reste franchie.

Une page publiée est pourtant un instantané GELÉ, tandis que les règles, elles,
continuent d'avancer. Sept correctifs ont été fusionnés en douze jours ; chacun
a rendu vrai quelque chose qui ne l'était pas, et aucun n'a touché ce qui était
déjà en ligne. L'écart entre les deux est exactement ce que cette veille mesure.

CE QU'ELLE FAIT, ET CE QU'ELLE NE FAIT PAS
==========================================
Deux questions, posées chaque nuit sur chaque page publiée :

  PORTE   — le brouillon derrière cette page passerait-il la porte d'aujourd'hui ?
  DÉRIVE  — ce que la page sert est-il encore ce que les règles d'aujourd'hui
            rendraient du même brouillon ?

Elle n'écrit rien, ne publie rien, n'approuve rien et n'appelle aucun
fournisseur. Elle lit et elle rapporte. Corriger reste un acte humain qui passe
par la porte — c'est la règle que l'article du 31 août a coûté cher à établir,
et une veille qui s'autoriserait à republier la démonterait.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PublicationState
from app.models import ContentDraft, PublishedContent

logger = logging.getLogger(__name__)

CONSTAT_PORTE = "GATE"
CONSTAT_DERIVE = "DRIFT"
CONSTAT_ORPHELIN = "ORPHAN"


@dataclass(frozen=True)
class Constat:
    """Une page publiée, et ce qui ne va plus avec elle."""

    slug: str
    locale: str
    content_id: str
    version: int
    kind: str
    detail: str

    def as_dict(self) -> dict:
        return {"slug": self.slug, "locale": self.locale,
                "content_id": self.content_id, "version": self.version,
                "kind": self.kind, "detail": self.detail}


@dataclass
class RapportVeille:
    checked: int = 0
    # Les pages écrites à la main n'ont pas de brouillon derrière elles : il n'y
    # a rien à re-juger, et les compter comme des constats noierait les vrais.
    unwatched: list[str] = field(default_factory=list)
    findings: list[Constat] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {"status": "CLEAN" if self.ok else "REGRESSIONS",
                "checked": self.checked, "unwatched": self.unwatched,
                "findings": [c.as_dict() for c in self.findings]}


async def veiller(session: AsyncSession, *, site_id: uuid.UUID) -> RapportVeille:
    """Relire toutes les pages vivantes d'un site. Lecture seule."""
    from app.site.publication import (compute_fingerprint, evaluate_gate,
                                      snapshot_fingerprint)

    rapport = RapportVeille()
    vivantes = (await session.execute(
        select(PublishedContent)
        .where(PublishedContent.site_id == site_id,
               PublishedContent.state == PublicationState.PUBLISHED.value)
        .order_by(PublishedContent.slug))).scalars().all()

    for snapshot in vivantes:
        if snapshot.content_draft_id is None:
            rapport.unwatched.append(snapshot.slug)
            continue
        rapport.checked += 1
        draft = await session.get(ContentDraft, snapshot.content_draft_id)
        if draft is None:
            rapport.findings.append(_constat(
                snapshot, CONSTAT_ORPHELIN,
                "la page est en ligne mais son brouillon n'existe plus : "
                "rien ne peut être re-jugé ni recalculé"))
            continue

        gate = await evaluate_gate(session, draft)
        if not gate.passed:
            rapport.findings.append(_constat(
                snapshot, CONSTAT_PORTE,
                "cette page ne passerait plus la porte d'aujourd'hui : "
                + " ; ".join(gate.reasons)))

        try:
            attendu, _ = await compute_fingerprint(session, draft)
        except Exception as exc:  # noqa: BLE001 — un brief manquant, par ex.
            rapport.findings.append(_constat(
                snapshot, CONSTAT_DERIVE,
                f"le rendu d'aujourd'hui ne peut pas être calculé : {exc}"))
            continue

        servi = snapshot_fingerprint(snapshot)
        if servi != attendu:
            rapport.findings.append(_constat(
                snapshot, CONSTAT_DERIVE,
                f"la page sert le rendu {servi[:12]}… alors que les règles "
                f"d'aujourd'hui produiraient {attendu[:12]}… : relire, "
                f"ré-approuver sur la nouvelle empreinte, republier"))

    logger.info("regression watch", extra={"checked": rapport.checked,
                                           "findings": len(rapport.findings)})
    return rapport


def _constat(snapshot: PublishedContent, kind: str, detail: str) -> Constat:
    return Constat(slug=snapshot.slug, locale=snapshot.locale,
                   content_id=str(snapshot.id), version=snapshot.version,
                   kind=kind, detail=detail)
