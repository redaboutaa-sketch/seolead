"""Phase 4 — lead capture, attribution, consent and the export boundary.

The boundary test is the one that matters most: **zero writes reach Prospect 360.**
Every other test here protects a person's submitted data or the honesty of the
funnel record, but that one protects a production tenant that this system has no
authorisation to touch.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.enums import ConsentPurpose, ConversionType, LeadState
from app.models import (CapturedLead, LeadAttribution, LeadConsent, Site,
                        SiteEvent, Vertical)
from app.site.config import load_site
from app.site.lead_capture import (LeadRejected, LeadSubmission,
                                   LocalLeadDestination, SubmissionRefused,
                                   capture_lead, normalize_email,
                                   normalize_phone)
from app.site.spam_protection import (AcceptAllSpamProtection,
                                      HeuristicSpamProtection, SubmissionSignals)

VALID_QUALIFICATION = {
    "owner_status": "OWNER",
    "postcode": "1000",
    "property_type": "HOUSE",
    "project_timeframe": "LT_6M",
    "roof_type": "PITCHED",
    "annual_consumption_kwh": 4200,
}

ATTRIBUTION = {
    "landing_path": "/prix-panneaux-solaires",
    "page_path": "/demande-etude",
    "channel": "organic",
    "source": "google",
    "referrer": "https://www.google.be/",
    "utm_source": "google", "utm_medium": "organic",
    "utm_campaign": "prix-solaire", "utm_content": "hero", "utm_term": "prix panneaux",
    "cta": "ESTIMATE_REQUEST", "search_intent": "COMMERCIAL",
    "keyword_cluster": "prix", "session_id": "sess-123",
    "correlation_id": "corr-456",
}


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


def _submission(**overrides) -> LeadSubmission:
    base = dict(
        site_id="solar_be", conversion_type=ConversionType.ESTIMATE_REQUEST.value,
        email="test.person@example.be", language="fr", first_name="Test",
        last_name="Person", phone="+32 470 12 34 56", postcode="1000",
        qualification=dict(VALID_QUALIFICATION), consent_processing=True,
        consent_marketing=False, attribution=dict(ATTRIBUTION),
        signals=SubmissionSignals(elapsed_ms=45_000),
    )
    base.update(overrides)
    return LeadSubmission(**base)


async def _capture(session, site, **overrides):
    return await capture_lead(
        session, submission=_submission(**overrides), site=site,
        config=load_site("solar_be"), vertical_code="SOLAR_BE",
        spam=AcceptAllSpamProtection())


@pytest.mark.asyncio
class TestLeadValidation:
    async def test_a_valid_lead_is_accepted_and_held_for_export(self, session,
                                                                 solar_site):
        result = await _capture(session, solar_site)
        assert result.state == LeadState.PENDING_EXPORT.value
        assert result.destination == "local"

        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert lead.email == "test.person@example.be"
        assert lead.phone == "+32470123456"
        assert lead.qualification["owner_status"] == "OWNER"
        assert lead.qualification["annual_consumption_kwh"] == 4200

    @pytest.mark.parametrize("email", [
        "not-an-email", "@example.be", "person@", "person@localhost",
        "person example@site.be", "", "a" * 70 + "@example.be",
    ])
    async def test_an_invalid_email_is_refused(self, session, solar_site, email):
        with pytest.raises(LeadRejected):
            await _capture(session, solar_site, email=email)

    async def test_an_unparseable_phone_is_dropped_not_fatal(self, session,
                                                              solar_site):
        """A typo in an optional field must not cost a real prospect."""
        await _capture(session, solar_site, phone="not a phone")
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert lead.phone is None
        assert lead.state == LeadState.PENDING_EXPORT.value

    async def test_consent_is_required_and_never_assumed(self, session,
                                                          solar_site):
        with pytest.raises(LeadRejected, match="consent"):
            await _capture(session, solar_site, consent_processing=False)

    async def test_marketing_consent_is_separate_and_optional(self, session,
                                                               solar_site):
        await _capture(session, solar_site, consent_marketing=False)
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert lead.consent_marketing is False
        assert lead.state == LeadState.PENDING_EXPORT.value, \
            "declining marketing must not reject the lead"

    async def test_consent_is_recorded_with_version_time_and_source(
            self, session, solar_site):
        await _capture(session, solar_site)
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert lead.consent_version == load_site("solar_be").legal.consent_version
        assert lead.consent_timestamp is not None
        assert lead.consent_source == "/demande-etude"

    async def test_a_missing_required_answer_is_refused(self, session,
                                                         solar_site):
        incomplete = dict(VALID_QUALIFICATION)
        del incomplete["project_timeframe"]
        with pytest.raises(LeadRejected, match="project_timeframe"):
            await _capture(session, solar_site, qualification=incomplete)

    async def test_unknown_qualification_keys_are_dropped(self, session,
                                                           solar_site):
        payload = dict(VALID_QUALIFICATION, injected="<script>alert(1)</script>",
                       admin=True)
        await _capture(session, solar_site, qualification=payload)
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert "injected" not in lead.qualification
        assert "admin" not in lead.qualification

    async def test_a_choice_outside_its_options_is_dropped(self, session,
                                                            solar_site):
        payload = dict(VALID_QUALIFICATION, roof_type="ARBITRARY")
        await _capture(session, solar_site, qualification=payload)
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert "roof_type" not in lead.qualification

    async def test_a_number_outside_its_bounds_is_dropped(self, session,
                                                           solar_site):
        payload = dict(VALID_QUALIFICATION, annual_consumption_kwh=9_999_999)
        await _capture(session, solar_site, qualification=payload)
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert "annual_consumption_kwh" not in lead.qualification




@pytest.mark.asyncio
class TestPerCaseConsent:
    """N independent consent cases, each with its own state, version and instant.

    The legacy pair on `captured_lead` is untouched — export contract v1 reads
    it — and these rows are what a v2 contract will read.
    """

    async def test_every_defined_case_gets_a_row_with_its_own_version(
            self, session, solar_site):
        await _capture(session, solar_site, consents={
            "consent_processing": True, "consent_followup_contact": True})
        rows = {r.consent_key: r
                for r in (await session.execute(select(LeadConsent))).scalars()}

        defined = {c["key"]: c for c in load_site("solar_be").consent_definitions()}
        assert set(rows) == set(defined), \
            "every case the form offers is recorded, granted or refused alike"
        for key, row in rows.items():
            assert row.text_version == defined[key]["version"]
            assert row.purpose == defined[key]["purpose"]
            assert row.channel == defined[key]["channel"]
            assert row.granted_at is not None
            assert row.source == "/demande-etude"

        assert rows["consent_marketing"].granted is False, \
            "an unticked case is a recorded refusal, not an absence"
        assert rows["consent_marketing"].channel == "WHATSAPP"
        assert rows["consent_partner_transfer"].granted is False
        assert rows["consent_partner_transfer"].purpose == \
            ConsentPurpose.PARTNER_TRANSFER.value

    async def test_each_case_records_its_own_version_not_a_shared_one(
            self, session, solar_site):
        await _capture(session, solar_site)
        versions = {r.consent_key: r.text_version
                    for r in (await session.execute(select(LeadConsent))).scalars()}
        assert versions["consent_processing"] == \
            load_site("solar_be").legal.consent_version
        assert versions["consent_partner_transfer"] == \
            "solar-be-partner-transfer-v1.0-2026-08-30"
        assert len(set(versions.values())) > 1, \
            "the whole point: versions differ per case"

    async def test_the_new_vocabulary_alone_satisfies_processing_consent(
            self, session, solar_site):
        """A form speaking only `consents` works; the legacy boolean is not
        secretly required."""
        result = await _capture(session, solar_site, consent_processing=False,
                                consents={"consent_processing": True})
        assert result.state == LeadState.PENDING_EXPORT.value

    async def test_the_new_vocabulary_can_refuse_what_the_old_one_granted(
            self, session, solar_site):
        """When both spellings are present, the per-case answer wins."""
        with pytest.raises(LeadRejected, match="consent"):
            await _capture(session, solar_site, consent_processing=True,
                           consents={"consent_processing": False})

    async def test_an_unknown_consent_key_is_dropped_not_stored(
            self, session, solar_site):
        await _capture(session, solar_site,
                       consents={"consent_processing": True,
                                 "consent_invented_by_a_bot": True})
        keys = {r.consent_key
                for r in (await session.execute(select(LeadConsent))).scalars()}
        assert "consent_invented_by_a_bot" not in keys, \
            "the browser does not get to invent a consent case"

    async def test_the_legacy_marketing_column_mirrors_the_case_row(
            self, session, solar_site):
        await _capture(session, solar_site, consent_marketing=False,
                       consents={"consent_processing": True,
                                 "consent_marketing": True})
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        row = (await session.execute(select(LeadConsent).where(
            LeadConsent.consent_key == "consent_marketing"))).scalar_one()
        assert lead.consent_marketing is True
        assert row.granted is True, \
            "the two spellings of marketing consent can never disagree"

    async def test_changing_a_version_in_config_is_the_whole_change(
            self, session, solar_site):
        """THE acceptance criterion: the day a validated text lands, editing the
        YAML version is sufficient for every new capture to record it."""
        config = load_site("solar_be").model_copy(deep=True)
        for field in config.conversion.fields:
            if field.get("key") == "consent_partner_transfer":
                field["consent_version"] = "solar-be-consent-partner-v1.0-2026-09-01"
                field["pending_legal_review"] = False
        await capture_lead(session, submission=_submission(
            consents={"consent_processing": True,
                      "consent_partner_transfer": True}),
            site=solar_site, config=config, vertical_code="SOLAR_BE",
            spam=AcceptAllSpamProtection())
        row = (await session.execute(select(LeadConsent).where(
            LeadConsent.consent_key == "consent_partner_transfer"))).scalar_one()
        assert row.text_version == "solar-be-consent-partner-v1.0-2026-09-01"
        assert row.granted is True

    async def test_a_placeholder_consent_cannot_leave_staging(self):
        """The loader is the gate: unvalidated consent text may exist only while
        the site is staging — same shape as the indexing gate."""
        from app.site.config import SiteConfig

        raw = load_site("solar_be").model_dump()
        raw["staging"] = False
        raw["domain"] = "monprojetsolaire.be"
        # La locale est déclarée ici : depuis le 2026-08-31 la campagne est
        # francophone, et une locale non servie ne collecte aucun consentement.
        # Le garde protège les locales OFFERTES — c'est le jour où le
        # néerlandais revient qu'il doit mordre, et ce test le vérifie.
        raw["supported_languages"] = ["fr", "nl"]
        with pytest.raises(Exception, match="pending_legal_review"):
            SiteConfig(**raw)

    async def test_a_non_processing_consent_may_not_be_required(self):
        from app.site.config import SiteConfig

        raw = load_site("solar_be").model_dump()
        for field in raw["conversion"]["fields"]:
            if field.get("key") == "consent_marketing":
                field["required"] = True
        with pytest.raises(Exception, match="may not be required"):
            SiteConfig(**raw)

    async def test_a_consent_field_without_a_purpose_is_refused(self):
        from app.site.config import SiteConfig

        raw = load_site("solar_be").model_dump()
        raw["conversion"]["fields"].append(
            {"key": "consent_mystery", "type": "consent",
             "label": "x", "required": False})
        with pytest.raises(Exception, match="resolvable purpose"):
            SiteConfig(**raw)


# Les textes FR validés par le propriétaire, responsable de traitement, le
# 2026-08-30 (locale fr-BE) — épinglés AU CARACTÈRE PRÈS contre leur version.
# Modifier un libellé sans frapper une nouvelle version rend cette table
# fausse et la suite rouge : c'est le garde de version, et il est voulu.
TEXTES_VERSIONNES = {
    # v1.1 (2026-08-31) : le service est nommé « Mon Projet Solaire » et non
    # plus « Solar Belgium ». Le texte v1.0 n'est PAS répété ici — il vit
    # désormais uniquement dans les lignes lead_consent déjà collectées, qui
    # portent leur propre version. C'est la règle : on frappe une version, on
    # ne réécrit pas ce à quoi quelqu'un a consenti.
    "solar-be-consent-v1.1-2026-08-31": (
        "consent_processing",
        "J'accepte que mes données personnelles soient traitées par BEAVER "
        "DATA GROUP, responsable du traitement de Mon Projet Solaire, afin "
        "d'analyser ma demande relative à mon projet solaire, me recontacter "
        "à ce sujet et assurer le suivi de ma demande. J'ai pris connaissance "
        "de la Politique de confidentialité et je peux retirer mon "
        "consentement à tout moment."),
    "solar-be-followup-contact-v1.0-2026-08-30": (
        "consent_followup_contact",
        "J'accepte d'être recontacté(e) par BEAVER DATA GROUP, par téléphone "
        "ou par WhatsApp, au sujet de ma demande d'étude solaire, afin d'en "
        "préciser les éléments et d'en recevoir les résultats. Ce "
        "consentement ne porte que sur le suivi de ma demande. Je peux le "
        "retirer à tout moment."),
    "solar-be-marketing-whatsapp-v1.0-2026-08-30": (
        "consent_marketing",
        "J'accepte de recevoir par WhatsApp des informations et offres de "
        "BEAVER DATA GROUP relatives aux solutions d'énergie, y compris les "
        "offres de sa boutique partenaire. Je peux me désinscrire à tout "
        "moment, notamment en répondant STOP."),
    "solar-be-partner-transfer-v1.0-2026-08-30": (
        "consent_partner_transfer",
        "J'accepte que mes coordonnées et les caractéristiques de mon projet "
        "soient transmises à Solution SG, partenaire installateur de BEAVER "
        "DATA GROUP, dans le seul but d'organiser un rendez-vous relatif à "
        "mon projet solaire. BEAVER DATA GROUP demeure responsable de ce "
        "traitement. Je peux retirer ce consentement à tout moment."),
}


def _verifier_textes_versionnes(config) -> list[str]:
    """Compare chaque libellé affiché au texte épinglé pour sa version.

    Rend la liste des versions dont le texte a divergé — vide quand tout est
    conforme. Partagée entre le test nominal et le test de mutation, pour que
    le second prouve que le premier détecte réellement une altération.
    """
    fields = config.field_definitions()
    versions = {c["field_key"]: c["version"]
                for c in config.consent_definitions()}
    divergents = []
    for version, (key, texte) in TEXTES_VERSIONNES.items():
        if versions.get(key) != version or fields[key]["label"] != texte:
            divergents.append(version)
    return divergents


@pytest.mark.asyncio
class TestValidatedConsentTexts:
    """Branchement des textes validés du 2026-08-30 — les preuves demandées."""

    async def test_les_textes_affiches_sont_au_caractere_pres_les_versionnes(self):
        assert _verifier_textes_versionnes(load_site("solar_be")) == []

    async def test_muter_un_libelle_sans_changer_la_version_est_detecte(self):
        """Mutation sur le garde de version : une altération d'UN caractère
        d'un texte validé, version inchangée, doit être détectée — sinon le
        garde ne garde rien."""
        config = load_site("solar_be").model_copy(deep=True)
        for field in config.conversion.fields:
            if field.get("key") == "consent_partner_transfer":
                field["label"] = field["label"].replace(
                    "Solution SG", "Solution XX", 1)
        divergents = _verifier_textes_versionnes(config)
        assert divergents == ["solar-be-partner-transfer-v1.0-2026-08-30"]

    async def test_une_case_deux_entrees_meme_texte_meme_version(
            self, session, solar_site):
        """La case 1 (suivi de la demande) émet DEUX entrées — PHONE et
        WHATSAPP — depuis UNE case cochée, même version de texte."""
        await _capture(session, solar_site,
                       consents={"consent_processing": True,
                                 "consent_followup_contact": True})
        rows = [r for r in (await session.execute(select(LeadConsent))).scalars()
                if r.purpose == ConsentPurpose.FOLLOWUP_CONTACT.value]
        assert sorted((r.consent_key, r.channel, r.granted, r.text_version)
                      for r in rows) == [
            ("consent_followup_contact:PHONE", "PHONE", True,
             "solar-be-followup-contact-v1.0-2026-08-30"),
            ("consent_followup_contact:WHATSAPP", "WHATSAPP", True,
             "solar-be-followup-contact-v1.0-2026-08-30"),
        ]

    async def test_la_case_marketing_emet_finalite_et_canal_valides(
            self, session, solar_site):
        await _capture(session, solar_site,
                       consents={"consent_processing": True,
                                 "consent_marketing": True})
        row = (await session.execute(select(LeadConsent).where(
            LeadConsent.consent_key == "consent_marketing"))).scalar_one()
        assert (row.purpose, row.channel, row.granted, row.text_version) == (
            ConsentPurpose.MARKETING.value, "WHATSAPP", True,
            "solar-be-marketing-whatsapp-v1.0-2026-08-30")

    async def test_le_garde_nl_tient_toujours(self):
        """Le FR est validé ; la variante NL de chaque case reste
        pending_legal_review, et quitter le staging reste refusé tant qu'une
        locale servie collecterait un consentement sur un placeholder."""
        from app.site.config import SiteConfig

        raw = load_site("solar_be").model_dump()
        raw["staging"] = False
        raw["supported_languages"] = ["fr", "nl"]
        with pytest.raises(Exception, match="'nl'.*pending_legal_review"):
            SiteConfig(**raw)

    async def test_le_fr_seul_ne_bloque_plus_le_staging(self):
        """La contre-preuve du garde : une fois les variantes NL validées (ou
        la locale nl retirée), plus aucune case FR ne retient le site — les
        gardes levés pour le FR le sont réellement."""
        from app.site.config import SiteConfig

        raw = load_site("solar_be").model_dump()
        raw["staging"] = False
        for field in raw["conversion"]["fields"]:
            for variant in (field.get("i18n") or {}).values():
                variant.pop("pending_legal_review", None)
        config = SiteConfig(**raw)
        assert config.staging is False


@pytest.mark.asyncio
class TestAttribution:
    async def test_every_attribution_field_is_persisted(self, session, solar_site):
        await _capture(session, solar_site)
        row = (await session.execute(select(LeadAttribution))).scalar_one()

        assert row.landing_path == "/prix-panneaux-solaires"
        assert row.page_path == "/demande-etude"
        assert row.language == "fr"
        assert row.search_intent == "COMMERCIAL"
        assert row.keyword_cluster == "prix"
        assert row.channel == "organic"
        assert row.source == "google"
        assert row.referrer == "https://www.google.be/"
        assert row.utm_source == "google"
        assert row.utm_medium == "organic"
        assert row.utm_campaign == "prix-solaire"
        assert row.utm_content == "hero"
        assert row.utm_term == "prix panneaux"
        assert row.cta == "ESTIMATE_REQUEST"
        assert row.conversion_type == ConversionType.ESTIMATE_REQUEST.value
        assert row.session_id == "sess-123"
        assert row.correlation_id == "corr-456"
        assert row.vertical_code == "SOLAR_BE"
        assert row.created_at is not None

    async def test_attribution_exists_even_with_no_utm_parameters(self, session,
                                                                   solar_site):
        """Direct traffic is still attributable — first-party, not vendor-dependent."""
        await _capture(session, solar_site,
                       attribution={"page_path": "/demande-etude",
                                    "channel": "direct"})
        row = (await session.execute(select(LeadAttribution))).scalar_one()
        assert row.channel == "direct"
        assert row.utm_source is None
        assert row.language == "fr"


@pytest.mark.asyncio
class TestProspect360Boundary:
    async def test_the_default_destination_writes_nowhere(self, session,
                                                           solar_site):
        """Phase 4's hard boundary. No adapter may reach production."""
        destination = LocalLeadDestination()
        assert destination.code == "local"

        result = await capture_lead(
            session, submission=_submission(), site=solar_site,
            config=load_site("solar_be"), vertical_code="SOLAR_BE",
            destination=destination, spam=AcceptAllSpamProtection())

        assert result.state == LeadState.PENDING_EXPORT.value
        assert result.state != LeadState.EXPORTED.value, \
            "a lead nothing received must never be marked exported"

    async def test_no_prospect360_adapter_is_wired(self):
        """There is an interface and no implementation. That is deliberate."""
        import app.site.lead_capture as module

        names = [n for n in dir(module) if "prospect" in n.lower()]
        assert names == []

    async def test_the_module_holds_no_external_connection_string(self):
        import inspect

        import app.site.lead_capture as module

        source = inspect.getsource(module)
        for fragment in ("acquisition_platform", "prospect360", "postgresql://",
                         "INSERT INTO"):
            assert fragment not in source


