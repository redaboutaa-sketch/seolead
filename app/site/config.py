"""Site profiles, loaded from YAML.

The boundary this file draws is the one that makes the frontend reusable. A
vertical describes *what may be said* (claims, authority, evidence policy); a site
describes *where and how it is said* (brand, domain, locales, funnel, legal, CTA).
Solar Belgium is one site over one vertical today, but nothing here assumes that:
a second site over the same vertical, or one site serving two markets, is a YAML
file, not a code change.

Placeholders are first-class. `brand_name` may be a placeholder and `domain` may be
null, because the owner has not supplied them and waiting for branding before
building the site would be the wrong order of work. What is *not* optional is
`staging`: a site with no domain cannot be anything but staging, and the loader
refuses a configuration that claims otherwise.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from app.core.enums import ConsentChannel, ConsentPurpose
from app.core.errors import SeoLeadError

SITE_DIR = Path(__file__).resolve().parents[2] / "config" / "sites"

# Purposes the two historical checkbox keys have always meant. Inference exists
# for THEM only, so existing site files stay valid; any other consent field must
# declare `consent_purpose` explicitly or the loader refuses the file.
_LEGACY_CONSENT_PURPOSES = {
    "consent_processing": ConsentPurpose.PROCESSING.value,
    "consent_marketing": ConsentPurpose.MARKETING.value,
}


class InvalidSite(SeoLeadError):
    code = "INVALID_SITE"


class ContactConfig(BaseModel):
    """Owner-supplied contact details. Every field may legitimately be missing."""

    email: str | None = None
    phone: str | None = None
    address: str | None = None
    company_name: str | None = None
    company_number: str | None = None
    # Where a captured lead should be routed once a destination exists.
    lead_destination_email: str | None = None


class LegalConfig(BaseModel):
    """Legal wording is owner/counsel territory, not the generator's.

    `reviewed` stays false until a human says otherwise, and the renderer shows an
    explicit placeholder rather than plausible-sounding invented policy text.
    """

    privacy_policy_path: str | None = None
    terms_path: str | None = None
    cookie_policy_path: str | None = None
    consent_version: str = "placeholder-v0"
    # La version de la POLITIQUE affichée, distincte de `consent_version` (qui
    # identifie le texte du consentement au traitement et voyage avec chaque
    # lead). Mettre à jour la politique incrémente celle-ci sans toucher à
    # celle-là : les consentements déjà recueillis restent traçables tels quels.
    privacy_policy_version: str | None = None
    data_controller: str | None = None
    # Adresse d'exercice des droits. Publiée sur la page de confidentialité :
    # un responsable du traitement sans point de contact ne permet à personne
    # d'exercer les droits que la politique annonce.
    privacy_contact_email: str | None = None
    reviewed: bool = False


class ConversionConfig(BaseModel):
    primary_cta: str
    primary_cta_label: str
    secondary_cta: str | None = None
    secondary_cta_label: str | None = None
    form_id: str = "default"
    # Ordered step definitions; each step lists field keys defined in `fields`.
    form_steps: list[dict] = Field(default_factory=list)
    fields: list[dict] = Field(default_factory=list)
    consent_required: bool = True
    marketing_consent_optional: bool = True


class SeoConfig(BaseModel):
    # The scheme+host every canonical URL is built against. Explicit rather than
    # derived from `domain`, because the two can legitimately differ (a staging
    # host serving content whose canonical is the production origin) and because
    # a canonical that silently falls back to localhost is worse than no canonical.
    canonical_origin: str | None = None
    # Whether PUBLISHED content may be served on the public routes at all.
    #
    # Separate from `allow_indexing` on purpose. "A person can read this page at
    # its real URL" and "a search engine may keep a copy of it" are different
    # decisions, and a soft launch is exactly the state where the first is true
    # and the second is not. Collapsing them — as this config did until the
    # domain existed — makes publishing a page impossible without also opening
    # the site to crawlers.
    allow_publication: bool = False
    default_title_suffix: str | None = None
    default_meta_description: str | None = None
    organization_schema: bool = False
    sitemap_enabled: bool = True
    # Even when a domain exists, indexing stays off until the owner opens the gate.
    allow_indexing: bool = False


class OfferFact(BaseModel):
    """One first-party fact about OUR offer — a fee, a term, a condition's value.

    First-party is the whole point of the type: this is what WE assert about our
    own offer, as opposed to a `researched_fact`, which is what a retrieved page
    asserts about the world. The research pipeline may never mint one of these —
    the only writers are this configuration file and the owner who validates it.

    `value: null` is a fact that exists as a slot but has not been supplied:
    « Ne mets PAS 150 uniquement parce que cela apparaît dans notre brief. »
    A fact is usable only once it carries a value AND a validation date.
    """

    id: str
    label: str
    value: str | int | float | bool | None = None
    unit: str | None = None
    provenance: str = "first_party"
    # When the owner validated THIS value. Null value + a date, or a value with
    # no date, are both unusable — the pairing is the fact.
    validated_at: str | None = None

    @property
    def usable(self) -> bool:
        return self.value is not None and bool(self.validated_at)


class OfferLegalConfig(BaseModel):
    """The lawyer's half of the offer. Nothing here is generated."""

    reviewed_at: str | None = None
    reviewer: str | None = None
    # Mentions the lawyer requires on any page describing the offer (consumer
    # credit advertising carries mandatory wording in Belgium). Rendered
    # verbatim when present; their absence while pending is what keeps the
    # landing unpublishable.
    mandatory_disclosures: list[str] = Field(default_factory=list)


