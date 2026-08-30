"""Freshness of evidence — dates, validity periods, and what "undated" means.

Phase 3.1 reduced freshness to one bit: does the source carry a `published_at`.
That is too coarse for official evidence, where three distinct situations look
identical under that rule:

* an official page with an explicit "last updated" date — usable
* an official page that is clearly current but carries no date — usable with a
  caveat, and NOT the same as an undated blog post
* an archived page describing a scheme that ended in 2023 — must never support a
  2026 claim

So freshness is a status with its own vocabulary, and a validity period is
persisted when a page states one. Nothing is ever fabricated: a missing date stays
missing.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app.services.intent import normalize_query


class FreshnessStatus(StrEnum):
    DATED_CURRENT = "DATED_CURRENT"        # carries a date, within validity
    DATED_EXPIRED = "DATED_EXPIRED"        # carries a date, validity has passed
    UNDATED_CURRENT = "UNDATED_CURRENT"    # no date, but presents as in force
    UNDATED = "UNDATED"                    # no date, no signal either way
    HISTORICAL = "HISTORICAL"              # explicitly archived or superseded

    @property
    def can_support_current_claim(self) -> bool:
        """Whether this evidence may support a claim about the present.

        `UNDATED_CURRENT` can, with a caveat — an official portal describing a
        scheme in the present tense is meaningfully different from a page with no
        date and no signal. `HISTORICAL` and `DATED_EXPIRED` never can.
        """
        return self in (FreshnessStatus.DATED_CURRENT,
                        FreshnessStatus.UNDATED_CURRENT)

    @property
    def is_dated(self) -> bool:
        return self in (FreshnessStatus.DATED_CURRENT, FreshnessStatus.DATED_EXPIRED)


# Pages that announce themselves as no longer in force.
_HISTORICAL_MARKERS = (
    "archive", "archives", "archivee", "page archivee", "n'est plus en vigueur",
    "n'est plus d'application", "supprime depuis", "abroge", "abrogee",
    "ancienne version", "historique",
    # NOT "jusqu'au …": a validity period is not an archival marker. A scheme
    # valid until 31 December 2027 is in force, and treating the phrase as
    # historical would mark every dated scheme as archived. Expiry is decided by
    # comparing the stated end year, below.
    "no longer available", "discontinued", "superseded",
    "niet langer", "afgeschaft",
)
# Pages that assert they describe the current state.
_CURRENT_MARKERS = (
    "actuellement", "a ce jour", "en vigueur", "actuel", "actuelle",
    "derniere mise a jour", "mis a jour le", "cette annee",
    "currently", "in force", "last updated",
    "momenteel", "van kracht", "laatst bijgewerkt",
)

_UPDATED_PATTERNS = (
    re.compile(r"(?:derni[eè]re mise [aà] jour|mis[e]?\s+[aà]\s+jour(?:\s+le)?|"
               r"last updated|laatst bijgewerkt)\s*:?\s*"
               r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|"
               r"\d{4}-\d{2}-\d{2}|"
               r"\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{4})", re.IGNORECASE),
)
_EFFECTIVE_FROM = re.compile(
    r"(?:[aà] partir du|depuis le|en vigueur (?:depuis|[aà] partir du)|"
    r"applicable (?:depuis|[aà] partir du)|effective from|vanaf)\s+"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE)
_EFFECTIVE_UNTIL = re.compile(
    r"(?:jusqu'au|jusqu'[aà]|valable jusqu'au|until|tot en met|tot)\s+"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4})",
    re.IGNORECASE)
_YEAR = re.compile(r"\b(20\d{2})\b")


@dataclass(frozen=True)
class FreshnessAssessment:
    status: FreshnessStatus
    published_at: datetime | None
    updated_at: datetime | None
    effective_from: str | None
    effective_until: str | None
    signals: list[str]
    note: str

    def as_dict(self) -> dict:
        return {
            "freshness_status": self.status.value,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "signals": self.signals,
            "note": self.note,
        }


# ── The year in the URL path ─────────────────────────────────────────────────
# Measured on 2026-08-30, over the 20 sources two probes returned and the 40 the
# authoritative pass returned:
#
#   provider_published_at   0 / 20      the field is dead, on every domain
#   bare year in body      12 / 20      and NOT a publication date — `2008` is a
#                                       price comparison, `2030` the end of a
#                                       scheme, `2001…2005` cited legal acts
#   year in URL path        6 / 9       at brugel, environnement.brussels, cwape
#                                       0 / 10 at energie.wallonie.be
#
# So the date that exists is in the path, and position decides its meaning. In
# `/decisions/2023/fr/DECISION-252-Methodologie-tarifaire-2025-2029.pdf` the
# segment `2023` is when the decision issued; `2025-2029` inside the filename is
# the period it covers. `…-territoire-belge-2030.pdf` is an analysis horizon.
#
# Hence: a segment that IS a year, or that OPENS with a full date — CWaPE names
# documents `2024.02.22-0054-…`. Nothing else. A year glued into words is not a
# date, and treating it as one is how you date a page to its price table.
_URL_PATH_YEAR = re.compile(
    # The segment IS a year — `/news/2025/`, `/decisions/2023/`.
    r"^(20[0-2]\d)$"
    # …or it OPENS with a full date and continues: CWaPE names its documents
    # `2024.02.22-0054-Projet lignes directrices…`. The date is the reference,
    # what follows is the title. Requiring the whole segment to be the date
    # missed six of these, which is how the canary caught the first attempt.
    r"|^(20[0-2]\d)[.\-][01]\d[.\-][0-3]\d(?:\D|$)")

# This year and last. Belgian premiums and grid tariffs change annually — the
# very reason SUBSIDY and GRID_RULE require freshness — so a two-year window is
# the widest that can still be called current. A knob, and openly arbitrary.
_URL_YEAR_CURRENT_WITHIN = 1


def url_path_year(url: str | None) -> int | None:
    """The publication year a URL states in its path, if it states one.

    A signal of PUBLICATION, never of validity: it says when a document issued,
    not whether the scheme it describes is still in force. That is what the
    textual markers say, and this never overrides them.
    """
    if not url:
        return None
    try:
        path = urlparse(url).path or ""
    except ValueError:
        return None
    for segment in path.split("/"):
        match = _URL_PATH_YEAR.match(segment.strip())
        if match:
            return int(match.group(1) or match.group(2))
    return None


def _contains(text: str, markers: tuple[str, ...]) -> str | None:
    normalized = normalize_query(text)
    for marker in markers:
        if normalize_query(marker) in normalized:
            return marker
    return None


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def assess(text: str, *, published_at: datetime | None = None,
           retrieved_at: datetime | None = None,
           now: datetime | None = None,
           url: str | None = None) -> FreshnessAssessment:
    """Classify the freshness of one retrieved page.

    Never invents a date. `effective_from` / `effective_until` are kept as the
    raw strings the page used — parsing every European date format would add
    failure modes without adding truth, and a human reviewer can read them. The
    URL year is kept as an int and NEVER written to `published_at`: a year is
    not a date, and turning `2025` into `2025-01-01` would be an invention.

    The URL year can raise a page's standing only when it is recent, and it can
    never lower a page that says it is in force. A 2023 page marked « en
    vigueur » is worth more than a mute 2025 one, and this ordering says so.
    """
    now = now or datetime.now(timezone.utc)
    text = text or ""
    signals: list[str] = []

    historical = _contains(text, _HISTORICAL_MARKERS)
    current = _contains(text, _CURRENT_MARKERS)
    updated_raw = None
    for pattern in _UPDATED_PATTERNS:
        updated_raw = _first(pattern, text)
        if updated_raw:
            break
    effective_from = _first(_EFFECTIVE_FROM, text)
    effective_until = _first(_EFFECTIVE_UNTIL, text)
    url_year = url_path_year(url)

    if historical:
        signals.append(f"historical_marker:{historical}")
    if current:
        signals.append(f"current_marker:{current}")
    if updated_raw:
        signals.append(f"updated:{updated_raw}")
    if effective_from:
        signals.append(f"effective_from:{effective_from}")
    if effective_until:
        signals.append(f"effective_until:{effective_until}")
    if url_year:
        signals.append(f"url_year:{url_year}")

    # An explicitly archived page never supports a present-tense claim, whatever
    # else it carries.
    if historical:
        return FreshnessAssessment(
            FreshnessStatus.HISTORICAL, published_at, None, effective_from,
            effective_until, signals,
            f"Page presents as no longer in force ({historical}).")

    # An expired validity period is the same refusal, stated by the page itself.
    if effective_until:
        years = [int(y) for y in _YEAR.findall(effective_until)]
        if years and max(years) < now.year:
            return FreshnessAssessment(
                FreshnessStatus.DATED_EXPIRED, published_at, None, effective_from,
                effective_until, signals,
                f"Stated validity ended {effective_until}.")

    if published_at or updated_raw:
        return FreshnessAssessment(
            FreshnessStatus.DATED_CURRENT, published_at, None, effective_from,
            effective_until, signals,
            "Carries a publication or update date.")

    # A recent URL year is a real publication date that was simply never read.
    # `published_at` stays None: the page states a year, not a day.
    if url_year and url_year >= now.year - _URL_YEAR_CURRENT_WITHIN:
        return FreshnessAssessment(
            FreshnessStatus.DATED_CURRENT, None, None, effective_from,
            effective_until, signals,
            f"URL path dates this to {url_year}.")

    if current:
        # The distinction the mission asks for: clearly current but undated is not
        # the same as undated with no signal at all.
        return FreshnessAssessment(
            FreshnessStatus.UNDATED_CURRENT, None, None, effective_from,
            effective_until, signals,
            f"No date, but the page presents as in force ({current}).")

    # An old URL year hardens nothing mechanically — UNDATED already cannot
    # support a present-tense claim — but it turns "we know nothing" into "this
    # issued in 2019", which is what an operator needs to see. Deliberately NOT
    # a new status: `FreshnessStatus` sits under a database CHECK constraint,
    # and a value added without its migration is the drift that cost a
    # production outage on 2026-08-30.
    if url_year:
        return FreshnessAssessment(
            FreshnessStatus.UNDATED, None, None, effective_from, effective_until,
            signals,
            f"URL path dates this to {url_year}, too old to support a claim "
            f"about the present, and the page states no currency.")

    return FreshnessAssessment(
        FreshnessStatus.UNDATED, None, None, effective_from, effective_until,
        signals, "No date and no currency signal.")
