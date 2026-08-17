"""TR-SL-01 — exporting a captured lead to Prospect 360.

NO REQUEST IN THIS FILE LEAVES THE PROCESS. Every test drives an
`httpx.MockTransport` standing in for Prospect 360. That is not only a speed
choice: this suite runs in CI, and a production tenant holding real people's
contact details is not a fixture.

The test that matters most is the crash window — remote accepted, local
acknowledgement lost. It is the one failure that silently duplicates a person in
a CRM, and the only thing standing between us and it is that a retry replays the
same correlation with the same frozen payload.
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import Settings
from app.core.enums import ConversionType, LeadState
from app.models import CapturedLead, Site, Vertical
from app.services import lead_export
from app.site.config import load_site
from app.site.lead_capture import LeadSubmission, capture_lead
from app.site.prospect360_destination import (SOURCE_SYSTEM,
                                              Prospect360Destination,
                                              ResultatExport,
                                              construire_charge)
from app.site.spam_protection import AcceptAllSpamProtection, SubmissionSignals

QUALIFICATION = {
    "owner_status": "OWNER", "postcode": "1000", "property_type": "HOUSE",
    "project_timeframe": "LT_6M", "roof_type": "PITCHED",
    "roof_orientation": "SOUTH", "annual_consumption_kwh": 4200,
    # Exclus par le contrat : présents localement, ils ne doivent PAS partir.
    "monthly_bill_eur": 180, "battery_interest": True,
}

ATTRIBUTION = {
    "landing_path": "/prix-panneaux-solaires", "page_path": "/demande-etude",
    "channel": "organic", "source": "google",
    "utm_source": "google", "utm_medium": "organic",
    "utm_campaign": "prix-solaire", "utm_content": "hero",
    "utm_term": "prix panneaux", "search_intent": "COMMERCIAL",
    "keyword_cluster": "prix",
}

SECRET = "sa_0123456789abcdef.tres-secret-qui-ne-doit-jamais-fuir"


def _settings(**o) -> Settings:
    base = dict(PROSPECT360_INGEST_URL="https://p360.invalid/api/v1/lead-ingest",
                PROSPECT360_CREDENTIAL=SECRET, PROSPECT360_TIMEOUT_SECONDS=5)
    base.update(o)
    return Settings(**base)


@pytest_asyncio.fixture
async def solar_site(session) -> Site:
    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    site = Site(vertical_id=vertical.id, name="solar_be", domain=None,
                market="BE", default_language="fr", status="PLANNED")
    session.add(site)
    await session.flush()
    return site


async def _capturer(session, site) -> CapturedLead:
    await capture_lead(
        session,
        submission=LeadSubmission(
            site_id="solar_be",
            conversion_type=ConversionType.ESTIMATE_REQUEST.value,
            email="ada.lovelace@example.test", language="fr",
            first_name="Ada", last_name="Lovelace", phone="+32 470 12 34 56",
            postcode="1000", qualification=dict(QUALIFICATION),
            consent_processing=True, consent_marketing=False,
            attribution=dict(ATTRIBUTION),
            signals=SubmissionSignals(elapsed_ms=45_000)),
        site=site, config=load_site("solar_be"), vertical_code="SOLAR_BE",
        spam=AcceptAllSpamProtection())
    return (await session.execute(select(CapturedLead))).scalar_one()


class FauxProspect360:
    """Prospect 360, en mémoire, avec la sémantique d'exactement-une-fois.

    Il applique la VRAIE règle : même corrélation + même charge → REPLAY ; même
    corrélation + charge différente → CONFLIT. Un faux qui rendrait 201 à chaque
    fois ne prouverait rien du tout.
    """

    def __init__(self, *, statuts: list[int] | None = None,
                 exception: Exception | None = None) -> None:
        self.depots: dict[str, str] = {}     # correlation → empreinte de charge
        self.prospects: dict[str, str] = {}  # correlation → prospect_id
        self.recu: list[dict] = []
        self.entetes: list[dict] = []
        self._statuts = list(statuts or [])
        self._exception = exception
        self._n = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._repondre)

    def _repondre(self, request: httpx.Request) -> httpx.Response:
        self._n += 1
        if self._exception is not None:
            raise self._exception
        if self._statuts:
            forcé = self._statuts.pop(0)
            if forcé not in (200, 201, 409):
                return httpx.Response(forcé, json={"error": "forcé"})

        charge = json.loads(request.content)
        self.recu.append(charge)
        self.entetes.append(dict(request.headers))

        correlation = charge["external_correlation_id"]
        empreinte = json.dumps(charge, sort_keys=True, separators=(",", ":"))
        if correlation in self.depots:
            if self.depots[correlation] != empreinte:
                return httpx.Response(409, json={"outcome": "CONFLICT"})
            return httpx.Response(200, json={"outcome": "REPLAY",
                                             "prospect_id": self.prospects[correlation]})
        pid = f"prospect-{len(self.prospects) + 1}"
        self.depots[correlation] = empreinte
        self.prospects[correlation] = pid
        return httpx.Response(201, json={"outcome": "CREATED", "prospect_id": pid})


def _destination(faux: FauxProspect360, **o) -> Prospect360Destination:
    return Prospect360Destination(_settings(**o), transport=faux.transport())


async def _exporter(session, lead, faux, **o):
    return await lead_export.exporter_lead(
        session, lead, destination=_destination(faux, **o),
        config=load_site("solar_be"),
        max_attempts=o.pop("max_attempts", 5))


# ── 1 — la capture reste durable, quoi qu'il arrive en face ─────────────────

@pytest.mark.asyncio
class TestDurabiliteLocale:

    async def test_la_capture_ne_depend_pas_de_prospect360(self, session, solar_site):
        """DoD-1 — Prospect 360 absent ≠ lead perdu."""
        lead = await _capturer(session, solar_site)
        assert lead.state == LeadState.PENDING_EXPORT.value
        assert lead.email == "ada.lovelace@example.test"

    async def test_un_echec_reseau_laisse_le_lead_rejouable(self, session, solar_site):
        """DoD-17 — le lead reste PENDING_EXPORT et garde son identité."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360(exception=httpx.ConnectTimeout("timeout"))
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.RETENTABLE
        assert lead.state == LeadState.PENDING_EXPORT.value
        assert lead.external_correlation_id is not None
        assert lead.export_payload is not None