class OfferConfig(BaseModel):
    """The versioned first-party offer registry — the single source of truth for
    what Mon Projet Solaire may say about its own offer.

    Fail-closed from birth: `status: draft` + `pending_legal_review: true` and
    every fact valueless. Three independent people must act before a figure can
    reach a public page — whoever writes the value, the owner who validates it,
    and the lawyer who lifts the review — and the code path that could skip one
    of them does not exist.
    """

    version: str = "offer-v0-empty"
    status: str = "draft"                    # draft | validated
    pending_legal_review: bool = True
    owner_validated_at: str | None = None
    facts: list[OfferFact] = Field(default_factory=list)
    financing: dict = Field(default_factory=dict)      # provider, conditions[]
    eligibility: dict = Field(default_factory=dict)    # criteria[]
    geography: dict = Field(default_factory=dict)      # service_areas[]
    guarantees: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    # The realistic worked example (production, instalment, saving) — supplied
    # by the owner from a real case, NEVER generated. Null until then.
    worked_example: dict | None = None
    legal: OfferLegalConfig = Field(default_factory=OfferLegalConfig)

    @model_validator(mode="after")
    def _check_consistency(self) -> "OfferConfig":
        if self.status not in ("draft", "validated"):
            raise ValueError(f"offer.status must be draft or validated, "
                             f"got {self.status!r}")
        if self.status == "validated" and not self.owner_validated_at:
            raise ValueError(
                "offer.status is validated but owner_validated_at is empty: a "
                "validation without a date is a validation nobody made")
        if self.legal.reviewed_at and not self.legal.reviewer:
            raise ValueError(
                "offer.legal.reviewed_at is set without a reviewer: a legal "
                "review must name who made it")
        return self

    @property
    def legally_reviewed(self) -> bool:
        return not self.pending_legal_review and bool(self.legal.reviewed_at)

    @property
    def publishable(self) -> bool:
        """Whether offer facts may appear on a PUBLIC page.

        Owner validation AND legal review, independently. Staging may display
        the structure earlier; publication may not.
        """
        return (self.status == "validated"
                and bool(self.owner_validated_at)
                and self.legally_reviewed)

    @property
    def usable_facts(self) -> list[OfferFact]:
        """Facts a page may render — and only when the offer is publishable."""
        if not self.publishable:
            return []
        return [f for f in self.facts if f.usable]

    def registered_numbers(self) -> set[str]:
        """Digit-strings of every usable fact value, for the QA guard.

        Empty while the offer is not publishable — which makes the guard
        fail-closed: with no registry to check against, ANY figure presented as
        our offer is an invention.
        """
        numbers: set[str] = set()
        for fact in self.usable_facts:
            digits = re.sub(r"\D", "", str(fact.value))
            if digits:
                numbers.add(digits)
        return numbers


