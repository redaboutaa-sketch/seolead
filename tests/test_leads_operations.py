"""`seolead leads show` / `leads followup` — la sortie opérateur des leads.

Le cas réel qui a exigé ces commandes : le lead 6b062901, capturé le
2026-08-31 à 09:14 AVANT la configuration SMTP, donc jamais notifié.
`leads report` le signale (c'est son travail) mais masque volontairement
les coordonnées ; `leads list` aussi. Il manquait l'acte délibéré : afficher
UN lead nommé pour le rappeler, puis consigner que le rappel humain a eu
lieu pour que la liste de rappel se vide au lieu de devenir du bruit.

Aucune donnée personnelle réelle ici : tout est fixture.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.enums import ConversionType
from app.db.base import Base
from app.models import CapturedLead, Site, Vertical

LEAD_A = uuid.UUID("6b062901-0000-4000-8000-000000000001")
LEAD_B = uuid.UUID("6b062902-0000-4000-8000-000000000002")


@pytest_asyncio.fixture
async def cli_db(monkeypatch):
    """Une base en mémoire branchée là où les commandes CLI la cherchent."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.cli.get_sessionmaker", lambda: maker)

    async with maker() as session:
        vertical = Vertical(code="SOLAR_BE", name="Solar", market="BE",
                            default_language="fr", active=True)
        session.add(vertical)
        await session.flush()
        site = Site(vertical_id=vertical.id, name="solar_be", domain=None,
                    market="BE", default_language="fr", status="PLANNED")
        session.add(site)
        await session.flush()
        for lead_id, email, state in (
                (LEAD_A, "ada.lovelace@example.test", None),
                (LEAD_B, "grace.hopper@example.test", "SENT")):
            session.add(CapturedLead(
                id=lead_id, site_id=site.id, vertical_code="SOLAR_BE",
                conversion_type=ConversionType.ESTIMATE_REQUEST.value,
                email=email, phone="+32 470 12 34 56", language="fr",
                first_name="Test", last_name="Fixture",
                qualification={"postcode": "1000"},
                notification_state=state,
                created_at=datetime.now(timezone.utc)))
        await session.commit()
    yield maker
    await engine.dispose()


def _last_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


@pytest.mark.asyncio
async def test_show_gives_the_full_contact_for_a_deliberate_call(
        cli_db, capsys):
    from app.cli import cmd_leads_show
    # Le préfixe court est exactement ce qu'un opérateur copie d'un report.
    rc = await cmd_leads_show(argparse.Namespace(lead_id="6b062901"))
    out = _last_json(capsys)
    assert rc == 0
    assert out["email"] == "ada.lovelace@example.test"  # PAS masqué : c'est le point
    assert out["phone"] == "+32 470 12 34 56"
    assert out["notification_state"] == "UNRECORDED"
    assert "jamais" in out["note"]  # l'avertissement PII fait partie de la sortie


@pytest.mark.asyncio
async def test_an_ambiguous_prefix_refuses_rather_than_guessing(
        cli_db, capsys):
    from app.cli import cmd_leads_show
    # "6b0629" matche les deux fixtures : deviner ici, c'est appeler la
    # mauvaise personne avec les données d'une autre.
    rc = await cmd_leads_show(argparse.Namespace(lead_id="6b0629"))
    out = _last_json(capsys)
    assert rc == 1
    assert out["status"] == "AMBIGUOUS"
    assert len(out["matches"]) == 2
    # Et l'introuvable est un échec loud, pas un JSON vide.
    rc = await cmd_leads_show(argparse.Namespace(lead_id=str(uuid.uuid4())))
    assert rc == 1
    assert _last_json(capsys)["status"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_followup_recorded_by_a_human_empties_the_callback_list(
        cli_db, capsys):
    from app.cli import cmd_leads_followup, cmd_leads_report
    # Avant : le lead jamais notifié est dans la liste de rappel, avec son âge.
    await cmd_leads_report(argparse.Namespace())
    before = _last_json(capsys)
    pending = [l["lead_id"] for l in before["needs_manual_followup"]]
    assert str(LEAD_A) in pending
    assert str(LEAD_B) not in pending  # SENT n'attend personne
    assert before["needs_manual_followup"][0]["age_hours"] is not None

    rc = await cmd_leads_followup(argparse.Namespace(
        lead_id="6b062901", by="owner", note="rappel effectué, RDV pris"))
    recorded = _last_json(capsys)
    assert rc == 0
    assert recorded["previous_notification_state"] == "UNRECORDED"

    # Après : la liste se vide — sinon elle devient du bruit et plus personne
    # ne la lit ; et le marquage porte qui/quand/pourquoi sur le lead.
    await cmd_leads_report(argparse.Namespace())
    after = _last_json(capsys)
    assert str(LEAD_A) not in [
        l["lead_id"] for l in after["needs_manual_followup"]]
    assert after["notifications"].get("MANUAL_FOLLOWUP_DONE") == 1

    async with cli_db() as session:
        lead = await session.get(CapturedLead, LEAD_A)
        assert lead.notification_state == "MANUAL_FOLLOWUP_DONE"
        assert lead.notified_at is not None
        assert lead.qualification["_manual_followup"]["recorded_by"] == "owner"
        # Les réponses de qualification d'origine ne sont pas écrasées.
        assert lead.qualification["postcode"] == "1000"