# ── 2 — identité d'export : frappée une fois, jamais refrappée ──────────────

@pytest.mark.asyncio
class TestIdentiteExport:

    async def test_l_identite_est_durable_avant_toute_tentative(self, session,
                                                                 solar_site):
        """DoD-2 — la corrélation existe en base AVANT le premier HTTP."""
        lead = await _capturer(session, solar_site)
        correlation = await lead_export.preparer_identite_export(
            session, lead, config=load_site("solar_be"))
        assert correlation and lead.external_correlation_id == correlation
        assert lead.export_payload["external_correlation_id"] == correlation

    async def test_la_relance_rejoue_la_meme_correlation(self, session, solar_site):
        """DoD-4 — regénérer la corrélation créerait un second prospect."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360(exception=httpx.ConnectTimeout("x"))
        await _exporter(session, lead, faux)
        premiere = lead.external_correlation_id

        sain = FauxProspect360()
        await _exporter(session, lead, sain)
        assert lead.external_correlation_id == premiere
        assert sain.recu[0]["external_correlation_id"] == premiere

    async def test_la_relance_rejoue_exactement_la_meme_charge(self, session,
                                                               solar_site):
        """DoD-5 — la charge est GELÉE, pas reconstruite depuis une ligne qui a bougé."""
        lead = await _capturer(session, solar_site)
        await lead_export.preparer_identite_export(
            session, lead, config=load_site("solar_be"))
        gelee = json.dumps(lead.export_payload, sort_keys=True)

        # La ligne locale bouge APRÈS le gel — exactement le cas qui produirait
        # un 409 si la charge était reconstruite.
        lead.first_name = "Modifiée"
        lead.qualification = {**lead.qualification, "roof_type": "FLAT"}
        await session.flush()

        faux = FauxProspect360()
        await _exporter(session, lead, faux)
        assert json.dumps(faux.recu[0], sort_keys=True) == gelee


# ── 3 — la charge canonique correspond au contrat, champ pour champ ─────────

@pytest.mark.asyncio
class TestChargeCanonique:

    async def test_la_charge_porte_exactement_les_cles_du_contrat(self, session,
                                                                  solar_site):
        """DoD-3 — `extra: forbid` en face : une clé en trop est un 422."""
        lead = await _capturer(session, solar_site)
        charge = construire_charge(lead, correlation_id="c-1",
                                   consent_version="v1")
        assert set(charge) == {"external_correlation_id", "source_system",
                               "contact", "project", "consent", "attribution"}
        assert charge["source_system"] == SOURCE_SYSTEM
        assert set(charge["contact"]) == {"first_name", "last_name", "email",
                                          "phone", "job_title"}
        assert set(charge["project"]) <= {
            "owner_status", "property_type", "postcode", "project_timeframe",
            "roof_type", "roof_orientation", "annual_consumption_kwh"}
        assert set(charge["consent"]) == {"processing", "version", "timestamp",
                                          "source"}
        assert charge["consent"]["processing"] is True

    async def test_les_champs_exclus_ne_partent_jamais(self, session, solar_site):
        """Le contrat les refuse nommément ; ils existent pourtant localement."""
        lead = await _capturer(session, solar_site)
        charge = construire_charge(lead, correlation_id="c-1", consent_version="v1")
        plat = json.dumps(charge)
        for interdit in ("monthly_bill_eur", "battery_interest", "tenant_id",
                         "service_account_id", "consent_marketing"):
            assert interdit not in plat, interdit

    async def test_une_reponse_absente_reste_absente(self, session, solar_site):
        """`UNKNOWN` est une réponse ; l'absence en est une autre."""
        lead = await _capturer(session, solar_site)
        lead.qualification = {k: v for k, v in lead.qualification.items()
                              if k != "roof_orientation"}
        charge = construire_charge(lead, correlation_id="c-1", consent_version="v1")
        assert "roof_orientation" not in charge["project"]