class OrganizationAddress(BaseModel):
    street: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str = "BE"

    @property
    def complete(self) -> bool:
        return bool(self.street and self.postal_code and self.city)


class OrganizationConfig(BaseModel):
    """The identity data an Organization/LocalBusiness schema would assert.

    Every field starts null because none of it may be invented: the banner still
    says « Marque et coordonnées à confirmer », and three names currently
    coexist (BEAVER DATA GROUP, Mon Projet Solaire, Solar Belgium). Structured
    data that asserts things nobody supplied is fabrication with a schema — the
    readiness predicates below are what keeps that sentence true mechanically.
    """

    legal_name: str | None = None
    bce_number: str | None = None
    address: OrganizationAddress = Field(default_factory=OrganizationAddress)
    phone: str | None = None
    email: str | None = None
    service_areas: list[str] = Field(default_factory=list)
    logo_path: str | None = None
    installer_partner: str | None = None
    certifications: list[str] = Field(default_factory=list)
    same_as: list[str] = Field(default_factory=list)

    @property
    def organization_schema_ready(self) -> bool:
        """The minimum an `Organization` node may honestly assert: who, legally,
        and under what registration. A brand name alone names nobody."""
        return bool(self.legal_name and self.bce_number)

    @property
    def local_business_schema_ready(self) -> bool:
        """`LocalBusiness` also claims a place and a way to reach it."""
        return (self.organization_schema_ready and self.address.complete
                and bool(self.phone or self.email))


class AnalyticsConfig(BaseModel):
    """First-party only in Phase 4. No vendor tag is configured or emitted."""

    first_party_events: bool = True
    ga4_measurement_id: str | None = None


