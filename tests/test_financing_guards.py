"""The financing positioning, held to the same standard as everything else.

Measured on 2026-08-31 (audit §2): « Panneaux solaires gratuits : vous ne payez
rien » — the formulation the owner himself names as dangerous — classified
GENERAL / LOW / ANY. These tests pin the closure of that hole, the boundary
that keeps it from banning the subject, and the two registries (offer,
organization) that give first-party facts a legitimate channel.
"""
from __future__ import annotations

import pytest

from app.core.enums import ClaimCategory
from app.services.claim_policy import (ClaimRisk, is_financing_promise,
                                       is_unconditional_financing_promise,
                                       requirements_for)
from app.services.qa_service import run_seo_qa_v2
from app.site.config import (InvalidSite, OfferConfig, OfferFact,
                             OrganizationConfig, load_site)
from app.site.offer import offer_for_vertical, offer_view


def lab(value):
    return getattr(value, "value", value)


# ─── §2 of the audit, replayed verbatim ──────────────────────────────────────

AUDIT_PHRASES = [
    "Installez des panneaux solaires sans apport initial en Belgique.",
    "Selon votre éligibilité, seuls des frais de dossier d'environ 150 € sont à avancer.",
    "L'installation s'autofinance grâce aux économies réalisées sur votre facture.",
    "Le financement permet des mensualités inférieures à vos économies d'électricité.",
    "Vos économies d'électricité couvrent la mensualité du financement.",
    "Panneaux solaires gratuits : vous ne payez rien.",
    "Une installation photovoltaïque accessible aux petits revenus, sans économies de départ.",
    "Vous êtes éligible au financement sans apport si vous êtes propriétaire.",
    # The owner's raw vocabulary list, verbatim.
    "gratuit", "panneaux solaires gratuits", "0 €", "zéro euro", "sans apport",
    "sans apport initial", "sans rien avancer", "sans rien payer", "autofinancé",
    "s'autofinance", "les économies couvrent la mensualité",
    "remboursement par les économies", "installation gratuite",
]


class TestTheHoleIsClosed:
    @pytest.mark.parametrize("phrase", AUDIT_PHRASES)
    def test_no_audit_phrase_classifies_low(self, solar_profile, phrase):
        requirements = requirements_for(phrase, solar_profile)
        assert lab(requirements.category) == "FINANCING_PROMISE"
        assert lab(requirements.risk) == ClaimRisk.HIGH

    def test_the_category_is_unassertable_from_research(self, solar_profile):
        """OFFICIAL authority, on purpose: no retrieved page is the source of
        OUR offer, so no retrieved page can ever clear this bar. The only path
        into a page is the validated first-party registry."""
        requirements = requirements_for("Panneaux solaires sans apport.",
                                        solar_profile)
        assert lab(requirements.authority) == "OFFICIAL"


class TestTheSubjectIsNotBanned:
    CONDITIONAL = ("Selon le financement, la production, la consommation et le "
                   "prix de l'électricité, les économies peuvent contribuer à "
                   "compenser tout ou partie de la mensualité.")

    def test_the_conditional_form_is_still_a_financing_claim(self,
                                                             solar_profile):
        """Conditional does not mean unclassified: it still needs the registry
        behind it, and it still classifies HIGH."""
        requirements = requirements_for(self.CONDITIONAL, solar_profile)
        assert lab(requirements.category) == "FINANCING_PROMISE"

    def test_but_it_is_not_the_unconditional_form(self):
        assert is_unconditional_financing_promise(self.CONDITIONAL) is False
        assert is_unconditional_financing_promise(
            "L'installation s'autofinance.") is True

    def test_the_predicate_needs_the_vocabulary_not_just_a_missing_selon(self):
        """A sentence with no financing vocabulary is nobody's business here."""
        assert is_unconditional_financing_promise(
            "Les panneaux durent vingt-cinq ans.") is False
        assert is_financing_promise("Les panneaux durent vingt-cinq ans.") is False


