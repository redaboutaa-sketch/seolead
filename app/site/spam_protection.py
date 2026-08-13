"""Spam protection behind a port, starting with the cheap honest signals.

Phase 4 uses a honeypot, a submission-timing floor and a server-side rate limit.
None of them tracks anyone, none needs a third-party script, and together they stop
the overwhelming majority of form spam — which is automated, fast, and fills every
field it finds.

The port exists so that adding Turnstile later is an adapter, not a rewrite of the
lead endpoint. It is deliberately not a CAPTCHA today: a tracking-heavy challenge
on a form that receives no spam yet would cost real conversions to solve a problem
that has not appeared.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SpamVerdict:
    accepted: bool
    reason: str | None = None

    @property
    def rejected(self) -> bool:
        return not self.accepted


@dataclass(frozen=True)
class SubmissionSignals:
    """Everything the check may look at. No personal data appears here."""

    # A field no human sees. Anything in it means an automated fill.
    honeypot_value: str | None = None
    # Milliseconds between form render and submit, reported by the client.
    elapsed_ms: int | None = None
    # A coarse client key — hashed IP or session. Never stored with the lead.
    client_key: str | None = None


class SpamProtectionProvider(Protocol):
    def check(self, signals: SubmissionSignals) -> SpamVerdict: ...


# A human cannot read five questions and type contact details in under this.
_MIN_ELAPSED_MS = 2500
_RATE_WINDOW_SECONDS = 3600
_RATE_MAX_SUBMISSIONS = 5


@dataclass
class HeuristicSpamProtection:
    """Honeypot + timing + per-client rate limit.

    The rate limiter is in-process, which is honest about what it is: one API
    replica today, and a shared store the day there are two. It is a backstop
    against a flood, not the primary defence.
    """

    min_elapsed_ms: int = _MIN_ELAPSED_MS
    window_seconds: int = _RATE_WINDOW_SECONDS
    max_submissions: int = _RATE_MAX_SUBMISSIONS
    _seen: dict[str, deque] = field(default_factory=dict)

    def check(self, signals: SubmissionSignals) -> SpamVerdict:
        if signals.honeypot_value:
            return SpamVerdict(False, "honeypot field was filled")

        if signals.elapsed_ms is not None and signals.elapsed_ms < self.min_elapsed_ms:
            return SpamVerdict(
                False, f"submitted in {signals.elapsed_ms}ms, under the "
                       f"{self.min_elapsed_ms}ms floor")

        if signals.client_key:
            now = time.monotonic()
            bucket = self._seen.setdefault(signals.client_key, deque())
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_submissions:
                return SpamVerdict(
                    False, f"more than {self.max_submissions} submissions in "
                           f"{self.window_seconds // 60} minutes")
            bucket.append(now)

        return SpamVerdict(True)


class AcceptAllSpamProtection:
    """For tests that are not about spam. Never wire this into a live path."""

    def check(self, signals: SubmissionSignals) -> SpamVerdict:
        return SpamVerdict(True)
