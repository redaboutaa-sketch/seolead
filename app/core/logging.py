"""Structured JSON logging with a credential guard.

The guard is not decoration. Provider adapters pass API keys around in config
objects, and the single most common way a secret escapes is an exception message
that happens to include a URL with a token in it. `_redact` runs on every record.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any

# Anything that looks like a key, either as `key=value` / `"key": "value"` or as a
# bare high-entropy token with a known provider prefix.
#
# The `\"?` before the separator is not cosmetic: this application logs JSON, so
# the overwhelmingly common shape is `"api_key": "value"` with a closing quote
# between the name and the colon. A pattern that only matched `api_key=value`
# would pass every test written by hand and redact nothing in production.
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token|authorization|bearer)"
               r"\"?\s*[=:]\s*\"?([^\s\"',}]+)"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{8,})"),
)

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(
            lambda m: m.group(0).replace(m.group(len(m.groups())), _REDACTED), text
        )
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        # Safe structured context, attached via `extra=`.
        for field in ("correlation_id", "vertical", "keyword_id", "research_run_id",
                      "provider", "duration_ms", "status", "error_code", "draft_id"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    # stderr, not stdout. The CLI emits its result as JSON on stdout, and
    # interleaving log lines there makes `seolead … | jq` fail — which defeats the
    # point of a machine-readable CLI. Docker captures both streams either way.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # These two are chatty and log full request URLs, which can carry tokens.
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("httpcore").setLevel("WARNING")