class TestNothingHistoricMoved:
    """The before/after the owner asked for, on real ledger texts.

    Every text below is quoted verbatim from the sealed package of the live run
    (probes and measurements of 2026-08-30/31), with the category it carried
    BEFORE this change. « produire gratuitement de l'électricité » and « sans
    aide ni subside » are the edges the regex was shaped around.
    The full-registry replay runs on the host:
    `seolead package replay f9534a41-82bc-4d85-9ea2-fa0ef13bb6fd`.
    """

    CORPUS = [
        ("GENERAL", "Les panneaux solaires n'aiment pas les fortes chaleurs."),
        ("GENERAL", "On estime aujourd'hui sa rentabilisation en 5 à 7 ans, "
                    "permettant de produire gratuitement de l'électricité pour "
                    "le ménage."),
        ("GRID_RULE", "Même à la suite de l'entrée en vigueur du tarif "
                      "prosumer, sachez qu'une installation standard est "
                      "rentabilisée au bout de 5 ans."),
        ("SUBSIDY", "En résumé, investir dans des panneaux solaires est un "
                    "placement rentable sans aide ni subside grâce à la baisse "
                    "des prix."),
        ("MARKET_AVERAGE", "Le prix moyen est désormais d'environ 1 €/Wc hors "
                           "TVA, soit environ 5.000 € pour une installation "
                           "moyenne de 5.000 Wc"),
        ("SUBSIDY", "Les installations de moins de 5 kWc reçoivent 2,055 "
                    "Certificats Verts par 1000 kWh produits et cela pendant "
                    "10 ans."),
        ("OBSERVED_PRICE_RANGE", "Comptez entre 1€ et 1,2€ par watt crête "
                                 "installé."),
        ("GRID_RULE", "Le tarif prosumer consiste à faire contribuer le "
                      "prosumer aux coûts du réseau à hauteur de 62,24%."),
        ("ROI", "La rentabilité atteinte par les petites installations "
                "photovoltaïques est aujourd'hui comprise entre 7,3% et 8,4%."),
        ("GENERAL", "Bref, les petites installations sont intéressantes même "
                    "sans soutien public."),
        ("ROI", "Le retour sur investissement est généralement compris entre "
                "6 et 9 ans, selon la région."),
        ("MARKET_PRICE", "Le tarif de nuit est à 0,05 €/kWh chez certains "
                         "fournisseurs."),
        ("GENERAL", "Sans entretien particulier, les panneaux durent 25 ans."),
    ]

    @pytest.mark.parametrize("expected,text", CORPUS)
    def test_the_category_it_carried_is_the_category_it_keeps(
            self, solar_profile, expected, text):
        assert lab(requirements_for(text, solar_profile).category) == expected


# ─── The QA gate ─────────────────────────────────────────────────────────────

def _seo(body, offer, solar_profile):
    draft = {"title": "Titre de test suffisant", "body": body,
             "meta_title": "Titre", "meta_description": "Description."}
    brief = {"primary_query": "financement panneaux solaires",
             "search_intent": "COMMERCIAL", "content_type": "ARTICLE",
             "target_audience": "propriétaires", "objective": "informer",
             "recommended_title": "T", "outline": [], "key_questions": [],
             "required_facts": [], "required_sources": [{"url": "https://x.be"}],
             "missing_information": [], "cta_strategy": {},
             "cautionary_claims": []}
    return run_seo_qa_v2(draft, brief, {"facts": [], "sources": []},
                         solar_profile, offer=offer)


def _codes(result):
    return [f["code"] for f in result["findings"]]


VALIDATED = {"version": "v1", "publishable": True,
             "pending_legal_review": False, "registered_numbers": {"150"}}


class TestTheOfferGuard:
    def test_an_unregistered_offer_figure_blocks(self, solar_profile):
        result = _seo("Les frais de dossier sont de 150 €.", None, solar_profile)
        assert "UNREGISTERED_OFFER_FACT" in _codes(result)
        assert result["status"] == "FAILED"

    def test_no_registry_reads_as_empty_never_as_permission(self, solar_profile):
        """None and {} must behave identically: fail-closed."""
        for offer in (None, {}, {"version": "v0", "publishable": False,
                                 "registered_numbers": set()}):
            assert "UNREGISTERED_OFFER_FACT" in _codes(
                _seo("Un apport de 500 € est demandé.", offer, solar_profile))

    def test_a_validated_registered_figure_passes(self, solar_profile):
        codes = _codes(_seo("Les frais de dossier sont de 150 €.",
                            VALIDATED, solar_profile))
        assert "UNREGISTERED_OFFER_FACT" not in codes
        assert "UNCONDITIONAL_FINANCING_PROMISE" not in codes

    def test_a_different_figure_is_refused_even_with_a_registry(
            self, solar_profile):
        """The registry validates 150; the draft says 175. Version discipline:
        close is not registered."""
        assert "UNREGISTERED_OFFER_FACT" in _codes(
            _seo("Les frais de dossier sont de 175 €.", VALIDATED,
                 solar_profile))

    def test_a_superstring_of_a_registered_figure_is_still_unregistered(
            self, solar_profile):
        """150 is validated; 1.500 is not, and it CONTAINS 150. Equality, not
        containment, is what registered means — a typo that multiplies the fee
        by ten must not ride on the digits it shares."""
        assert "UNREGISTERED_OFFER_FACT" in _codes(
            _seo("Les frais de dossier sont de 1.500 €.", VALIDATED,
                 solar_profile))

    def test_an_unconditional_promise_blocks_with_or_without_registry(
            self, solar_profile):
        for offer in (None, VALIDATED):
            assert "UNCONDITIONAL_FINANCING_PROMISE" in _codes(
                _seo("Panneaux solaires gratuits : vous ne payez rien.",
                     offer, solar_profile))

    def test_the_conditional_form_passes_this_gate(self, solar_profile):
        codes = _codes(_seo(
            "Selon le financement et votre consommation, les économies "
            "peuvent contribuer à compenser tout ou partie de la mensualité.",
            None, solar_profile))
        assert "UNCONDITIONAL_FINANCING_PROMISE" not in codes
        assert "UNREGISTERED_OFFER_FACT" not in codes

    def test_third_party_prices_are_not_this_guard_s_business(
            self, solar_profile):
        codes = _codes(_seo(
            "Le prix moyen d'une installation est de 7 000 € selon la source "
            "consultée.", None, solar_profile))
        assert "UNREGISTERED_OFFER_FACT" not in codes
        assert "UNCONDITIONAL_FINANCING_PROMISE" not in codes