@pytest.mark.asyncio
class TestSpamProtection:
    async def _refuse(self, session, solar_site, signals):
        with pytest.raises(SubmissionRefused) as caught:
            await capture_lead(
                session, submission=_submission(signals=signals),
                site=solar_site, config=load_site("solar_be"),
                vertical_code="SOLAR_BE", spam=HeuristicSpamProtection())
        return caught.value

    async def test_a_filled_honeypot_is_rejected(self, session, solar_site):
        assert await self._refuse(
            session, solar_site,
            SubmissionSignals(honeypot_value="http://spam.example",
                              elapsed_ms=40_000))

    async def test_an_instant_submission_is_rejected(self, session, solar_site):
        assert await self._refuse(
            session, solar_site, SubmissionSignals(elapsed_ms=120))

    # ── What the refusal is allowed to say ───────────────────────────────────
    # On 2026-08-30 the owner submitted the form himself, from Chrome, and the
    # page answered "submission rejected: honeypot field was filled". Two
    # failures in one sentence: it told a wrongly-refused human nothing he could
    # act on, and it told whoever tripped the trap exactly which trap it was.

    @pytest.mark.parametrize("signals", [
        SubmissionSignals(honeypot_value="http://spam.example", elapsed_ms=40_000),
        SubmissionSignals(elapsed_ms=120),
    ])
    async def test_the_refusal_names_no_defence(self, session, solar_site,
                                                signals):
        message = str(await self._refuse(session, solar_site, signals)).casefold()
        for word in ("honeypot", "floor", "spam", "trap", "bot", "2500", "ms"):
            assert word not in message, \
                f"the visitor-facing refusal must not contain {word!r}"

    async def test_it_carries_its_own_code_so_the_front_end_can_neutralise_it(
            self, session, solar_site):
        """The proxy needs to tell this refusal from a useful validation one.

        "consent to process the request is required" helps a visitor and must
        still be shown; this one must not be.
        """
        refusal = await self._refuse(
            session, solar_site,
            SubmissionSignals(honeypot_value="x", elapsed_ms=40_000))
        assert refusal.code == "SUBMISSION_REFUSED"
        assert refusal.code != LeadRejected.code
        assert isinstance(refusal, LeadRejected), \
            "the API's existing handler must keep catching it"

    async def test_the_reason_still_reaches_the_operator(self, session,
                                                         solar_site, caplog):
        """Neutral to the visitor, precise in the log. Not neutral everywhere."""
        import logging

        caplog.set_level(logging.WARNING)
        await self._refuse(session, solar_site,
                           SubmissionSignals(honeypot_value="x", elapsed_ms=40_000))
        reasons = [getattr(r, "reason", "") for r in caplog.records]
        assert any("honeypot" in str(reason) for reason in reasons)


class TestNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("+32 470 12 34 56", "+32470123456"),
        ("0470/12.34.56", "0470123456"),
        ("0032470123456", "+32470123456"),
        ("12345", None),
    ])
    def test_phone_normalisation(self, raw, expected):
        assert normalize_phone(raw) == expected

    def test_email_normalisation_lowercases_and_trims(self):
        assert normalize_email("  Test.Person@Example.BE ") == "test.person@example.be"


class TestRateLimiting:
    def test_the_rate_limit_bites_after_its_ceiling(self):
        guard = HeuristicSpamProtection(max_submissions=3)
        signals = SubmissionSignals(elapsed_ms=30_000, client_key="abc")
        assert [guard.check(signals).accepted for _ in range(4)] == \
            [True, True, True, False]

    def test_clients_are_bucketed_separately(self):
        guard = HeuristicSpamProtection(max_submissions=1)
        assert guard.check(SubmissionSignals(elapsed_ms=9_000,
                                             client_key="a")).accepted
        assert guard.check(SubmissionSignals(elapsed_ms=9_000,
                                             client_key="b")).accepted


@pytest.mark.asyncio
class TestLeadLogging:
    async def test_no_submitted_value_reaches_the_logs(self, session, solar_site,
                                                        caplog):
        import logging

        caplog.set_level(logging.INFO)
        await _capture(session, solar_site)

        # The message AND everything passed through `extra` — that is where a
        # leak would actually land, and `extra` is invisible in `getMessage()`.
        #
        # LogRecord's OWN attributes are excluded, and that exclusion is the
        # point: they carry no submitted data, but they do carry numbers.
        # `relativeCreated` counts milliseconds since logging started, so in a
        # full-suite run it reaches values like 21000.9 — which contains "1000",
        # the postcode this test forbids. The haystack was failing the test at
        # random, on evidence that was never a leak. `process` and `thread` are
        # the same trap.
        reserved = set(logging.LogRecord("x", logging.INFO, "p", 1, "m",
                                         None, None).__dict__)
        fragments = []
        for record in caplog.records:
            fragments.append(record.getMessage())
            fragments += [f"{k}={v!r}" for k, v in record.__dict__.items()
                          if k not in reserved]
        logged = " ".join(fragments)

        for secret in ("test.person@example.be", "+32470123456", "Test", "Person",
                       "1000"):
            assert secret not in logged, f"leaked {secret!r} into the logs"

    async def test_a_rejected_submission_does_not_log_its_payload(
            self, session, solar_site, caplog):
        import logging

        caplog.set_level(logging.WARNING)
        with pytest.raises(LeadRejected):
            await capture_lead(
                session,
                submission=_submission(
                    email="victim@example.be",
                    signals=SubmissionSignals(honeypot_value="x", elapsed_ms=9_000)),
                site=solar_site, config=load_site("solar_be"),
                vertical_code="SOLAR_BE", spam=HeuristicSpamProtection())
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert "victim@example.be" not in logged


@pytest.mark.asyncio
class TestGenericVerticalReusesTheSameCode:
    async def test_a_non_solar_site_captures_through_the_same_path(self, session):
        """The isolation control: no Solar field is required by the machinery."""
        vertical = Vertical(code="TEST_GENERIC", name="Generic", market="FR",
                            default_language="en", active=True)
        session.add(vertical)
        await session.flush()
        site = Site(vertical_id=vertical.id, name="demo_generic", domain=None,
                    market="FR", default_language="en", status="PLANNED")
        session.add(site)
        await session.flush()

        result = await capture_lead(
            session,
            submission=LeadSubmission(
                site_id="demo_generic", conversion_type="CONTACT",
                email="someone@example.com", language="en",
                qualification={}, consent_processing=True,
                attribution={"page_path": "/"},
                signals=SubmissionSignals(elapsed_ms=30_000)),
            site=site, config=load_site("demo_generic"),
            vertical_code="TEST_GENERIC", spam=AcceptAllSpamProtection())

        assert result.state == LeadState.PENDING_EXPORT.value
        lead = (await session.execute(select(CapturedLead))).scalar_one()
        assert lead.vertical_code == "TEST_GENERIC"
        assert lead.language == "en"
