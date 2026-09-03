"""Contrat d'ingestion v2 — le producteur l'émet, et le prouve (2026-09-03).

Point bloquant du propriétaire : « quel contrat `leads export` émet-il
aujourd'hui ? » Mesuré dans le code avant ce commit : v1 (`construire_charge`,
bloc `consent`, pas de `contact_type`, pas de `campaign`). Une charge v1 gelée
rejouerait 422 à chaque tentative sur `/api/v2/lead-ingest`.

Ce fichier prouve, sans qu'aucune requête ne quitte le processus :
1. la charge GELÉE pour un lead aux consentements enregistrés est une charge
   v2 valide contre le contrat figé (modèle strict, `consents[]` non vide avec
   PROCESSING accordé, `contact_type`, `attribution.campaign`) ;
2. la corrélation `sl-<uuid4>` et l'empreinte tiennent sur un rejeu : même
   corrélation, corps octet pour octet identique, 200 REPLAY ;
3. une charge v1 gelée n'est jamais déposée sur la route v2 ;

Le digest golden v2 de la PLATEFORME n'existe pas dans ce dépôt ; celui
épinglé ici est l'identité producteur d'une charge synthétique gelée.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.enums import LeadState
from app.models import CapturedLead, LeadConsent
from app.services import lead_export
from app.site import prospect360_contract_v2 as contrat
from app.site.config import ExportConfig, load_site
from app.site.prospect360_destination import (ResultatExport,
                                              construire_charge,
                                              construire_charge_v2)
from tests.test_lead_export import (CAMPAGNE, FauxProspect360, _capturer,
                                    _config, _destination, _exporter,
                                    _settings, solar_site)  # noqa: F401


async def _consents(session, lead) -> list[LeadConsent]:
    return list((await session.execute(
        select(LeadConsent).where(LeadConsent.captured_lead_id == lead.id)
        .order_by(LeadConsent.consent_key))).scalars().all())


# ── 1 — ce que le producteur émet ───────────────────────────────────────────

@pytest.mark.asyncio
class TestLeProducteurEmetLeV2:

    async def test_la_charge_gelee_est_une_charge_v2_valide(self, session,
                                                            solar_site):
        lead = await _capturer(session, solar_site)
        assert await _consents(session, lead), "le formulaire enregistre ses cases"
        await lead_export.preparer_identite_export(session, lead, config=_config())
        charge = lead.export_payload
        assert contrat.version_de_charge(charge) == 2
        # Valide contre le contrat figé — ou le test lève.
        valide = contrat.valider_charge_v2(charge)
        assert valide.contact.contact_type == "B2C"
        assert valide.attribution.campaign == CAMPAGNE
        assert valide.attribution.locale == "fr-BE"
        assert "consent" not in charge, "le bloc v1 ne voyage plus"
        assert charge["source_system"] == "seo_lead_factory"

    async def test_consents_porte_les_cases_offertes_triees(self, session,
                                                            solar_site):
        lead = await _capturer(session, solar_site)
        lignes = await _consents(session, lead)
        await lead_export.preparer_identite_export(session, lead, config=_config())
        cas = lead.export_payload["consents"]
        assert len(cas) == len(lignes) >= 1
        processing = [c for c in cas if c["purpose"] == "PROCESSING"]
        assert processing and processing[0]["granted"] is True
        assert processing[0]["channel"] is None
        assert processing[0]["text_version"] == lead.consent_version
        assert processing[0]["timestamp"].endswith("Z")
        # Tri par clé explicite : sans canal avant canalisé, puis par canal.
        assert [contrat.cle_de_tri(c) for c in cas] == sorted(
            contrat.cle_de_tri(c) for c in cas)
        # Les refus voyagent (addendum §4) : une case refusée est une entrée.
        assert all(isinstance(c["granted"], bool) for c in cas)

    async def test_un_lead_d_avant_la_migration_0008_projette_le_processing_legal(
            self, session, solar_site):
        """Aucune ligne `lead_consent` : le consentement au traitement, prouvé
        par l'existence du lead et porté par les colonnes historiques, devient
        UNE entrée PROCESSING. Rien d'autre n'est inventé."""
        lead = await _capturer(session, solar_site)
        for ligne in await _consents(session, lead):
            await session.delete(ligne)
        await session.flush()
        await lead_export.preparer_identite_export(session, lead, config=_config())
        cas = lead.export_payload["consents"]
        assert len(cas) == 1
        assert cas[0]["purpose"] == "PROCESSING" and cas[0]["granted"] is True
        assert cas[0]["text_version"] == lead.consent_version
        contrat.valider_charge_v2(lead.export_payload)

    async def test_sans_campagne_rien_n_est_frappe_ni_gele(self, session,
                                                          solar_site):
        """Le YAML ne porte pas encore de campagne : la vraie configuration du
        site refuse, avant tout HTTP, et le lead reste intact."""
        lead = await _capturer(session, solar_site)
        assert load_site("solar_be").export.prospect360_campaign is None
        with pytest.raises(lead_export.ExportRefuse, match="campaign"):
            await lead_export.preparer_identite_export(
                session, lead, config=load_site("solar_be"))
        assert lead.external_correlation_id is None
        assert lead.export_payload is None
        assert lead.state == LeadState.PENDING_EXPORT.value

    async def test_une_charge_invalide_n_est_jamais_gelee(self, session,
                                                          solar_site,
                                                          monkeypatch):
        """Mutation : si la construction produisait une charge hors contrat,
        la validation à la frappe la refuserait — aucune corrélation, aucune
        charge en base."""
        lead = await _capturer(session, solar_site)

        def cassee(*a, **k):
            charge = construire_charge_v2(*a, **k)
            charge["contact"].pop("contact_type")
            return charge
        monkeypatch.setattr(lead_export, "construire_charge_v2", cassee)
        with pytest.raises(lead_export.ExportRefuse, match="contract v2"):
            await lead_export.preparer_identite_export(session, lead,
                                                       config=_config())
        assert lead.external_correlation_id is None
        assert lead.export_payload is None

    async def test_la_route_v1_est_refusee_avant_toute_frappe(self, session,
                                                             solar_site):
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()
        with pytest.raises(lead_export.ExportRefuse, match="v2 route"):
            await _exporter(session, lead, faux,
                            PROSPECT360_INGEST_URL="https://p360.invalid/api/v1/lead-ingest")
        assert faux.recu == [] and lead.export_payload is None


_ABSENT = object()

CHARGE_SYNTHETIQUE = {
    "external_correlation_id": "sl-00000000-0000-4000-8000-000000000001",
    "source_system": "seo_lead_factory",
    "contact": {"first_name": "Ada", "last_name": "Lovelace",
                "email": "ada.lovelace@example.test", "phone": "+32470123456",
                "job_title": None, "contact_type": "B2C"},
    "project": {"owner_status": "OWNER", "property_type": "HOUSE",
                "postcode": "1000", "project_timeframe": "LT_6M",
                "roof_type": "PITCHED", "roof_orientation": "SOUTH",
                "annual_consumption_kwh": 4200},
    "consents": [
        {"purpose": "PROCESSING", "channel": None, "granted": True,
         "text_version": "solar-be-consent-v1.1-2026-08-31",
         "timestamp": "2026-09-01T09:00:00Z", "source": "/demande-etude"},
        {"purpose": "FOLLOWUP_CONTACT", "channel": "PHONE", "granted": True,
         "text_version": "solar-be-followup-contact-v1.0-2026-08-30",
         "timestamp": "2026-09-01T09:00:00Z", "source": "/demande-etude"},
        {"purpose": "FOLLOWUP_CONTACT", "channel": "WHATSAPP", "granted": False,
         "text_version": "solar-be-followup-contact-v1.0-2026-08-30",
         "timestamp": "2026-09-01T09:00:00Z", "source": "/demande-etude"},
        {"purpose": "MARKETING", "channel": "WHATSAPP", "granted": False,
         "text_version": "solar-be-marketing-whatsapp-v1.0-2026-08-30",
         "timestamp": "2026-09-01T09:00:00Z", "source": "/demande-etude"},
        {"purpose": "PARTNER_TRANSFER", "channel": None, "granted": True,
         "text_version": "solar-be-partner-transfer-v1.0-2026-08-30",
         "timestamp": "2026-09-01T09:00:00Z", "source": "/demande-etude"},
    ],
    "attribution": {"source": "google", "source_detail": "organic",
                    "landing_page": "/prix-panneaux-solaires",
                    "content_id": None, "locale": "fr-BE",
                    "search_intent": "COMMERCIAL", "keyword_cluster": "prix",
                    "utm_source": "google", "utm_medium": "organic",
                    "utm_campaign": "prix-solaire", "utm_content": "hero",
                    "utm_term": "prix panneaux", "cta": "ESTIMATE_REQUEST",
                    "conversion_type": "ESTIMATE_REQUEST",
                    "campaign": "solar-be-2026-q4"},
}


# ── 2 — le contrat figé, tel que le producteur le lit ───────────────────────

class TestContratFige:
    def _charge(self, **maj) -> dict:
        charge = json.loads(json.dumps(CHARGE_SYNTHETIQUE))
        for chemin, valeur in maj.items():
            cible = charge
            *parents, feuille = chemin.split(".")
            for p in parents:
                cible = cible[p]
            if valeur is _ABSENT:
                cible.pop(feuille)
            else:
                cible[feuille] = valeur
        return charge

    def test_la_charge_synthetique_est_valide(self):
        contrat.valider_charge_v2(self._charge())

    @pytest.mark.parametrize("mutation", [
        {"contact.contact_type": _ABSENT},
        {"attribution.campaign": _ABSENT},
        {"attribution.campaign": ""},
        {"consents": []},
        {"attribution.locale": "fr"},
        {"contact.extra": "x"},
        {"tenant_id": "t"},
        {"consent": {"processing": True}},
    ])
    def test_ce_que_le_contrat_refuse(self, mutation):
        with pytest.raises(contrat.ContratV2Invalide):
            contrat.valider_charge_v2(self._charge(**mutation))

    def test_processing_ne_peut_pas_etre_refuse(self):
        charge = self._charge()
        charge["consents"][0]["granted"] = False
        with pytest.raises(contrat.ContratV2Invalide, match="PROCESSING"):
            contrat.valider_charge_v2(charge)

    def test_sans_processing_pas_de_charge(self):
        charge = self._charge()
        charge["consents"] = [c for c in charge["consents"]
                              if c["purpose"] != "PROCESSING"]
        with pytest.raises(contrat.ContratV2Invalide, match="PROCESSING"):
            contrat.valider_charge_v2(charge)

    def test_un_doublon_purpose_channel_est_refuse(self):
        charge = self._charge()
        charge["consents"].append(dict(charge["consents"][0]))
        with pytest.raises(contrat.ContratV2Invalide, match="duplicate"):
            contrat.valider_charge_v2(charge)

    def test_la_route_est_le_discriminant(self):
        assert contrat.route_est_v2("https://p360.example/api/v2/lead-ingest")
        assert contrat.route_est_v2("https://p360.example/api/v2/lead-ingest/")
        assert not contrat.route_est_v2("https://p360.example/api/v1/lead-ingest")
        assert not contrat.route_est_v2("")
        assert not contrat.route_est_v2(None)

    def test_la_version_se_lit_sur_la_forme(self):
        assert contrat.version_de_charge(self._charge()) == 2
        assert contrat.version_de_charge({"consent": {}}) == 1
        assert contrat.version_de_charge({"consent": {}, "consents": []}) is None
        assert contrat.version_de_charge(None) is None


# ── 3 — l'empreinte producteur et son golden ────────────────────────────────

class TestGoldenV2Producteur:
    """Épingle le digest ET les octets canoniques d'une requête synthétique
    gelée — même discipline que `TestGoldenV1` côté plateforme. Un changement
    silencieux de la canonicalisation v2 met la suite au rouge. Ce digest est
    celui du PRODUCTEUR : le golden de la plateforme est le sien."""

    CONDENSE = "ed33052f4994ce7da7cdf6142c8b27d747d26f8af9aeb8781bfebf4161431b11"
    OCTETS_PREFIXE = b'{"attribution":{"campaign":"solar-be-2026-q4"'

    def test_le_digest_est_epingle(self):
        assert contrat.empreinte_v2(CHARGE_SYNTHETIQUE) == self.CONDENSE

    def test_les_octets_canoniques_sont_epingles(self):
        octets = contrat.canonical_ingest_payload_v2(CHARGE_SYNTHETIQUE)
        assert octets.startswith(self.OCTETS_PREFIXE)
        assert b'"fingerprint_version":2' in octets
        assert len(contrat.empreinte_v2(CHARGE_SYNTHETIQUE)) == 64

    def test_l_ordre_des_cases_ne_change_pas_l_empreinte(self):
        melangee = json.loads(json.dumps(CHARGE_SYNTHETIQUE))
        melangee["consents"].reverse()
        assert contrat.empreinte_v2(melangee) == self.CONDENSE

    def test_absent_null_et_vide_font_une_seule_empreinte(self):
        a = json.loads(json.dumps(CHARGE_SYNTHETIQUE))
        b = json.loads(json.dumps(CHARGE_SYNTHETIQUE))
        a["attribution"]["content_id"] = ""
        b["attribution"].pop("content_id")
        assert contrat.empreinte_v2(a) == contrat.empreinte_v2(b) == self.CONDENSE

    def test_un_refus_de_plus_est_une_autre_empreinte(self):
        autre = json.loads(json.dumps(CHARGE_SYNTHETIQUE))
        autre["consents"][4]["granted"] = False
        assert contrat.empreinte_v2(autre) != self.CONDENSE

    def test_aucun_logger_dans_le_module(self):
        import inspect
        source = inspect.getsource(contrat)
        assert "import logging" not in source and "getLogger" not in source


# ── 4 — corrélation et empreinte tiennent sur un rejeu ──────────────────────

@pytest.mark.asyncio
class TestRejeu:

    async def test_le_rejeu_reenvoie_les_memes_octets_sous_la_meme_correlation(
            self, session, solar_site):
        """Accusé perdu → rejeu : même `sl-<uuid4>`, corps identique octet pour
        octet, même empreinte producteur, 200 REPLAY avec le prospect
        d'origine, et EXPORTED une seule fois."""
        lead = await _capturer(session, solar_site)
        corps: list[bytes] = []

        class Espion(FauxProspect360):
            def _repondre(self, request):
                corps.append(bytes(request.content))
                return super()._repondre(request)

        # Première tentative : la plateforme ACCEPTE et enregistre le dépôt,
        # puis l'accusé se perd en route (500 vu du producteur).
        class AccuseEgare(Espion):
            def _repondre(self, request):
                reponse = super()._repondre(request)
                if len(corps) == 1:
                    return httpx.Response(500, json={"error": "perdu"})
                return reponse

        perdu = AccuseEgare()
        r1 = await _exporter(session, lead, perdu)
        assert perdu.depots, "le dépôt a bien été enregistré en face"
        assert r1.resultat == ResultatExport.RETENTABLE
        assert lead.state == LeadState.PENDING_EXPORT.value
        correlation = lead.external_correlation_id
        assert correlation.startswith("sl-")
        uuid.UUID(correlation[3:], version=4)
        empreinte = contrat.empreinte_v2(lead.export_payload)

        # La ligne bouge entre-temps : la charge gelée ne doit pas la suivre.
        lead.first_name = "Modifiée"
        await session.flush()

        sain = Espion()
        sain.depots = dict(perdu.depots); sain.prospects = dict(perdu.prospects)
        r2 = await _exporter(session, lead, sain)
        assert r2.resultat == ResultatExport.REJEU and r2.http_status == 200
        assert lead.state == LeadState.EXPORTED.value
        assert lead.external_correlation_id == correlation
        assert corps[0] == corps[1]
        assert contrat.empreinte_v2(json.loads(corps[1])) == empreinte
        assert r2.prospect_id == perdu.prospects[correlation]

    async def test_une_charge_v1_gelee_n_est_jamais_deposee_sur_la_route_v2(
            self, session, solar_site):
        """Une identité frappée ne change jamais de version, et la route est
        v2 : la charge v1 n'est pas envoyée (elle ferait 422 pour toujours),
        pas re-frappée, et le lead reste en attente d'un humain."""
        lead = await _capturer(session, solar_site)
        correlation = f"sl-{uuid.uuid4()}"
        lead.external_correlation_id = correlation
        lead.export_payload = construire_charge(lead, correlation_id=correlation,
                                                consent_version="v1")
        await session.flush(); await session.commit()
        faux = FauxProspect360()
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.CONTRAT_PERIME
        assert faux.recu == []
        assert lead.external_correlation_id == correlation
        assert lead.state == LeadState.PENDING_EXPORT.value
        assert lead.export_error.startswith("STALE_CONTRACT")