# ─── The registry itself ─────────────────────────────────────────────────────

def _fact(**kwargs):
    return OfferFact(**{"id": "application_fee_eur",
                        "label": "Frais de dossier (€)", **kwargs})


class TestOfferRegistry:
    def test_it_is_born_fail_closed(self):
        offer = OfferConfig()
        assert offer.publishable is False
        assert offer.usable_facts == []
        assert offer.registered_numbers() == set()

    def test_a_value_without_owner_validation_is_unusable(self):
        assert _fact(value=150).usable is False

    def test_a_validation_without_a_value_is_unusable(self):
        assert _fact(validated_at="2026-08-31").usable is False

    def test_publishable_needs_owner_AND_lawyer_independently(self):
        base = dict(version="v1", status="validated",
                    owner_validated_at="2026-08-31",
                    facts=[_fact(value=150, validated_at="2026-08-31")])
        owner_only = OfferConfig(**base, pending_legal_review=True)
        assert owner_only.publishable is False
        assert owner_only.registered_numbers() == set(), \
            "owner validation alone must not release a figure"

        both = OfferConfig(**base, pending_legal_review=False,
                           legal={"reviewed_at": "2026-09-01",
                                  "reviewer": "Me Exemple"})
        assert both.publishable is True
        assert both.registered_numbers() == {"150"}

        lawyer_only = OfferConfig(
            version="v1", pending_legal_review=False,
            facts=[_fact(value=150, validated_at="2026-08-31")],
            legal={"reviewed_at": "2026-09-01", "reviewer": "Me Exemple"})
        assert lawyer_only.publishable is False, \
            "legal review alone must not release a figure either"
        assert lawyer_only.registered_numbers() == set()

    def test_validated_status_without_a_date_is_refused(self):
        with pytest.raises(ValueError, match="owner_validated_at"):
            OfferConfig(version="v1", status="validated")

    def test_a_review_without_a_reviewer_is_refused(self):
        with pytest.raises(ValueError, match="reviewer"):
            OfferConfig(legal={"reviewed_at": "2026-09-01"})

    def test_an_unknown_status_is_refused(self):
        with pytest.raises(ValueError, match="status"):
            OfferConfig(status="probably_fine")

    def test_the_live_registry_is_empty_and_locked(self):
        """The configuration as shipped: slots, no values, both locks on.
        « Ne mets PAS 150 uniquement parce que cela apparaît dans notre brief. »
        """
        offer = load_site("solar_be").offer
        assert offer.pending_legal_review is True
        assert offer.publishable is False
        assert all(f.value is None for f in offer.facts)
        assert offer.worked_example is None

    def test_the_vertical_bridge_serves_the_qa_gate(self):
        view = offer_for_vertical("SOLAR_BE")
        assert view is not None
        assert view["publishable"] is False
        assert view["registered_numbers"] == set()
        assert offer_for_vertical("NO_SUCH_VERTICAL") is None


class TestOrganizationReadiness:
    def test_nothing_supplied_nothing_ready(self):
        org = load_site("solar_be").organization
        assert org.organization_schema_ready is False
        assert org.local_business_schema_ready is False

    def test_organization_needs_legal_name_and_bce(self):
        assert OrganizationConfig(legal_name="X SRL").organization_schema_ready \
            is False
        assert OrganizationConfig(
            legal_name="X SRL", bce_number="0123.456.789"
        ).organization_schema_ready is True

    def test_local_business_needs_a_place_and_a_way_to_reach_it(self):
        org = OrganizationConfig(
            legal_name="X SRL", bce_number="0123.456.789",
            address={"street": "Rue A 1", "postal_code": "1000",
                     "city": "Bruxelles"})
        assert org.local_business_schema_ready is False, "no phone, no email"
        assert OrganizationConfig(
            legal_name="X SRL", bce_number="0123.456.789", phone="+32 2 000 00 00",
            address={"street": "Rue A 1", "postal_code": "1000",
                     "city": "Bruxelles"}).local_business_schema_ready is True