class SiteConfig(BaseModel):
    site_id: str
    vertical: str
    brand_name: str
    brand_name_is_placeholder: bool = True
    domain: str | None = None
    market: str
    default_language: str
    supported_languages: list[str] = Field(default_factory=list)
    staging: bool = True
    locale_paths: dict[str, str] = Field(default_factory=dict)

    contact: ContactConfig = Field(default_factory=ContactConfig)
    legal: LegalConfig = Field(default_factory=LegalConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    conversion: ConversionConfig
    seo: SeoConfig = Field(default_factory=SeoConfig)
    offer: OfferConfig = Field(default_factory=OfferConfig)
    organization: OrganizationConfig = Field(default_factory=OrganizationConfig)

    # Route definitions the site may link to. A link target absent from here is a
    # 404 waiting to happen, so the renderer refuses to emit it.
    routes: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_canonical_origin(self) -> "SiteConfig":
        origin = (self.seo.canonical_origin or "").strip()
        if not origin:
            return self
        if not origin.startswith("https://"):
            raise ValueError("canonical_origin must be an https:// origin")
        if origin.endswith("/"):
            raise ValueError("canonical_origin must not end with a slash")
        # An internal hostname in a canonical URL tells a crawler that the real
        # address of the page is somewhere it can never reach.
        lowered = origin.lower()
        for forbidden in ("localhost", "127.0.0.1", "0.0.0.0", "::1",
                          "seolead_web", "seolead_api", ".internal", ".local"):
            if forbidden in lowered:
                raise ValueError(
                    f"canonical_origin must not contain {forbidden!r}: a canonical "
                    f"pointing at an internal host is worse than none")
        if self.domain and self.domain.lower() not in lowered:
            raise ValueError(
                f"canonical_origin {origin!r} does not match domain "
                f"{self.domain!r}")
        return self

    @model_validator(mode="after")
    def _check_consent_definitions(self) -> "SiteConfig":
        """Every consent case must be resolvable, and unvalidated text must not
        be able to leave staging.

        The second rule is the same shape as the indexing gate: a consent field
        marked `pending_legal_review: true` may exist only while the site is
        staging. The day someone flips `staging: false` with a placeholder
        consent text still in the form, the loader refuses the configuration
        instead of letting a non-validated legal text collect real consent.
        """
        known_channels = {c.value for c in ConsentChannel}
        for field in self.conversion.fields:
            if field.get("type") != "consent" or not field.get("key"):
                continue
            key = str(field["key"])
            purpose = field.get("consent_purpose") or \
                _LEGACY_CONSENT_PURPOSES.get(key)
            if purpose not in {p.value for p in ConsentPurpose}:
                raise ValueError(
                    f"consent field {key!r} has no resolvable purpose: declare "
                    f"consent_purpose as one of "
                    f"{sorted(p.value for p in ConsentPurpose)}")
            if field.get("consent_channel") is not None and \
                    field.get("consent_channels") is not None:
                raise ValueError(
                    f"consent field {key!r} declares both consent_channel and "
                    f"consent_channels: one case names its channel(s) one way")
            channels = field.get("consent_channels")
            if channels is not None and (not isinstance(channels, list)
                                         or not channels
                                         or len(set(channels)) != len(channels)):
                raise ValueError(
                    f"consent field {key!r}: consent_channels must be a "
                    f"non-empty list without duplicates")
            for channel in (channels or [field.get("consent_channel")]):
                if channel is not None and channel not in known_channels:
                    raise ValueError(
                        f"consent field {key!r} names unknown channel "
                        f"{channel!r}")
            if field.get("required") and purpose != ConsentPurpose.PROCESSING.value:
                raise ValueError(
                    f"consent field {key!r} ({purpose}) may not be required: "
                    f"only PROCESSING consent may condition the submission — a "
                    f"forced choice is not consent")
            if field.get("pending_legal_review") and not self.staging:
                raise ValueError(
                    f"consent field {key!r} carries pending_legal_review and "
                    f"the site is not staging: a non-validated consent text "
                    f"must never collect real consent")
            # A locale variant of a consent text is a legal text of its own.
            # The base text being validated does not validate its translations:
            # a supported locale whose variant is still pending blocks leaving
            # staging exactly like a pending base text, because that locale's
            # form would collect consent on a placeholder.
            for locale in (self.supported_languages or []):
                variant = (field.get("i18n") or {}).get(locale) or {}
                if variant.get("pending_legal_review") and not self.staging:
                    raise ValueError(
                        f"consent field {key!r}: the {locale!r} text is "
                        f"pending_legal_review and the site is not staging — "
                        f"a non-validated consent text must never collect "
                        f"real consent, in any supported locale")
        return self

    @model_validator(mode="after")
    def _check_option_values(self) -> "SiteConfig":
        """No form option may carry a boolean value.

        YAML 1.1 reads `value: YES` as `true`, and the first real lead stored
        `battery_interest: true` because of exactly that. A choice value is an
        enum token the API, the analytics and a future export all read as a
        string; a boolean that happens to round-trip is a corruption with a
        delay on it.
        """
        for field in self.conversion.fields:
            for option in field.get("options") or []:
                if isinstance(option.get("value"), bool):
                    raise ValueError(
                        f"field {field.get('key')!r}: option value "
                        f"{option.get('value')!r} is a boolean — quote it in "
                        f"the YAML (\"YES\"/\"NO\"), YAML 1.1 reads the bare "
                        f"word as a bool")
        return self

    @model_validator(mode="after")
    def _check_publication_safety(self) -> "SiteConfig":
        if not self.domain and not self.staging:
            raise ValueError(
                "a site with no domain cannot be non-staging; there is nowhere "
                "for it to be published to")
        if self.staging and self.seo.allow_indexing:
            raise ValueError(
                "a staging site may not allow indexing; an unfinished site in the "
                "index is not something a later fix undoes")
        if self.seo.allow_indexing and not self.seo.allow_publication:
            raise ValueError(
                "allow_indexing requires allow_publication: a page that is not "
                "served publicly cannot meaningfully be indexed")
        if self.seo.allow_publication and not self.domain:
            raise ValueError(
                "allow_publication requires a domain; there is no public route "
                "to serve content on")
        if self.default_language not in (self.supported_languages or
                                         [self.default_language]):
            raise ValueError("default_language must be one of supported_languages")
        return self

    @property
    def is_publishable(self) -> bool:
        """Whether PUBLISHED content may be served on the public routes.

        The weaker of the two gates. It needs a domain to serve on and an explicit
        owner decision, and it says nothing about crawlers.
        """
        return bool(self.domain) and self.seo.allow_publication

    @property
    def is_indexable(self) -> bool:
        """Whether any page of this site may be indexed at all.

        Unchanged, and deliberately stricter than `is_publishable`: three
        independent conditions, all required. A single flag would be one
        accidental commit away from indexing an unfinished site. A page can be
        publicly readable for a long time before this becomes true.
        """
        return bool(self.domain) and not self.staging and self.seo.allow_indexing

    def canonical_url(self, path: str) -> str:
        """Absolute canonical for a path, or the path itself when no origin is set.

        Returning a relative path is the honest fallback before a domain exists:
        it is incomplete, and it is not a lie about where the page lives.
        """
        origin = (self.seo.canonical_origin or "").rstrip("/")
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{origin}{normalized}" if origin else normalized

    def locale_prefix(self, locale: str) -> str:
        """URL prefix for a locale. `/` for the default when unprefixed."""
        return self.locale_paths.get(locale, f"/{locale}")

    def known_paths(self) -> set[str]:
        return {str(r.get("path")) for r in self.routes if r.get("path")}

    def field_definitions(self) -> dict[str, dict]:
        return {f["key"]: f for f in self.conversion.fields if f.get("key")}

    def consent_definitions(self) -> list[dict]:
        """Every consent case the form offers, fully resolved.

        The version rule is the point: `consent_version` on the field wins, and
        `legal.consent_version` is the fallback — which is exactly what the two
        historical checkboxes have always recorded. The day a validated text
        lands, the change is one YAML edit (label + version + drop
        `pending_legal_review`), and every new capture records the new version
        with no code change.

        A field declaring `consent_channels` is ONE checkbox whose validated
        text names SEVERAL channels: it expands to one case per channel, all
        sharing the field's text version, each stored under a derived key
        (`<field_key>:<channel>`) so every channel keeps its own row and its
        own future revocation. `field_key` is what the submission answers;
        `key` is what the storage records.
        """
        cases: list[dict] = []
        for field in self.conversion.fields:
            if field.get("type") != "consent" or not field.get("key"):
                continue
            key = str(field["key"])
            base = {
                "field_key": key,
                "purpose": field.get("consent_purpose")
                or _LEGACY_CONSENT_PURPOSES[key],
                "version": str(field.get("consent_version")
                               or self.legal.consent_version),
                "required": bool(field.get("required")),
                "pending_legal_review": bool(field.get("pending_legal_review")),
            }
            channels = field.get("consent_channels")
            if channels:
                for channel in channels:
                    cases.append({**base, "key": f"{key}:{channel}",
                                  "channel": channel})
            else:
                cases.append({**base, "key": key,
                              "channel": field.get("consent_channel")})
        return cases


def _load(path: Path) -> SiteConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise InvalidSite(f"site config {path.name} is not valid YAML: {exc}") from exc
    try:
        return SiteConfig(**raw)
    except Exception as exc:
        raise InvalidSite(f"site config {path.name} is invalid: {exc}") from exc


@lru_cache(maxsize=32)
def load_site(site_id: str) -> SiteConfig:
    key = (site_id or "").strip().lower()
    path = SITE_DIR / f"{key}.yaml"
    if not key or not path.exists():
        raise InvalidSite(f"unknown site {site_id!r}")
    return _load(path)


def available_sites() -> list[str]:
    if not SITE_DIR.exists():
        return []
    return sorted(p.stem for p in SITE_DIR.glob("*.yaml"))