# ── 4 — classification des réponses ────────────────────────────────────────

@pytest.mark.asyncio
class TestReponses:

    async def test_201_exporte_et_conserve_le_prospect(self, session, solar_site):
        """DoD-6/7."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.CREE
        assert lead.state == LeadState.EXPORTED.value
        assert lead.remote_prospect_id == "prospect-1"
        assert lead.exported_at is not None

    async def test_409_n_est_jamais_un_succes(self, session, solar_site):
        """DoD-10/11/12 — et la corrélation n'est pas refrappée."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()
        await _exporter(session, lead, faux)          # 201, dépôt enregistré
        correlation = lead.external_correlation_id

        # Même corrélation, charge divergente : le faux répond 409, comme la vraie.
        lead.export_payload = {**lead.export_payload,
                               "contact": {**lead.export_payload["contact"],
                                           "first_name": "Divergente"}}
        lead.state = LeadState.PENDING_EXPORT.value
        await session.flush()
        r = await _exporter(session, lead, faux)

        assert r.resultat == ResultatExport.CONFLIT
        assert lead.state != LeadState.EXPORTED.value
        assert lead.state == LeadState.EXPORT_FAILED.value
        assert lead.external_correlation_id == correlation
        assert "CONFLICT" in (lead.export_error or "")

    @pytest.mark.parametrize("statut", [401, 403])
    async def test_401_403_arretent_la_relance(self, session, solar_site, statut):
        """DoD-13/14 — marteler avec un identifiant refusé ne le valide pas."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360(statuts=[statut])
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.REFUS_AUTH
        assert lead.state == LeadState.EXPORT_FAILED.value
        assert "UNAUTHORIZED" in lead.export_error

    @pytest.mark.parametrize("statut", [429, 500, 503])
    async def test_429_et_5xx_sont_rejouables(self, session, solar_site, statut):
        """DoD-15/16."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360(statuts=[statut])
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.RETENTABLE
        assert lead.state == LeadState.PENDING_EXPORT.value

    async def test_la_relance_est_bornee(self, session, solar_site):
        """DoD-12 — pas de boucle serrée : au plafond, on s'arrête et on le dit."""
        lead = await _capturer(session, solar_site)
        for _ in range(3):
            faux = FauxProspect360(statuts=[503])
            await _exporter(session, lead, faux, max_attempts=3)
        assert lead.export_attempts == 3
        assert lead.state == LeadState.EXPORT_FAILED.value
        assert "RETRY_EXHAUSTED" in lead.export_error

    async def test_un_4xx_inattendu_ne_boucle_pas(self, session, solar_site):
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360(statuts=[422])
        r = await _exporter(session, lead, faux)
        assert r.resultat == ResultatExport.REFUS_DEFINITIF
        assert lead.state == LeadState.EXPORT_FAILED.value


