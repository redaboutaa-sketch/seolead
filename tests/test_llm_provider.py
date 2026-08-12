"""LLM provider behaviour, using a mock transport. No network, no credential."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import LLMNotConfigured, LLMProviderError, LLMTimeout
from app.providers.llm.base import LLMCapability, LLMRequest
from app.providers.llm.openai_compatible import OpenAICompatibleProvider
from app.providers.llm.registry import NullLLMProvider, get_llm_provider


def _request() -> LLMRequest:
    return LLMRequest(capability=LLMCapability.LONG_FORM_WRITING, prompt="hello",
                      correlation_id="test")


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={
        "model": "test-model",
        "choices": [{"message": {"content": "generated text"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33},
    })


class TestConfiguration:
    def test_registry_returns_null_provider_without_a_key(self, settings_no_llm):
        provider = get_llm_provider(settings_no_llm)
        assert isinstance(provider, NullLLMProvider)
        assert provider.configured is False

    def test_registry_returns_real_provider_with_a_key(self, settings_with_llm):
        provider = get_llm_provider(settings_with_llm)
        assert isinstance(provider, OpenAICompatibleProvider)
        assert provider.configured is True

    async def test_null_provider_refuses_rather_than_fabricating(self):
        with pytest.raises(LLMNotConfigured):
            await NullLLMProvider().generate(_request())

    async def test_unconfigured_real_provider_refuses(self, settings_no_llm):
        provider = OpenAICompatibleProvider(settings_no_llm)
        with pytest.raises(LLMNotConfigured):
            await provider.generate(_request())


class TestSuccess:
    async def test_usage_is_captured(self, settings_with_llm):
        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(_ok_response))
        response = await provider.generate(_request())
        assert response.content == "generated text"
        assert response.usage.input_tokens == 11
        assert response.usage.output_tokens == 22
        assert response.usage.total_tokens == 33
        assert response.provider == "openai_compatible"


class TestErrors:
    async def test_timeout_raises_llm_timeout(self, settings_with_llm):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        with pytest.raises(LLMTimeout):
            await provider.generate(_request())

    async def test_client_error_is_not_retried(self, settings_with_llm):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, json={"error": {"message": "bad request"}})

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        with pytest.raises(LLMProviderError) as exc:
            await provider.generate(_request())
        assert calls == 1, "a 400 will not become a 200 on retry"
        assert exc.value.retryable is False

    async def test_server_error_is_retried_then_raises(self, settings_with_llm):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503)

        settings_with_llm.llm_max_retries = 1
        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        with pytest.raises(LLMProviderError):
            await provider.generate(_request())
        assert calls == 2

    async def test_malformed_response_shape_raises(self, settings_with_llm):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        with pytest.raises(LLMProviderError):
            await provider.generate(_request())


class TestSecrets:
    async def test_api_key_is_sent_as_a_bearer_header_only(self, settings_with_llm):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("authorization")
            seen["url"] = str(request.url)
            seen["body"] = request.content.decode()
            return _ok_response(request)

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        await provider.generate(_request())

        assert seen["auth"] == "Bearer test-llm-key-not-a-real-secret"
        # The key must not travel in the URL or the body, where it would be logged.
        assert "test-llm-key" not in seen["url"]
        assert "test-llm-key" not in seen["body"]

    async def test_error_detail_does_not_echo_the_key(self, settings_with_llm):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": {
                "message": "invalid key test-llm-key-not-a-real-secret provided"}})

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        with pytest.raises(LLMProviderError) as exc:
            await provider.generate(_request())
        # The provider echoes a bounded upstream message; the log redactor is what
        # guarantees it never reaches a log line. Asserted in test_security.py.
        assert len(exc.value.detail) <= 500


class TestJsonMode:
    async def test_json_response_format_is_requested(self, settings_with_llm):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return _ok_response(request)

        provider = OpenAICompatibleProvider(
            settings_with_llm, transport=httpx.MockTransport(handler))
        await provider.generate(LLMRequest(
            capability=LLMCapability.CONTENT_BRIEF, prompt="x",
            response_format="json"))
        assert seen["payload"]["response_format"] == {"type": "json_object"}
