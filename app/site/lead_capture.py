"""Lead capture: validation, attribution, persistence, and the export boundary.

The boundary is the point. Prospect 360 ingestion is not open, so Phase 4 must not
pretend it is: a lead is validated, stored locally, attributed, and left in
`PENDING_EXPORT`. `LeadDestination` exists so the day the contract opens, the change
is one adapter and one configuration value — not a rewrite of the endpoint that
already holds real people's contact details.

`LocalLeadDestination` is the default and is honest about what it does. It does not
call anything. A destination that silently succeeded while nothing received the
lead would be the single worst failure mode in this file, because the lead would be
marked handled and never followed up.

Validation is server-side and total. The browser's `type="email"` is a convenience
for the visitor, not a check — anything can POST to this endpoint.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ConsentPurpose, ConversionType, LeadState
from app.core.errors import SeoLeadError
from app.models import CapturedLead, LeadAttribution, LeadConsent, Site
from app.site.config import SiteConfig
from app.site.spam_protection import (HeuristicSpamProtection,
                                      SpamProtectionProvider, SubmissionSignals)

logger = logging.getLogger(__name__)


class LeadRejected(SeoLeadError):
    code = "LEAD_REJECTED"


# Deliberately permissive on the local part and strict on shape. A stricter regex
# rejects valid addresses, and the real verification is a delivered email.
_EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
                    r"(\.[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+$")
_PHONE_CHARS = re.compile(r"[^\d+]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_MAX_TEXT = 200
_MAX_QUALIFICATION_KEYS = 40


@dataclass(frozen=True)
class LeadSubmission:
    """Raw input from the form. Nothing here is trusted."""

    site_id: str
    conversion_type: str
    email: str
    language: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    postcode: str | None = None
    qualification: dict = field(default_factory=dict)
    consent_processing: bool = False
    consent_marketing: bool = False
    # Per-case answers, keyed by the consent field key. The two booleans above
    # remain the legacy spelling of the two historical cases; when a key appears
    # here it wins, so a form that only speaks the new vocabulary works, and a
    # form that only speaks the old one keeps working.
    consents: dict = field(default_factory=dict)
    attribution: dict = field(default_factory=dict)
    signals: SubmissionSignals = field(default_factory=SubmissionSignals)


@dataclass(frozen=True)
class LeadResult:
    lead_id: str
    state: str
    destination: str


class LeadDestination(Protocol):
    """Where a validated lead goes after it is stored locally."""

    code: str

    async def deliver(self, lead: CapturedLead) -> LeadState: ...


class LocalLeadDestination:
    """Phase 4's default: store and stop.

    Returns `PENDING_EXPORT`, which is the truth — the lead is captured and nothing
    downstream has seen it. Reporting `EXPORTED` here would lose leads silently.
    """

    code = "local"

    async def deliver(self, lead: CapturedLead) -> LeadState:
        logger.info("lead captured and held for export",
                    extra={"lead_id": str(lead.id), "site": lead.vertical_code})
        return LeadState.PENDING_EXPORT


def _clean(value: str | None, *, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    stripped = _CONTROL.sub("", str(value)).strip()
    return stripped[:limit] or None


def normalize_email(value: str) -> str:
    email = (_clean(value, limit=320) or "").lower()
    if not _EMAIL.match(email):
        raise LeadRejected(f"not a usable email address: {value[:64]!r}")
    return email


def normalize_phone(value: str | None) -> str | None:
    """Keep digits and a leading +. An unparseable phone is dropped, not guessed.

    A phone number is optional here, so refusing the whole lead over a typo would
    trade a real prospect for a tidy field.
    """
    if value is None:
        return None
    raw = _PHONE_CHARS.sub("", str(value))
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    digits = raw.lstrip("+")
    if not digits.isdigit() or not (6 <= len(digits) <= 15):
        return None
    return ("+" + digits) if raw.startswith("+") else digits


def normalize_postcode(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\w]", "", str(value)).upper()
    return cleaned[:16] or None


def _validate_qualification(raw: dict, config: SiteConfig) -> dict:
    """Keep only answers the site actually defined, coerced to their type.

    An unknown key is dropped rather than stored: the qualification blob is
    operator-visible, and accepting arbitrary keys makes it an injection surface
    for whatever a bot decides to send.
    """
    definitions = config.field_definitions()
    cleaned: dict = {}
    for key, value in list(raw.items())[:_MAX_QUALIFICATION_KEYS]:
        definition = definitions.get(key)
        if not definition or definition.get("type") == "consent":
            continue
        kind = definition.get("type")
        if kind == "choice":
            allowed = {o.get("value") for o in definition.get("options") or []}
            if value in allowed:
                cleaned[key] = value
        elif kind == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            low, high = definition.get("min"), definition.get("max")
            if low is not None and number < low:
                continue
            if high is not None and number > high:
                continue
            cleaned[key] = int(number) if number.is_integer() else number
        elif kind == "postcode":
            pattern = definition.get("pattern")
            postcode = normalize_postcode(value)
            if postcode and (not pattern or re.match(pattern, str(value).strip())):
                cleaned[key] = postcode
        else:
            text = _clean(value, limit=int(definition.get("max_length", _MAX_TEXT)))
            if text:
                cleaned[key] = text
    return cleaned


def _required_missing(submission: LeadSubmission, qualification: dict,
                      config: SiteConfig) -> list[str]:
    missing: list[str] = []
    for definition in config.conversion.fields:
        key = definition.get("key")
        if not definition.get("required") or not key:
            continue
        if definition.get("type") == "consent":
            continue
        if key == "email":
            continue          # validated separately, with its own message
        if key not in qualification and not getattr(submission, key, None):
            missing.append(key)
    return missing


def _attribution_value(raw: dict, key: str, limit: int = 255) -> str | None:
    return _clean(raw.get(key), limit=limit)


def _resolve_consents(submission: LeadSubmission, config: SiteConfig) -> list[dict]:
    """Every consent case the form defines, with the answer this submission gave.

    The site configuration is the authority on WHAT was asked (purpose, channel,
    text version); the submission only supplies the answers. A key the client
    sends that no configuration defines is dropped, exactly like an unknown
    qualification key — the browser does not get to invent a consent case.

    An unanswered case resolves to False: the checkbox was rendered and left
    unticked, and that refusal is a fact worth a row. This holds because every
    defined case is on the form; a case defined but not rendered would need a
    different rule.
    """
    given = {str(k): bool(v) for k, v in (submission.consents or {}).items()}
    legacy = {"consent_processing": submission.consent_processing,
              "consent_marketing": submission.consent_marketing}
    resolved: list[dict] = []
    for case in config.consent_definitions():
        # The submission answers by FORM FIELD key; a multi-channel case
        # expands into several rows that all carry that one answer — the
        # visitor ticked one box whose text names every channel it covers.
        key = case["field_key"]
        granted = given[key] if key in given else bool(legacy.get(key, False))
        resolved.append({**case, "granted": granted})
    return resolved


def _processing_granted(consentements: list[dict],
                        submission: LeadSubmission) -> bool:
    """Whether processing consent was given, whichever vocabulary carried it.

    Falls back to the legacy boolean when no PROCESSING case is defined, so a
    site whose YAML predates per-case definitions keeps its guarantee.
    """
    cases = [c for c in consentements
             if c["purpose"] == ConsentPurpose.PROCESSING.value]
    if cases:
        return all(c["granted"] for c in cases if c["required"]) and \
            any(c["granted"] for c in cases)
    return bool(submission.consent_processing)


async def capture_lead(
    session: AsyncSession, *, submission: LeadSubmission, site: Site,
    config: SiteConfig, vertical_code: str,
    destination: LeadDestination | None = None,
    spam: SpamProtectionProvider | None = None,
) -> LeadResult:
    """Validate, store and attribute one lead. Never writes outside this database."""
    spam = spam or HeuristicSpamProtection()
    verdict = spam.check(submission.signals)
    if verdict.rejected:
        # Logged without any submitted field: a spam log that contains the payload
        # is a copy of the payload.
        logger.warning("lead submission rejected", extra={"reason": verdict.reason})
        raise LeadRejected(f"submission rejected: {verdict.reason}")

    try:
        conversion = ConversionType(submission.conversion_type)
    except ValueError as exc:
        raise LeadRejected(
            f"unknown conversion type {submission.conversion_type!r}") from exc

    consentements = _resolve_consents(submission, config)
    if config.conversion.consent_required and \
            not _processing_granted(consentements, submission):
        raise LeadRejected("consent to process the request is required")

    email = normalize_email(submission.email)
    qualification = _validate_qualification(submission.qualification or {}, config)

    missing = _required_missing(submission, qualification, config)
    if missing:
        raise LeadRejected(f"missing required answer(s): {', '.join(missing)}")

    language = _clean(submission.language, limit=8) or config.default_language
    if language not in (config.supported_languages or [config.default_language]):
        language = config.default_language

    now = datetime.now(timezone.utc)
    source_consentement = _clean((submission.attribution or {}).get("page_path"),
                                 limit=255)
    # The legacy marketing boolean mirrors the `consent_marketing` case when the
    # configuration defines one, so the two spellings can never disagree on the
    # row that export contract v1 reads.
    marketing = next((c["granted"] for c in consentements
                      if c["key"] == "consent_marketing"),
                     bool(submission.consent_marketing))
    lead = CapturedLead(
        site_id=site.id, vertical_code=vertical_code,
        state=LeadState.NEW.value, conversion_type=conversion.value,
        first_name=_clean(submission.first_name, limit=120),
        last_name=_clean(submission.last_name, limit=120),
        email=email,
        phone=normalize_phone(submission.phone),
        postcode=normalize_postcode(submission.postcode
                                    or qualification.get("postcode")),
        language=language,
        qualification=qualification,
        consent_marketing=marketing,
        consent_version=config.legal.consent_version,
        consent_timestamp=now,
        consent_source=source_consentement,
        export_destination=(destination or LocalLeadDestination()).code,
    )
    session.add(lead)
    await session.flush()

    # One row per case the form offered, granted or refused alike. The text
    # version comes from the configuration at THIS instant — the same instant
    # the legacy pair records — so each case stays answerable a year later:
    # which text, what answer, when, from where.
    for cas in consentements:
        session.add(LeadConsent(
            captured_lead_id=lead.id, consent_key=cas["key"],
            purpose=cas["purpose"], channel=cas["channel"],
            granted=cas["granted"], text_version=cas["version"],
            granted_at=now, source=source_consentement))

    raw = submission.attribution or {}
    session.add(LeadAttribution(
        captured_lead_id=lead.id, site_id=site.id, vertical_code=vertical_code,
        published_content_id=raw.get("published_content_id"),
        landing_path=_attribution_value(raw, "landing_path", 512),
        page_path=_attribution_value(raw, "page_path", 512),
        language=language,
        search_intent=_attribution_value(raw, "search_intent", 32),
        keyword_cluster=_attribution_value(raw, "keyword_cluster"),
        channel=_attribution_value(raw, "channel", 64),
        source=_attribution_value(raw, "source"),
        referrer=_attribution_value(raw, "referrer", 1024),
        utm_source=_attribution_value(raw, "utm_source"),
        utm_medium=_attribution_value(raw, "utm_medium"),
        utm_campaign=_attribution_value(raw, "utm_campaign"),
        utm_content=_attribution_value(raw, "utm_content"),
        utm_term=_attribution_value(raw, "utm_term"),
        cta=_attribution_value(raw, "cta", 128),
        conversion_type=conversion.value,
        session_id=_attribution_value(raw, "session_id", 64),
        correlation_id=_attribution_value(raw, "correlation_id", 64),
    ))

    state = await (destination or LocalLeadDestination()).deliver(lead)
    lead.state = state.value
    lead.export_attempts = 0
    await session.flush()

    # No submitted field is logged. The identifier is enough to find the row.
    logger.info("lead stored", extra={"lead_id": str(lead.id),
                                      "state": lead.state,
                                      "conversion": conversion.value})
    return LeadResult(lead_id=str(lead.id), state=lead.state,
                      destination=lead.export_destination)
