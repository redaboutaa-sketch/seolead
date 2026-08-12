"""OpenAI-compatible chat-completions adapter.

Written against the `/chat/completions` shape so it serves OpenAI, DeepSeek,
Together, a local vLLM, or anything else speaking that dialect — base URL and
model are configuration. No credential is ever an argument, a default, or a log
field.

The pipeline is designed to run without this provider configured. `configured` is
checked before any call so the caller can stop cleanly at LLM_NOT_CONFIGURED
rather than discovering the problem as a 401 from a third party.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.core.config import Settings
from app.core.errors import LLMNotConfigured, LLMProviderError, LLMTimeout
from app.providers.llm.base import LLMRequest, LLMResponse, LLMUsage

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    code = "openai_compatible"

    def __init__(self, settings: Settings, *,
                 transport: httpx.AsyncBaseTransport | None = None):
        self._api_key = settings.llm_api_key.strip()
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds
        self._max_retries = max(0, settings.llm_max_retries)
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.configured:
            raise LLMNotConfigured(
                "no API key configured for the OpenAI-compatible provider"
            )

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url, timeout=self._timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        "/chat/completions",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
            except httpx.TimeoutException as exc:
                last_error = LLMTimeout(type(exc).__name__)
            except httpx.HTTPError as exc:
                last_error = LLMProviderError(type(exc).__name__)
            else:
                # 4xx other than 429 will not succeed on retry — fail immediately
                # rather than burning the retry budget and the operator's time.
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = LLMProviderError(
                        f"HTTP {response.status_code}", retryable=True
                    )
                elif response.status_code >= 400:
                    raise LLMProviderError(
                        f"HTTP {response.status_code}: {_safe_detail(response)}",
                        retryable=False,
                    )
                else:
                    return _parse_response(
                        response, self.code, self._model,
                        int((time.monotonic() - started) * 1000),
                    )

            if attempt < self._max_retries:
                await asyncio.sleep(min(8.0, 1.5 ** (attempt + 1)))

        assert last_error is not None
        raise last_error


def _parse_response(response: httpx.Response, provider: str, model: str,
                    latency_ms: int) -> LLMResponse:
    try:
        body = response.json()
        choice = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(f"unexpected response shape: {type(exc).__name__}") from exc

    raw_usage = body.get("usage") or {}
    usage = LLMUsage(
        input_tokens=int(raw_usage.get("prompt_tokens") or 0),
        output_tokens=int(raw_usage.get("completion_tokens") or 0),
        total_tokens=int(raw_usage.get("total_tokens") or 0),
    )
    return LLMResponse(
        content=choice or "",
        provider=provider,
        model=str(body.get("model") or model),
        usage=usage,
        latency_ms=latency_ms,
    )


def _safe_detail(response: httpx.Response) -> str:
    """Bounded and never echoing the request — an error body can quote headers."""
    try:
        body = response.json()
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("type") or "")[:200]
        return str(body)[:200]
    except ValueError:
        return response.text[:200]
