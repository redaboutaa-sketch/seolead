"""Explicit, persistable failure codes.

A failure that reaches an operator as a stack trace is a failure they cannot act
on. Every path that can fail carries one of these codes, it is stored on the row
that failed, and the message never contains a credential.
"""
from __future__ import annotations


class ErrorCode:
    LAST30DAYS_UNAVAILABLE = "LAST30DAYS_UNAVAILABLE"
    LAST30DAYS_TIMEOUT = "LAST30DAYS_TIMEOUT"
    LAST30DAYS_CONTRACT_ERROR = "LAST30DAYS_CONTRACT_ERROR"
    RESEARCH_PARTIAL = "RESEARCH_PARTIAL"
    RESEARCH_FAILED = "RESEARCH_FAILED"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"
    CONTENT_GENERATION_FAILED = "CONTENT_GENERATION_FAILED"
    QA_FAILED = "QA_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    INVALID_VERTICAL = "INVALID_VERTICAL"
    INVALID_REQUEST = "INVALID_REQUEST"


class SeoLeadError(Exception):
    """Base error. `code` is what gets persisted and shown; `detail` is bounded."""

    code = ErrorCode.RESEARCH_FAILED
    retryable = False

    def __init__(self, detail: str = "", *, code: str | None = None,
                 retryable: bool | None = None):
        # Bounded: provider errors can carry unbounded external text.
        self.detail = (detail or "")[:500]
        if code:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        super().__init__(f"{self.code}: {self.detail}" if self.detail else self.code)


class ResearchProviderError(SeoLeadError):
    code = ErrorCode.RESEARCH_FAILED


class ResearchUnavailable(ResearchProviderError):
    code = ErrorCode.LAST30DAYS_UNAVAILABLE
    retryable = True


class ResearchTimeout(ResearchProviderError):
    code = ErrorCode.LAST30DAYS_TIMEOUT
    retryable = True


class ResearchContractError(ResearchProviderError):
    """The payload does not honour the agreed contract. Retrying will not fix it."""

    code = ErrorCode.LAST30DAYS_CONTRACT_ERROR
    retryable = False


class LLMNotConfigured(SeoLeadError):
    code = ErrorCode.LLM_NOT_CONFIGURED


class LLMTimeout(SeoLeadError):
    code = ErrorCode.LLM_TIMEOUT
    retryable = True


class LLMProviderError(SeoLeadError):
    code = ErrorCode.LLM_PROVIDER_ERROR
    retryable = True


class InvalidVertical(SeoLeadError):
    code = ErrorCode.INVALID_VERTICAL
