"""Security properties.

Three claims are checked, each of which would be a real incident if false:
the internal API cannot be driven without the shared key, approval in particular
cannot be reached anonymously, and no credential reaches a log line.
"""
from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal
from app.api.deps import require_internal_key
from app.core.config import Settings, get_settings
from app.core.logging import JsonFormatter, redact

KEY = "test-internal-key-not-a-real-secret"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(internal.router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        SEOLEAD_INTERNAL_API_KEY=KEY,
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def unprotected_client():
    """A deployment where the operator forgot to set the key."""
    app = FastAPI()
    app.include_router(internal.router)
    app.dependency_overrides[get_settings] = lambda: Settings(
        SEOLEAD_INTERNAL_API_KEY="",
        SEOLEAD_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    )
    return TestClient(app, raise_server_exceptions=False)


DRAFT_ID = str(uuid.uuid4())

MUTATING_ROUTES = [
    ("post", "/internal/v1/research-jobs",
     {"vertical": "SOLAR_BE", "query": "prix panneaux solaires"}),
    ("post", f"/internal/v1/content/{DRAFT_ID}/approve", {"decided_by": "attacker"}),
    ("post", f"/internal/v1/content/{DRAFT_ID}/reject", {"decided_by": "attacker"}),
    ("post", f"/internal/v1/content/{DRAFT_ID}/request-revision",
     {"decided_by": "attacker"}),
]

READ_ROUTES = [
    ("get", "/internal/v1/verticals", None),
    ("get", "/internal/v1/drafts", None),
    ("get", f"/internal/v1/drafts/{DRAFT_ID}", None),
]


class TestAuthentication:
    @pytest.mark.parametrize("method,path,body", MUTATING_ROUTES + READ_ROUTES)
    def test_no_key_is_rejected(self, client, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401

    @pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
    def test_wrong_key_is_rejected(self, client, method, path, body):
        response = getattr(client, method)(path, json=body,
                                           headers={"X-Internal-Key": "wrong"})
        assert response.status_code == 401

    def test_approval_specifically_cannot_be_reached_anonymously(self, client):
        """The single most damaging unauthenticated action."""
        response = client.post(f"/internal/v1/content/{DRAFT_ID}/approve",
                               json={"decided_by": "attacker"})
        assert response.status_code == 401

    def test_correct_key_is_accepted(self, client):
        response = client.get("/internal/v1/verticals",
                              headers={"X-Internal-Key": KEY})
        assert response.status_code == 200
        assert "SOLAR_BE" in response.json()["profiles"]

    def test_unset_key_fails_closed(self, unprotected_client):
        """An unconfigured key must never mean 'no check'."""
        response = unprotected_client.get("/internal/v1/verticals",
                                          headers={"X-Internal-Key": "anything"})
        assert response.status_code == 503

    def test_dependency_is_attached_to_every_internal_route(self):
        """Belt and braces: a new route added to this router inherits the guard,
        but only if it stays on the router. Assert the router-level dependency."""
        assert any(d.dependency is require_internal_key
                   for d in internal.router.dependencies)


class TestInputValidation:
    def test_unknown_vertical_is_rejected(self, client):
        response = client.post("/internal/v1/research-jobs",
                               json={"vertical": "NOT_A_VERTICAL",
                                     "query": "some query"},
                               headers={"X-Internal-Key": KEY})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_VERTICAL"

    @pytest.mark.parametrize("payload", [
        {},
        {"vertical": "SOLAR_BE"},
        {"query": "some query"},
        {"vertical": "SOLAR_BE", "query": "ab"},
        {"vertical": "SOLAR_BE", "query": "x" * 500},
        {"vertical": "S", "query": "some query"},
        {"vertical": "SOLAR_BE", "query": "valid query", "stop_after": "publish"},
    ])
    def test_malformed_payloads_are_rejected(self, client, payload):
        response = client.post("/internal/v1/research-jobs", json=payload,
                               headers={"X-Internal-Key": KEY})
        assert response.status_code == 422

    def test_approval_requires_an_actor(self, client):
        response = client.post(f"/internal/v1/content/{DRAFT_ID}/approve", json={},
                               headers={"X-Internal-Key": KEY})
        assert response.status_code == 422


class TestSecretRedaction:
    @pytest.mark.parametrize("text", [
        "api_key=sk-abcdefghijklmnop",
        'authorization: "Bearer sk-abcdefghijklmnop"',
        "password=hunter2hunter2",
        '{"secret": "abcdef123456"}',
        "token: ghp_abcdefghijklmnopqrst",
    ])
    def test_credential_shaped_text_is_redacted(self, text):
        assert "REDACTED" in redact(text)

    def test_openai_style_key_is_redacted_even_bare(self):
        assert "sk-livekeyabcdef123456" not in redact(
            "request failed for sk-livekeyabcdef123456")

    def test_formatter_redacts_the_message(self):
        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="", lineno=0,
            msg="upstream said api_key=sk-abcdefghijklmnop is invalid",
            args=(), exc_info=None,
        )
        output = JsonFormatter().format(record)
        assert "sk-abcdefghijklmnop" not in output
        assert "REDACTED" in output

    def test_formatter_redacts_exception_text(self):
        try:
            raise ValueError("token=ghp_abcdefghijklmnopqrst rejected")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="t", level=logging.ERROR, pathname="", lineno=0,
                msg="failed", args=(), exc_info=sys.exc_info(),
            )
            output = JsonFormatter().format(record)
        assert "ghp_abcdefghijklmnopqrst" not in output

    def test_ordinary_text_is_untouched(self):
        message = "research run completed with 5 sources in 4210ms"
        assert redact(message) == message


class TestNoSecretsInRepo:
    def test_env_example_has_no_real_looking_values(self):
        import pathlib

        text = (pathlib.Path(__file__).parents[1] / ".env.example").read_text()
        for line in text.splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            _, _, value = line.partition("=")
            value = value.strip()
            assert not value.startswith("sk-"), line
            assert not value.startswith("ghp_"), line
            # Placeholders and empties only.
            if value and "CHANGE_ME" not in value:
                assert value.startswith(("http://", "https://", "postgresql")) or \
                    value.isdigit() or value in {
                        "dev", "INFO", "openai_compatible", "gpt-4o-mini"}, line
