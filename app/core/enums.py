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


class ObservationStatus(StrEnum):
    """How well we can place a piece of retrieved material IN TIME.

    This is a statement about publication metadata, and nothing else.

    OBSERVED  — retrieved, and we hold a publication date.
    ESTIMATED — retrieved, but undated; we saw it, we cannot place it in time.
    UNKNOWN   — actively contradicted or unsupported by a freshness check.

    Phase 3's live run proved why this must NOT decide factual support. Tavily's
    general search returns no dates, so every web source is ESTIMATED — and while
    `supported` required OBSERVED, the web-research path yielded zero usable
    evidence for any query, forever. Whether a source is dated and whether it
    supports a claim are different questions; `EvidenceStatus` answers the second.
    """

    OBSERVED = "OBSERVED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


# Phase 2/3 name. Kept so existing code and stored rows keep working.
Observability = ObservationStatus


class EvidenceStatus(StrEnum):
    """Whether a specific passage materially supports an atomic claim.

    Independent of ObservationStatus, RelevanceStatus and SourceQuality. A claim
    can be perfectly supported by an undated page, and a dated page can support
    nothing.
    """

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTING = "CONFLICTING"

    @property
    def is_usable_by_writer(self) -> bool:
        """Only SUPPORTED reaches the writer as a fact it may state.

        PARTIALLY_SUPPORTED may be passed separately and explicitly labelled when
        vertical policy allows; it is never presented as established.
        """
        return self is EvidenceStatus.SUPPORTED


class FreshnessRequirement(StrEnum):
    """Whether a claim's truth depends on when it was published.

    "Panels are usually mounted facing south" is timeless. "The regional premium
    is EUR 1,750" is worthless without a date. Treating both the same way is what
    broke Phase 3.
    """

    REQUIRED = "REQUIRED"        # undated evidence cannot fully support it
    PREFERRED = "PREFERRED"      # undated evidence downgrades, does not disqualify
    NOT_REQUIRED = "NOT_REQUIRED"


class AuthorityRequirement(StrEnum):
    """The minimum source authority a claim needs before it may be stated."""

    OFFICIAL = "OFFICIAL"
    INSTITUTIONAL = "INSTITUTIONAL"
    SPECIALIST = "SPECIALIST"
    ANY = "ANY"


class ClaimCategory(StrEnum):
    """What KIND of assertion a claim makes.

    Risk and requirements derive from the category, and the category is matched
    per vertical from configuration — so nothing solar-specific lives in the core.
    """

    SUBSIDY = "SUBSIDY"
    TAX = "TAX"
    REGULATION = "REGULATION"
    GRID_RULE = "GRID_RULE"
    ELIGIBILITY = "ELIGIBILITY"
    GUARANTEED_SAVINGS = "GUARANTEED_SAVINGS"
    ROI = "ROI"
    ENERGY_PRICE = "ENERGY_PRICE"
    # Narrow categories added in Phase 3.2/3.3, each justified by evidence the
    # live authoritative run actually returned (CWaPE and ORES tariff pages).
    TARIFF = "TARIFF"                  # a regulated periodic tariff
    GRID_FEE = "GRID_FEE"              # a connection or network charge
    # Price claims split by WHAT THEY ASSERT, because the evidence each needs
    # differs sharply. Phase 3.4 found 27 of 34 quantified price claims blocked by
    # the market-average bar while asserting no average at all.
    MARKET_AVERAGE = "MARKET_AVERAGE"  # "the average Belgian installation costs X"
    OBSERVED_PRICE_RANGE = "OBSERVED_PRICE_RANGE"   # "source S reports X–Y"
    MARKET_PRICE = "MARKET_PRICE"      # unqualified price mention — residual
    VENDOR_PRICE = "VENDOR_PRICE"      # a specific vendor's own displayed price
    PRODUCT_SPEC = "PRODUCT_SPEC"
    GENERAL = "GENERAL"


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


class QALayer(StrEnum):
    """WHAT a review examined, as opposed to HOW it was made.

    `QAType` answers "deterministic or model-assisted"; this answers "facts or
    presentation". Phase 4 needed both: the publication gate must know that a
    draft has a passing factual review AND a passing SEO review, and inferring
    that from finding codes broke the moment a review came back clean with no
    codes at all.
    """

    FACTUAL = "FACTUAL"
    SEO = "SEO"
    ADVISORY = "ADVISORY"


class KeywordStatus(StrEnum):
    NEW = "NEW"
    RESEARCHING = "RESEARCHING"
    RESEARCHED = "RESEARCHED"
    FAILED = "FAILED"


class SiteStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class PublicationState(StrEnum):
    """Where a piece of content sits between generation and a live page.

    `APPROVED` and `PUBLISHED` are deliberately different states. A human has
    approved the *content*; whether it is live also depends on the site having a
    domain, a launch decision and a publication action. Collapsing the two would
    make "a person said this is fit to publish" and "this is on the internet" the
    same fact, and only one of them is reversible by the owner.
    """

    DRAFT = "DRAFT"
    QA_FAILED = "QA_FAILED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    STAGED = "STAGED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


# The only states whose content may be served on a public route. Staging is not
# here: a staged page is reachable through the preview path alone.
PUBLIC_PUBLICATION_STATES: frozenset[PublicationState] = frozenset({
    PublicationState.PUBLISHED,
})


class LeadState(StrEnum):
    """A captured lead's journey out of this system.

    Phase 4 stops at PENDING_EXPORT: the Prospect 360 ingestion boundary is not
    open, and a lead that claims to be exported when nothing received it is worse
    than one that honestly waits.
    """

    NEW = "NEW"
    PENDING_EXPORT = "PENDING_EXPORT"
    EXPORTING = "EXPORTING"
    EXPORTED = "EXPORTED"
    EXPORT_FAILED = "EXPORT_FAILED"
    REJECTED_SPAM = "REJECTED_SPAM"
    ARCHIVED = "ARCHIVED"


class SiteEventType(StrEnum):
    """First-party analytics. Deliberately coarse.

    Every event here answers a question about the funnel. None of them tracks a
    person across sites, and none stores behaviour that the funnel does not need.
    """

    PAGE_VIEW = "PAGE_VIEW"
    CTA_CLICK = "CTA_CLICK"
    FORM_STARTED = "FORM_STARTED"
    FORM_STEP_COMPLETED = "FORM_STEP_COMPLETED"
    FORM_SUBMITTED = "FORM_SUBMITTED"
    LEAD_CREATED = "LEAD_CREATED"


class ConversionType(StrEnum):
    ESTIMATE_REQUEST = "ESTIMATE_REQUEST"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    CONTACT = "CONTACT"
    TOOL_COMPLETION = "TOOL_COMPLETION"