# ── 5 — LA FENÊTRE DE PANNE : accepté en face, perdu ici ────────────────────

@pytest.mark.asyncio
class TestFenetreDePanne:
    """DoD-18 — la seule panne qui dupliquerait une personne dans un CRM."""

    async def test_un_accuse_perdu_se_rattrape_par_un_rejeu(self, session,
                                                            solar_site):
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()

        # 1. Le dépôt réussit RÉELLEMENT en face…
        await lead_export.preparer_identite_export(
            session, lead, config=load_site("solar_be"))
        charge = dict(lead.export_payload)
        reponse = await _destination(faux).deposer(charge)
        assert reponse.resultat == ResultatExport.CREE
        distant = reponse.prospect_id

        # 2. …et l'accusé local est PERDU : le lead ne sait rien de ce succès.
        assert lead.state == LeadState.PENDING_EXPORT.value
        assert lead.remote_prospect_id is None

        # 3. La reprise rejoue la même corrélation et la même charge.
        r = await _exporter(session, lead, faux)

        assert r.resultat == ResultatExport.REJEU
        assert lead.state == LeadState.EXPORTED.value
        assert lead.remote_prospect_id == distant, "le rejeu rend le prospect D'ORIGINE"
        assert len(faux.prospects) == 1, "un second prospect a été créé"


# ── 6 — secrets et PII ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSecretsEtPII:

    async def test_le_secret_n_apparait_dans_aucun_journal(self, session,
                                                           solar_site, caplog):
        """DoD-19/20."""
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()
        with caplog.at_level(logging.DEBUG):
            await _exporter(session, lead, faux)
        tout = "\n".join(r.getMessage() + json.dumps(getattr(r, "__dict__", {}),
                                                     default=str)
                         for r in caplog.records)
        # Le secret ne doit apparaître NULLE PART, pilote de base compris : il
        # n'entre jamais en base, donc rien ne peut l'y écrire.
        assert SECRET not in tout
        assert "Authorization" not in tout
        assert "Bearer" not in tout

        # La PII, elle, est jugée sur les journaux DE L'APPLICATION. Le pilote
        # SQLite en mode DEBUG relaie l'INSERT de la charge gelée — c'est notre
        # propre base, et c'est le mécanisme même qui rend le rejeu possible.
        applicatif = "\n".join(
            r.getMessage() + json.dumps(getattr(r, "__dict__", {}), default=str)
            for r in caplog.records if r.name.startswith("app."))
        assert "ada.lovelace@example.test" not in applicatif
        assert "+32470123456" not in applicatif
        assert "Lovelace" not in applicatif

    async def test_le_secret_voyage_bien_mais_ne_fuit_pas_dans_la_charge(
            self, session, solar_site):
        lead = await _capturer(session, solar_site)
        faux = FauxProspect360()
        await _exporter(session, lead, faux)
        assert faux.entetes[0]["authorization"] == f"Bearer {SECRET}"
        assert SECRET not in json.dumps(faux.recu[0])

    async def test_le_producteur_est_backend_seulement(self):
        """DoD-21 — aucune référence au producteur côté site public."""
        import pathlib
        racine = pathlib.Path(__file__).resolve().parents[1]
        for repertoire in ("web", "app/api"):
            base = racine / repertoire
            if not base.exists():
                continue
            for chemin in base.rglob("*"):
                if chemin.is_file() and chemin.suffix in (".py", ".js", ".ts",
                                                          ".html", ".jinja2"):
                    contenu = chemin.read_text(encoding="utf-8", errors="ignore")
                    assert "PROSPECT360_CREDENTIAL" not in contenu, chemin
                    assert "prospect360_credential" not in contenu, chemin


