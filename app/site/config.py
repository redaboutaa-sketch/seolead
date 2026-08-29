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
            channel = field.get("consent_channel")
            if channel is not None and \
                    channel not in {c.value for c in ConsentChannel}:
                raise ValueError(
                    f"consent field {key!r} names unknown channel {channel!r}")
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
        """
        cases: list[dict] = []
        for field in self.conversion.fields:
            if field.get("type") != "consent" or not field.get("key"):
                continue
            key = str(field["key"])
            cases.append({
                "key": key,
                "purpose": field.get("consent_purpose")
                or _LEGACY_CONSENT_PURPOSES[key],
                "channel": field.get("consent_channel"),
                "version": str(field.get("consent_version")
                               or self.legal.consent_version),
                "required": bool(field.get("required")),
                "pending_legal_review": bool(field.get("pending_legal_review")),
            })
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
