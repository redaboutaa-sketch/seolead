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

from app.core.errors import SeoLeadError

SITE_DIR = Path(__file__).resolve().parents[2] / "config" / "sites"


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
    def _check_publication_safety(self) -> "SiteConfig":
        if not self.domain and not self.staging:
            raise ValueError(
                "a site with no domain cannot be non-staging; there is nowhere "
                "for it to be published to")
        if self.staging and self.seo.allow_indexing:
            raise ValueError(
                "a staging site may not allow indexing; an unfinished site in the "
                "index is not something a later fix undoes")
        if self.default_language not in (self.supported_languages or
                                         [self.default_language]):
            raise ValueError("default_language must be one of supported_languages")
        return self

    @property
    def is_indexable(self) -> bool:
        """Whether any page of this site may be indexed at all.

        Three independent conditions, all required. A single flag would be one
        accidental commit away from indexing an unfinished site.
        """
        return bool(self.domain) and not self.staging and self.seo.allow_indexing

    def locale_prefix(self, locale: str) -> str:
        """URL prefix for a locale. `/` for the default when unprefixed."""
        return self.locale_paths.get(locale, f"/{locale}")

    def known_paths(self) -> set[str]:
        return {str(r.get("path")) for r in self.routes if r.get("path")}

    def field_definitions(self) -> dict[str, dict]:
        return {f["key"]: f for f in self.conversion.fields if f.get("key")}


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