# ── 7 — configuration absente ──────────────────────────────────────────────

class TestConfiguration:

    def test_un_producteur_non_configure_est_inerte(self):
        """DoD-22 — la production tourne aujourd'hui SANS producteur."""
        assert Settings(PROSPECT360_INGEST_URL="",
                        PROSPECT360_CREDENTIAL="").prospect360_configured is False

    def test_une_moitie_de_configuration_ne_suffit_pas(self):
        """Un point d'entrée sans identifiant enverrait une requête anonyme et
        lirait le 401 comme une nouvelle."""
        assert Settings(PROSPECT360_INGEST_URL="https://x.invalid",
                        PROSPECT360_CREDENTIAL="").prospect360_configured is False
        assert _settings().prospect360_configured is True

    def test_aucun_appel_de_production_dans_ce_fichier(self):
        """DoD-23 — la garde qui protège un partenaire réel."""
        import pathlib
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        # Composés à l'exécution : écrits en clair, ils figureraient dans le
        # fichier que la garde inspecte, et elle échouerait sur elle-même.
        interdits = ["techform" + "anord", "acquisition" + "_platform",
                     "76.13" + ".44.177"]
        for interdit in interdits:
            assert interdit not in source, interdit
        # Et l'URL réellement utilisée par les bancs est une adresse morte.
        assert "p360.invalid" in source


# ── 8 — le consentement exporté est un consentement RÉEL ───────────────────

class TestConsentementApprouve:
    """Ce qui part chez Prospect 360 doit nommer un consentement qui existe.

    Un `placeholder-v0` déposé dans un CRM attache à une personne réelle une
    version de texte qui n'a jamais été rédigée : la trace de consentement
    devient invérifiable, et c'est précisément ce que la version sert à rendre
    possible. Le garde vit ici plutôt que dans la configuration parce que c'est
    l'EXPORT qui rend la valeur irrattrapable.
    """

    def test_la_configuration_solaire_ne_porte_plus_de_version_provisoire(self):
        from app.site.config import load_site
        legal = load_site("solar_be").legal
        assert legal.reviewed is True
        assert "placeholder" not in legal.consent_version.lower()
        assert legal.data_controller and legal.privacy_contact_email

    @pytest.mark.asyncio
    async def test_la_charge_porte_la_version_approuvee(self, session, solar_site):
        from app.site.config import load_site
        lead = await _capturer(session, solar_site)
        charge = construire_charge(
            lead, correlation_id="c-1",
            consent_version=lead.consent_version
            or load_site("solar_be").legal.consent_version)
        version = charge["consent"]["version"]
        assert version == "solar-be-consent-v1.0-2026-08-17"
        assert "placeholder" not in version.lower()

    @pytest.mark.asyncio
    async def test_aucun_consentement_marketing_ne_part(self, session, solar_site):
        """Le contrat refuse nommément les champs de consentement marketing, et
        le formulaire les tient séparés. Rien ne doit les rapprocher."""
        lead = await _capturer(session, solar_site)
        charge = construire_charge(lead, correlation_id="c-1",
                                   consent_version="v1")
        assert set(charge["consent"]) == {"processing", "version", "timestamp",
                                          "source"}
        assert "marketing" not in json.dumps(charge).lower()
