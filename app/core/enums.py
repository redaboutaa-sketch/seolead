"""Explicit state vocabularies.

Two of these are not ours: `SourceState` and `FreshnessVerdict` are the upstream
Last30Days agent contract, adopted verbatim rather than re-invented. The reason is
in `SourceState.is_clean_empty` — the distinction between "the source looked and
found nothing" and "we could not look" is the whole point, and flattening it would
turn a rate-limit into a false claim about the world.
"""
from __future__ import annotations

from enum import StrEnum


class SourceState(StrEnum):
    """The ten upstream source states. Do not add an eleventh without upstream."""

    OK = "ok"
    NO_RESULTS = "no-results"
    PARTIAL = "partial"
    RATE_LIMITED = "rate-limited"
    AUTH_FAILED = "auth-failed"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    SCHEMA_DRIFT = "schema-drift"
    SKIPPED_UNCONFIGURED = "skipped-unconfigured"
    ERROR = "error"

    @property
    def produced_items(self) -> bool:
        return self in (SourceState.OK, SourceState.PARTIAL)

    @property
    def is_clean_empty(self) -> bool:
        """ONLY `no-results` means the source completed and found nothing.

        Everything else that produced no items is a non-observation, not evidence
        of absence.
        """
        return self is SourceState.NO_RESULTS

    @property
    def is_degraded(self) -> bool:
        return self in (
            SourceState.RATE_LIMITED, SourceState.AUTH_FAILED,
            SourceState.UNREACHABLE, SourceState.TIMEOUT,
            SourceState.SCHEMA_DRIFT, SourceState.ERROR,
        )

    @property
    def was_attempted(self) -> bool:
        """A source nobody configured was never asked; it did not fail."""
        return self is not SourceState.SKIPPED_UNCONFIGURED


class FreshnessVerdict(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"


class Observability(StrEnum):
    """How much we actually know about a claim.

    OBSERVED  — a source we retrieved states it, and we hold the URL.
    ESTIMATED — derived or inferred; must never be presented as fact.
    UNKNOWN   — we do not know. Never upgraded by guessing.
    """

    OBSERVED = "OBSERVED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class ContentType(StrEnum):
    ARTICLE = "ARTICLE"
    GUIDE = "GUIDE"
    COMPARISON = "COMPARISON"
    LANDING_PAGE = "LANDING_PAGE"
    # Declared but not selectable in Phase 2 — the selector must never return one
    # of these until the vertical config and QA rules for them exist.
    LOCAL_PAGE = "LOCAL_PAGE"
    FAQ_PAGE = "FAQ_PAGE"
    CALCULATOR = "CALCULATOR"
    SIMULATOR = "SIMULATOR"
    PROGRAMMATIC_PAGE = "PROGRAMMATIC_PAGE"


PHASE2_CONTENT_TYPES: frozenset[ContentType] = frozenset({
    ContentType.ARTICLE,
    ContentType.GUIDE,
    ContentType.COMPARISON,
    ContentType.LANDING_PAGE,
})


class SearchIntent(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    COMMERCIAL = "COMMERCIAL"
    TRANSACTIONAL = "TRANSACTIONAL"
    NAVIGATIONAL = "NAVIGATIONAL"
    LOCAL = "LOCAL"


class ContentStatus(StrEnum):
    BRIEF_CREATED = "BRIEF_CREATED"
    DRAFT_CREATED = "DRAFT_CREATED"
    QA_PENDING = "QA_PENDING"
    QA_PASSED = "QA_PASSED"
    QA_FAILED = "QA_FAILED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVISION = "NEEDS_REVISION"


class QAStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class QAType(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    LLM_ASSISTED = "LLM_ASSISTED"


class KeywordStatus(StrEnum):
    NEW = "NEW"
    RESEARCHING = "RESEARCHING"
    RESEARCHED = "RESEARCHED"
    FAILED = "FAILED"


class SiteStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
