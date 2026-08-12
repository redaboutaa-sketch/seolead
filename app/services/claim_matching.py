"""Claim ↔ passage matching — the Phase 3.3 precision fix.

Phase 3.2's live run inflated `TRUE_CONFLICT` from 11 to 163. The conflict
classifier was not at fault; its input was. `passage_supports_claim` accepted a
two-content-word overlap, and across 23 sources about one topic almost any two
statements share two words:

    claim   "Le tarif prosumer dépend de la puissance de l'onduleur."
    passage "Le prix moyen d'une installation photovoltaïque est de 5 000 €."

Shared: `photovoltaique`, `installation`. Two words, one about a grid tariff and
one about a market price — then their unrelated numbers were compared and recorded
as a disagreement.

The fix is a staged matcher that asks whether a passage is about the *same
proposition*, not whether it shares vocabulary:

    A  topic alignment      discriminative terms only; generic ones cannot carry it
    B  head-concept match   the claim's semantic head must be present
    C  numeric typing       €5 000 and 5 ans are not comparable quantities
    D  region compatibility a Walloon passage cannot support a Brussels claim
    E  category alignment   a grid-rule page does not establish a market price

Every decision carries a reason code. A matcher whose refusals cannot be inspected
is a matcher nobody can tune, and Phase 3.2 spent a whole phase discovering that.

Precision is preferred to recall throughout: missing a valid candidate costs one
supported claim, while a false pairing manufactures a conflict that blocks a draft.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.enums import ClaimCategory
from app.services.intent import normalize_query
from app.services.relevance import _stem
from app.services.region import Region, detect_region
from app.verticals.profile import VerticalProfile


class MatchReason(StrEnum):
    """Why a pairing was accepted or refused. Always populated."""

    MATCHED_HEAD_CONCEPT = "MATCHED_HEAD_CONCEPT"
    MATCHED_TOPIC_TERMS = "MATCHED_TOPIC_TERMS"
    NUMERIC_AGREES = "NUMERIC_AGREES"
    NUMERIC_DISAGREES = "NUMERIC_DISAGREES"
    # Refusals
    INSUFFICIENT_TOPIC_ALIGNMENT = "INSUFFICIENT_TOPIC_ALIGNMENT"
    GENERIC_OVERLAP_ONLY = "GENERIC_OVERLAP_ONLY"
    HEAD_CONCEPT_ABSENT = "HEAD_CONCEPT_ABSENT"
    NUMERIC_TYPE_MISMATCH = "NUMERIC_TYPE_MISMATCH"
    REGION_MISMATCH = "REGION_MISMATCH"
    CATEGORY_MISMATCH = "CATEGORY_MISMATCH"


class NumericType(StrEnum):
    MONEY = "MONEY"
    PERCENT = "PERCENT"
    YEAR = "YEAR"
    DATE = "DATE"
    DURATION = "DURATION"
    ENERGY = "ENERGY"
    POWER = "POWER"
    RATE = "RATE"          # a quantity per unit: €/Wc, €/kWh
    COUNT = "COUNT"


@dataclass(frozen=True)
class NumericEntity:
    raw: str
    digits: str
    type: NumericType

    def as_dict(self) -> dict:
        return {"raw": self.raw, "digits": self.digits, "type": self.type.value}


# Ordered: the first pattern to match wins, so a rate is typed before the money or
# energy unit inside it is seen on its own.
_NUMERIC_PATTERNS: tuple[tuple[NumericType, re.Pattern[str]], ...] = (
    (NumericType.RATE, re.compile(
        r"(\d[\d\s.,]*)\s*(?:€|eur|euros?)\s*(?:/|par)\s*"
        r"(?:wc|wp|kwc|kwp|kwh|mwh|m²|m2|an|mois)", re.IGNORECASE)),
    (NumericType.PERCENT, re.compile(r"(\d[\d.,]*)\s*%")),
    (NumericType.MONEY, re.compile(
        r"(?:€|\$|£)\s*(\d[\d\s.,]*)|(\d[\d\s.,]*)\s*(?:€|\$|£|eur\b|euros?\b|"
        r"cents?\b)", re.IGNORECASE)),
    (NumericType.POWER, re.compile(
        r"(\d[\d\s.,]*)\s*(?:kwc|kwp|kw\b|mw\b|wc\b|wp\b|watt[-\s]?cr[eê]te)",
        re.IGNORECASE)),
    (NumericType.ENERGY, re.compile(
        r"(\d[\d\s.,]*)\s*(?:kwh|mwh|gwh)\b", re.IGNORECASE)),
    (NumericType.DURATION, re.compile(
        r"(\d[\d.,]*)\s*(?:ans?\b|années?\b|mois\b|jaar\b|years?\b|jours?\b)",
        re.IGNORECASE)),
    (NumericType.DATE, re.compile(
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2})")),
    (NumericType.YEAR, re.compile(r"(?<![\w/])((?:19|20)\d{2})(?![\w/])")),
    (NumericType.COUNT, re.compile(r"(?<![\w/])(\d[\d\s.,]*)(?![\w/])")),
)

# Function words and units that never carry topic. Language-level, not domain.
_STOPWORDS = frozenset({
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "en", "au",
    "aux", "pour", "par", "sur", "dans", "avec", "sans", "est", "sont", "sera",
    "cette", "ces", "son", "sa", "ses", "leur", "leurs", "qui", "que", "dont",
    "plus", "moins", "tres", "bien", "aussi", "donc", "mais", "car", "selon",
    "the", "of", "and", "or", "for", "in", "on", "with", "to", "is", "are",
    "het", "een", "van", "voor", "met", "zonder", "op", "zijn", "wordt",
    "euro", "euros", "kwh", "kwc", "kwp", "ans", "annee", "annees", "mois",
})


def _tokens(text: str) -> list[str]:
    """Discriminative tokens, lightly stemmed.

    Stemming is shared with the relevance gate so `solaires` and `solaire` are one
    term in both. Without it a configured generic term would fail to mask its own
    plural, and a claim would fail to match a passage that used the singular.
    """
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", normalize_query(text or ""))
            if len(t) > 2 and t not in _STOPWORDS]


def extract_numerics(text: str) -> list[NumericEntity]:
    """Type every quantity in a text.

    Typing is what stops "€5 000" being compared with "5 ans". Positions already
    consumed by a more specific pattern are masked, so a rate is not re-read as a
    bare money amount.
    """
    entities: list[NumericEntity] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < e and end > s for s, e in consumed)

    for numeric_type, pattern in _NUMERIC_PATTERNS:
        for match in pattern.finditer(text or ""):
            if overlaps(match.start(), match.end()):
                continue
            raw = next((g for g in match.groups() if g), match.group(0))
            digits = re.sub(r"\D", "", raw)
            if not digits:
                continue
            consumed.append((match.start(), match.end()))
            entities.append(NumericEntity(raw=raw.strip(), digits=digits,
                                          type=numeric_type))
    return entities


@dataclass
class Concepts:
    """Structured view of a claim or a passage."""

    text: str
    topic_terms: frozenset[str]          # discriminative terms only
    generic_terms: frozenset[str]        # present, but cannot carry a match
    head_phrase: str | None
    phrases: frozenset[str]              # every domain concept phrase present
    region: Region
    numerics: list[NumericEntity] = field(default_factory=list)
    category: ClaimCategory | None = None

    def numeric_types(self) -> set[NumericType]:
        return {n.type for n in self.numerics}

    def as_dict(self) -> dict:
        return {
            "topic_terms": sorted(self.topic_terms),
            "generic_terms": sorted(self.generic_terms),
            "head_phrase": self.head_phrase,
            "phrases": sorted(self.phrases),
            "region": self.region.value,
            "numerics": [n.as_dict() for n in self.numerics],
            "category": self.category.value if self.category else None,
        }


def _generic_terms(profile: VerticalProfile) -> frozenset[str]:
    """Terms that are context, not topic, *in this vertical*.

    Deliberately per-vertical: `solaire` is generic for Solar Belgium and highly
    discriminative for a vertical about roofing. Hard-coding it globally would
    break the second vertical the moment one exists.
    """
    configured = getattr(profile, "generic_terms", None) or []
    terms: set[str] = set()
    for term in configured:
        terms.update(_tokens(term))
    return frozenset(terms)


def _concept_phrases(profile: VerticalProfile) -> tuple[str, ...]:
    """Multi-word domain concepts, longest first so the most specific wins."""
    configured = list(getattr(profile, "concept_phrases", None) or [])
    for terms in (profile.claim_categories or {}).values():
        configured.extend(t for t in terms if " " in t)
    normalized = {normalize_query(p) for p in configured if p and p.strip()}
    return tuple(sorted((p for p in normalized if p), key=len, reverse=True))


def _head_phrase(normalized: str, phrases: tuple[str, ...],
                 topic_terms: frozenset[str]) -> tuple[str | None, frozenset[str]]:
    """The claim's semantic head, and every concept phrase it contains.

    A configured concept phrase is preferred — "tarif prosumer" is exactly the kind
    of head that decides whether two statements are about the same thing. Failing
    that, a bigram of adjacent discriminative terms; failing that, the single most
    distinctive term.
    """
    positions: dict[str, int] = {}
    for phrase in phrases:
        found = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized)
        if found:
            positions[phrase] = found.start()
    present = frozenset(positions)
    if present:
        # Earliest wins, longest breaking a tie. In "Le tarif prosumer dépend de
        # la puissance installée" the head is the subject, and picking the longest
        # string instead would choose "puissance installee" — the object.
        head = min(positions, key=lambda p: (positions[p], -len(p)))
        return head, present

    words = [w for w in normalized.split() if w in topic_terms]
    for first, second in zip(words, words[1:]):
        return f"{first} {second}", present
    return (words[0] if words else None), present


def extract_concepts(text: str, profile: VerticalProfile, *,
                     category: ClaimCategory | None = None,
                     region: Region | None = None) -> Concepts:
    normalized = normalize_query(text or "")
    generic = _generic_terms(profile)
    all_terms = frozenset(_tokens(text))
    topic_terms = frozenset(all_terms - generic)

    head, phrases = _head_phrase(normalized, _concept_phrases(profile), topic_terms)

    return Concepts(
        text=text or "",
        topic_terms=topic_terms,
        generic_terms=frozenset(all_terms & generic),
        head_phrase=head,
        phrases=phrases,
        region=region if region is not None else detect_region(text or "").region,
        numerics=extract_numerics(text or ""),
        category=category,
    )


@dataclass
class MatchResult:
    supports: bool
    agrees_numerically: bool | None
    score: float
    reasons: list[MatchReason] = field(default_factory=list)
    detail: str = ""

    def as_dict(self) -> dict:
        return {"supports": self.supports,
                "agrees_numerically": self.agrees_numerically,
                "score": round(self.score, 3),
                "reasons": [r.value for r in self.reasons],
                "detail": self.detail}


# A claim and a passage must share this many discriminative terms before topic
# alignment counts, when no head concept matched. Three, not two: two was the
# Phase 3.2 defect, and across one topical corpus two generic-adjacent words are
# almost guaranteed.
_MIN_TOPIC_OVERLAP = 3
# Share of the claim's discriminative terms the passage must cover.
_MIN_TOPIC_COVERAGE = 0.5
_RELEVANT_SCORE = 0.55
# Once the head concept matches, this much of the claim's REMAINING substance must
# also appear. Guards against same-subject-different-predicate pairings.
_MIN_PREDICATE_COVERAGE = 0.34

# Categories whose evidence genuinely crosses. Anything not listed here is treated
# as a mismatch that strongly reduces eligibility rather than an outright refusal.
_COMPATIBLE_CATEGORIES: dict[ClaimCategory, frozenset[ClaimCategory]] = {
    ClaimCategory.SUBSIDY: frozenset({ClaimCategory.SUBSIDY,
                                      ClaimCategory.ELIGIBILITY,
                                      ClaimCategory.REGULATION}),
    ClaimCategory.ELIGIBILITY: frozenset({ClaimCategory.ELIGIBILITY,
                                          ClaimCategory.SUBSIDY,
                                          ClaimCategory.REGULATION}),
    ClaimCategory.GRID_RULE: frozenset({ClaimCategory.GRID_RULE,
                                        ClaimCategory.TARIFF,
                                        ClaimCategory.GRID_FEE,
                                        ClaimCategory.REGULATION}),
    # Deliberately NOT including VENDOR_PRICE: one installer's own price is not
    # evidence of a market average, and a market claim earns its figure through
    # corroboration across market-level statements instead.
    ClaimCategory.MARKET_PRICE: frozenset({ClaimCategory.MARKET_PRICE}),
    # A vendor price is established by that vendor's page and nothing else.
    ClaimCategory.VENDOR_PRICE: frozenset({ClaimCategory.VENDOR_PRICE}),
    ClaimCategory.ROI: frozenset({ClaimCategory.ROI, ClaimCategory.ENERGY_PRICE}),
    ClaimCategory.TAX: frozenset({ClaimCategory.TAX, ClaimCategory.REGULATION}),
    ClaimCategory.TARIFF: frozenset({ClaimCategory.TARIFF,
                                     ClaimCategory.GRID_RULE,
                                     ClaimCategory.GRID_FEE}),
    ClaimCategory.GRID_FEE: frozenset({ClaimCategory.GRID_FEE,
                                       ClaimCategory.GRID_RULE,
                                       ClaimCategory.TARIFF}),
}


def _categories_compatible(claim: ClaimCategory | None,
                           passage: ClaimCategory | None) -> bool:
    if claim is None or passage is None:
        return True
    if claim is passage:
        return True
    compatible = _COMPATIBLE_CATEGORIES.get(claim)
    if compatible is None:
        # Unlisted category: allow, so an incomplete table never silently blocks.
        return True
    return passage in compatible


def match(claim: Concepts, passage: Concepts) -> MatchResult:
    """Decide whether a passage bears on a claim, and why."""
    reasons: list[MatchReason] = []

    # ── Stage D: region ──────────────────────────────────────────────────────
    # Checked first: a Walloon passage cannot support a Brussels claim however
    # well the words line up, and refusing early keeps the reason unambiguous.
    if (claim.region is not Region.UNKNOWN and passage.region is not Region.UNKNOWN
            and not passage.region.covers(claim.region)):
        return MatchResult(
            False, None, 0.0, [MatchReason.REGION_MISMATCH],
            f"passage is scoped {passage.region.value}, claim is "
            f"{claim.region.value}")

    # ── Stage E: category ────────────────────────────────────────────────────
    if not _categories_compatible(claim.category, passage.category):
        return MatchResult(
            False, None, 0.0, [MatchReason.CATEGORY_MISMATCH],
            f"claim is {claim.category.value if claim.category else '?'}, passage "
            f"reads as {passage.category.value if passage.category else '?'}")

    # ── Stage B: head concept ────────────────────────────────────────────────
    head_matched = False
    if claim.head_phrase:
        normalized_passage = normalize_query(passage.text)
        head_matched = bool(
            re.search(rf"(?<!\w){re.escape(claim.head_phrase)}(?!\w)",
                      normalized_passage))
        if not head_matched and claim.phrases:
            head_matched = bool(claim.phrases & passage.phrases)

    # ── Stage A: topic alignment ─────────────────────────────────────────────
    shared = claim.topic_terms & passage.topic_terms
    coverage = (len(shared) / len(claim.topic_terms)) if claim.topic_terms else 0.0

    if head_matched:
        # Sharing a head concept is necessary, not sufficient. "La batterie réduit
        # le temps de retour" and "La batterie augmente l'autoconsommation" share
        # their subject and assert different things, so the rest of the claim's
        # substance must also be present.
        head_tokens = frozenset(_tokens(claim.head_phrase or ""))
        remainder = claim.topic_terms - head_tokens
        if remainder:
            remainder_coverage = len(remainder & passage.topic_terms) / len(remainder)
            if remainder_coverage < _MIN_PREDICATE_COVERAGE:
                return MatchResult(
                    False, None, round(0.5 * remainder_coverage, 3),
                    [MatchReason.MATCHED_HEAD_CONCEPT,
                     MatchReason.INSUFFICIENT_TOPIC_ALIGNMENT],
                    f"shares the head concept {claim.head_phrase!r} but only "
                    f"{remainder_coverage:.0%} of the rest of the claim "
                    f"({sorted(remainder)}) — same subject, different predicate")
        reasons.append(MatchReason.MATCHED_HEAD_CONCEPT)
        score = 0.7 + 0.3 * coverage
    else:
        if not shared:
            generic_shared = claim.generic_terms & passage.generic_terms
            reason = (MatchReason.GENERIC_OVERLAP_ONLY if generic_shared
                      else MatchReason.INSUFFICIENT_TOPIC_ALIGNMENT)
            return MatchResult(
                False, None, 0.0,
                [reason] + ([MatchReason.HEAD_CONCEPT_ABSENT]
                            if claim.head_phrase else []),
                f"shared discriminative terms: none; generic: "
                f"{sorted(generic_shared)}")

        # A short claim can be almost entirely generic vocabulary in its own
        # vertical — "Nos tarifs pour une installation de 5 kWc sont de 4 400 €"
        # leaves two discriminative terms. Demanding three would refuse a passage
        # that restates it word for word. Such claims instead need FULL coverage
        # of what little they carry, which is a proportionally stricter bar, and
        # they still face the numeric-type stage below.
        few_terms = len(claim.topic_terms) < _MIN_TOPIC_OVERLAP
        if few_terms and coverage >= 1.0:
            reasons.append(MatchReason.MATCHED_TOPIC_TERMS)
            score = 0.6
        elif len(shared) < _MIN_TOPIC_OVERLAP or coverage < _MIN_TOPIC_COVERAGE:
            return MatchResult(
                False, None, round(0.5 * coverage, 3),
                [MatchReason.INSUFFICIENT_TOPIC_ALIGNMENT]
                + ([MatchReason.HEAD_CONCEPT_ABSENT] if claim.head_phrase else []),
                f"shared {len(shared)}/{len(claim.topic_terms)} discriminative "
                f"terms ({sorted(shared)}), need {_MIN_TOPIC_OVERLAP} and "
                f"{_MIN_TOPIC_COVERAGE:.0%} coverage")
        else:
            reasons.append(MatchReason.MATCHED_TOPIC_TERMS)
            score = 0.4 + 0.5 * coverage

    if score < _RELEVANT_SCORE:
        return MatchResult(False, None, round(score, 3),
                           [MatchReason.INSUFFICIENT_TOPIC_ALIGNMENT],
                           f"alignment score {score:.2f} below {_RELEVANT_SCORE}")

    # ── Stage C: numeric typing ──────────────────────────────────────────────
    # Only reached once the statements are established as being about the same
    # thing. Comparing numbers before that is what produced 163 false conflicts.
    claim_numbers = claim.numerics
    if not claim_numbers:
        return MatchResult(True, None, round(score, 3), reasons,
                           f"aligned, claim carries no quantity")

    comparable = [n for n in passage.numerics
                  if n.type in {c.type for c in claim_numbers}]
    if not comparable:
        # The passage is on-topic but silent about this KIND of quantity. That is
        # not a disagreement — "€5 000" vs "5 ans" says nothing either way.
        return MatchResult(
            False, None, round(score, 3),
            reasons + [MatchReason.NUMERIC_TYPE_MISMATCH],
            f"claim carries {sorted(t.value for t in claim.numeric_types())}, "
            f"passage carries "
            f"{sorted(t.value for t in passage.numeric_types()) or 'none'}")

    claim_digits = {n.digits for n in claim_numbers}
    passage_digits = {n.digits for n in comparable}
    if claim_digits & passage_digits:
        return MatchResult(True, True, round(score, 3),
                           reasons + [MatchReason.NUMERIC_AGREES],
                           "same quantity of the same type")

    return MatchResult(False, False, round(score, 3),
                       reasons + [MatchReason.NUMERIC_DISAGREES],
                       f"same quantity type, different values: "
                       f"{sorted(claim_digits)} vs {sorted(passage_digits)}")
