"""Phase 4 — the site API surface.

What is being protected here is simple to state and easy to get wrong: **a visitor
must not be able to reach content a human has not approved and published.** The
tests below try every route a crawler or a curious person would try.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import site
from app.core.config import Settings, get_settings

KEY = "test-internal-key-not-a-real-secret"
PREVIEW = "test-preview-token-not-a-real-secret"


def _settings() -> Settings:
    return Settings(
        _env_file=None,          # hermetic — never read the operator's real .env
        SEOLEAD_INTERNAL_API_KEY=KEY,
        SEOLEAD_SITE_PREVIEW_TOKEN=PREVIEW,
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def client(monkeypatch):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(site.router)
    app.dependency_overrides[get_settings] = _settings
    # The preview route reads settings directly rather than through a dependency,
    # because it is checked before any request-scoped wiring exists.
    monkeypatch.setattr("app.core.config.get_settings", _settings)
    return TestClient(app, raise_server_exceptions=False)


class TestSiteApiAuthentication:
    def test_every_site_route_requires_the_internal_key(self, client):
        for path in ("/site/v1/sites/solar_be",
                     "/site/v1/sites/solar_be/content",
                     "/site/v1/sites/solar_be/content/fr/prix-panneaux-solaires",
                     "/site/v1/sites/solar_be/preview/fr/prix-panneaux-solaires"):
            assert client.get(path).status_code == 401, path

    def test_posting_a_lead_requires_the_key(self, client):
        response = client.post("/site/v1/sites/solar_be/leads",
                               json={"conversion_type": "CONTACT",
                                     "email": "a@b.be", "language": "fr"})
        assert response.status_code == 401

    def test_a_wrong_key_is_refused(self, client):
        response = client.get("/site/v1/sites/solar_be",
                              headers={"X-Internal-Key": "wrong"})
        assert response.status_code == 401


class TestSiteConfigEndpoint:
    def test_the_config_reports_the_site_as_not_indexable(self, client):
        """The domain is set and the site is still not indexable.

        This is the assertion that matters after the domain arrived: the API is
        what the frontend trusts for `robots`, `sitemap` and every page's meta,
        so if `indexable` ever flipped here the whole gate would open at once.
        """
        response = client.get("/site/v1/sites/solar_be",
                              headers={"X-Internal-Key": KEY})
        assert response.status_code == 200
        body = response.json()
        assert body["domain"] == "monprojetsolaire.be"
        assert body["seo"]["canonical_origin"] == "https://monprojetsolaire.be"
        assert body["staging"] is True
        assert body["seo"]["allow_indexing"] is False
        assert body["indexable"] is False
        assert body["brand_name"] == "Mon Projet Solaire"
        assert body["brand_name_is_placeholder"] is False

    def test_no_secret_appears_in_the_site_config(self, client):
        body = client.get("/site/v1/sites/solar_be",
                          headers={"X-Internal-Key": KEY}).text
        assert KEY not in body
        assert PREVIEW not in body
        for fragment in ("api_key", "password", "sk-", "token"):
            assert fragment not in body.lower()

    def test_an_unknown_site_is_404(self, client):
        response = client.get("/site/v1/sites/no_such_site",
                              headers={"X-Internal-Key": KEY})
        assert response.status_code == 404

    def test_verification_tokens_are_exposed_and_null_until_supplied(self, client):
        """Les jetons Search Console voyagent avec la config SEO ; null tant
        que le propriétaire n'a rien collé — rien n'est jamais inventé ici."""
        body = client.get("/site/v1/sites/solar_be",
                          headers={"X-Internal-Key": KEY}).json()
        assert body["seo"]["verification"] == {"google": None, "bing": None}


class TestPreviewToken:
    def test_preview_needs_its_own_second_secret(self, client):
        """The internal key alone must not open unpublished content."""
        response = client.get(
            "/site/v1/sites/solar_be/preview/fr/prix-panneaux-solaires",
            headers={"X-Internal-Key": KEY})
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "PREVIEW_UNAUTHORIZED"

    def test_a_wrong_preview_token_is_refused(self, client):
        response = client.get(
            "/site/v1/sites/solar_be/preview/fr/prix-panneaux-solaires",
            headers={"X-Internal-Key": KEY, "X-Preview-Token": "wrong"})
        assert response.status_code == 401


class TestEventValidation:
    def test_an_unknown_event_type_is_refused(self, client):
        response = client.post("/site/v1/sites/solar_be/events",
                               headers={"X-Internal-Key": KEY},
                               json={"event_type": "EXFILTRATE"})
        assert response.status_code in (409, 422)


class TestOpenApiRemainsDisabled:
    def test_the_application_still_publishes_no_schema(self):
        """Phase 2 disabled it. Adding a site router must not undo that."""
        import app.main as main

        assert main.app.openapi_url is None
        assert main.app.docs_url is None
        assert main.app.redoc_url is None