class TestBooleanOptionGuard:
    def test_a_bare_yes_option_is_refused_by_the_loader(self):
        """YAML 1.1 reads `value: YES` as True, and the first real lead stored
        `battery_interest: true` because of it. Never again."""
        config = load_site("solar_be").model_dump()
        field = next(f for f in config["conversion"]["fields"]
                     if f.get("key") == "battery_interest")
        field["options"][0]["value"] = True
        from app.site.config import SiteConfig
        with pytest.raises(ValueError, match="boolean"):
            SiteConfig(**config)

    def test_the_shipped_config_has_no_boolean_option(self):
        config = load_site("solar_be")
        for field in config.conversion.fields:
            for option in field.get("options") or []:
                assert not isinstance(option.get("value"), bool), field.get("key")


# ─── The lead carries the answer, end to end ─────────────────────────────────

import pytest_asyncio


@pytest_asyncio.fixture
async def solar_site(session):
    from app.models import Site, Vertical

    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    site = Site(vertical_id=vertical.id, name="solar_be", domain=None,
                market="BE", default_language="fr", status="PLANNED")
    session.add(site)
    await session.flush()
    return site


@pytest.mark.asyncio
class TestFinancingInterestCapture:
    async def _capture(self, session, solar_site, qualification):
        from app.site.lead_capture import LeadSubmission, capture_lead
        from app.site.spam_protection import (AcceptAllSpamProtection,
                                              SubmissionSignals)
        return await capture_lead(
            session,
            submission=LeadSubmission(
                site_id="solar_be", conversion_type="ESTIMATE_REQUEST",
                email="candidate@example.be", language="fr",
                consent_processing=True, qualification=qualification,
                signals=SubmissionSignals(elapsed_ms=9_000)),
            site=solar_site, config=load_site("solar_be"),
            vertical_code="SOLAR_BE", spam=AcceptAllSpamProtection())

    @pytest.mark.parametrize("answer",
                             ["YES", "NO", "ALREADY_FINANCED", "UNSURE"])
    async def test_every_declared_answer_survives_to_the_row(
            self, session, solar_site, answer):
        from sqlalchemy import select
        from app.models import CapturedLead

        result = await self._capture(
            session, solar_site,
            {**_VALID_QUALIFICATION, "financing_interest": answer})
        import uuid as _uuid

        lead = (await session.execute(select(CapturedLead).where(
            CapturedLead.id == _uuid.UUID(str(result.lead_id))))).scalar_one()
        assert lead.qualification["financing_interest"] == answer

    async def test_an_invented_answer_is_dropped_not_stored(self, session,
                                                            solar_site):
        from sqlalchemy import select
        from app.models import CapturedLead

        result = await self._capture(
            session, solar_site,
            {**_VALID_QUALIFICATION, "financing_interest": "GIVE_ME_MONEY"})
        import uuid as _uuid

        lead = (await session.execute(select(CapturedLead).where(
            CapturedLead.id == _uuid.UUID(str(result.lead_id))))).scalar_one()
        assert "financing_interest" not in lead.qualification

    async def test_it_stays_optional(self, session, solar_site):
        """A qualification question is never a toll gate."""
        result = await self._capture(session, solar_site,
                                     dict(_VALID_QUALIFICATION))
        assert result.lead_id is not None

    async def test_battery_interest_now_stores_the_string_it_always_meant(
            self, session, solar_site):
        """The YAML 1.1 repair, observed at the row: "YES" in, "YES" stored —
        not `true`, which is what the first real lead carries."""
        from sqlalchemy import select
        from app.models import CapturedLead

        result = await self._capture(
            session, solar_site,
            {**_VALID_QUALIFICATION, "battery_interest": "YES"})
        import uuid as _uuid

        lead = (await session.execute(select(CapturedLead).where(
            CapturedLead.id == _uuid.UUID(str(result.lead_id))))).scalar_one()
        assert lead.qualification["battery_interest"] == "YES"


_VALID_QUALIFICATION = {
    "owner_status": "OWNER", "postcode": "1000", "property_type": "HOUSE",
    "project_timeframe": "LT_6M", "roof_type": "PITCHED",
    "annual_consumption_kwh": 4200,
}
