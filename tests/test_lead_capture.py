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
                                   LocalLeadDestination, capture_lead,
                                   normalize_email, normalize_phone)
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
            "consent_processing": True, "consent_followup_phone": True})
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

        assert rows["consent_followup_phone"].granted is True
        assert rows["consent_followup_phone"].channel == "PHONE"
        assert rows["consent_followup_whatsapp"].granted is False, \
            "an unticked case is a recorded refusal, not an absence"
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
            "solar-be-consent-partner-v0.0-NON-VALIDE"
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
    async def test_a_filled_honeypot_is_rejected(self, session, solar_site):
        with pytest.raises(LeadRejected, match="honeypot"):
            await capture_lead(
                session,
                submission=_submission(
                    signals=SubmissionSignals(honeypot_value="http://spam.example",
                                              elapsed_ms=40_000)),
                site=solar_site, config=load_site("solar_be"),
                vertical_code="SOLAR_BE", spam=HeuristicSpamProtection())

    async def test_an_instant_submission_is_rejected(self, session, solar_site):
        with pytest.raises(LeadRejected, match="floor"):
            await capture_lead(
                session,
                submission=_submission(signals=SubmissionSignals(elapsed_ms=120)),
                site=solar_site, config=load_site("solar_be"),
                vertical_code="SOLAR_BE", spam=HeuristicSpamProtection())


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
        logged = " ".join(record.getMessage() for record in caplog.records)
        logged += " " + str([record.__dict__ for record in caplog.records])

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
