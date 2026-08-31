"""This campaign is French only — owner decision, 2026-08-31.

Dutch will serve a future energy campaign in the Netherlands, not this one.

The consequence is recorded rather than glossed: the Flemish market is NOT
addressed by this campaign. A Dutch-speaking visitor in Belgium gets the site in
French, no page is served in their language, and no Flemish lead is captured
here. That is a commercial choice, and it is the kind that gets forgotten and
later mistaken for an oversight.

Nothing of the Dutch machinery is deleted. Routes, i18n plumbing and the
« À TRADUIRE PAR UN NATIF » placeholders stay: they were built, they work, and a
Dutch campaign will want them back.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from app.site.config import SiteConfig

CONFIG = pathlib.Path("config/sites/solar_be.yaml")


@pytest.fixture
def raw():
    return yaml.safe_load(CONFIG.read_text())


class TestTheCampaignIsFrenchOnly:
    def test_only_french_is_supported(self, raw):
        assert SiteConfig(**raw).supported_languages == ["fr"]

    def test_no_route_declares_a_dutch_locale(self, raw):
        offenders = [r["path"] for r in raw["routes"] if "nl" in r.get("locales", [])]
        assert offenders == []


class TestTheStagingExitGuardIsGreen:
    """The verdict that matters: the config now accepts `staging: false`.

    It did not before. Every Dutch consent variant carries
    `pending_legal_review`, and the loader refuses to leave staging while a
    SUPPORTED locale has one — a locale whose form would collect consent on a
    placeholder. Dropping `nl` from the supported set does not weaken that rule:
    it removes the locale the rule was protecting.
    """

    def test_the_configuration_now_accepts_leaving_staging(self, raw):
        public = SiteConfig(**{**raw, "staging": False})
        assert public.is_publishable is True

    def test_leaving_staging_is_still_not_indexing(self, raw):
        """Two decisions — both now made on the live file, so the mechanism is
        pinned on a fixture that closes the second one back."""
        public = SiteConfig(**{**raw, "staging": False,
                               "seo": {**raw["seo"], "allow_indexing": False}})
        assert public.is_indexable is False

    def test_restoring_dutch_blocks_again_until_the_texts_are_validated(self, raw):
        """The guard is not disarmed, only unaddressed.

        Re-declaring `nl` the day a Dutch campaign starts brings the block back,
        which is exactly what should happen: the placeholders are still
        placeholders.
        """
        with pytest.raises(ValueError, match="pending_legal_review"):
            SiteConfig(**{**raw, "staging": False,
                          "supported_languages": ["fr", "nl"]})


class TestTheDutchMachineryIsKeptIntact:
    def test_the_dutch_route_file_still_exists(self):
        assert pathlib.Path("web/app/nl/demande-etude/page.tsx").exists()
        assert pathlib.Path("web/app/nl/layout.tsx").exists()

    def test_the_route_refuses_to_serve_an_undeclared_locale(self):
        """Kept but inert: it 404s rather than rendering a page the API would
        reject anyway — a submission with `language: "nl"` is refused server-side
        against `supported_languages`, and a page that can only collect a
        rejection has no business being reachable."""
        source = pathlib.Path("web/app/nl/demande-etude/page.tsx").read_text()
        assert "notFound()" in source
        assert 'supported_languages?.includes("nl")' in source

    def test_the_dutch_placeholders_are_still_in_the_configuration(self, raw):
        """They are the work a native translator will revise, not restart."""
        consent_fields = [f for f in raw["conversion"]["fields"]
                          if f.get("type") == "consent"]
        assert consent_fields
        for field in consent_fields:
            variant = (field.get("i18n") or {}).get("nl") or {}
            assert variant.get("label"), field["key"]
            assert variant.get("pending_legal_review") is True, field["key"]
