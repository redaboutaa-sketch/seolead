"""Factual QA against atomic claims — Phase 3.1.

The earlier version re-derived claims from the draft and tried to bind them to
page excerpts. That was the only option when the package held excerpts, and it
meant QA and the evidence model disagreed about what a claim even was.

Now the package already carries evaluated atomic claims, so QA does two things:

1. **Checks the draft against the claim ledger.** Every factual sentence in the
   draft must correspond to a SUPPORTED claim. A sentence asserting something the
   package refused is the failure mode that matters.
2. **Enforces the blocking policy**, which is narrow on purpose:

       HIGH-risk + not SUPPORTED            → BLOCK
       HIGH-risk + insufficient authority   → BLOCK
       CONFLICTING evidence                 → BLOCK (policy default)
       numeric claim absent from evidence   → BLOCK
       undecidable between the two          → BLOCK, as AMBIGUOUS_MATCH

Everything else is reported for the reviewer to weigh. A wrong sentence about
panel orientation is a quality problem; a wrong sentence about a subsidy is a
legal one, and only the second should stop a draft reaching a human.
"""
from __future__ import annotations

import re

from app.core.enums import EvidenceStatus
from app.services.claim_policy import ClaimRisk
from app.services.intent import normalize_query
from app.services.region import Region, names_region
from app.verticals.profile import VerticalProfile

# A dated rule is a factual sentence too. « avant le 31 décembre 2023 … jusqu'au
# 31 décembre 2030 » carried no unit, so it was invisible to every sentence-level
# check on the published article — including the one that asks whether a
# regional rule names its region. Measured 2026-09-03.
_FACTUAL_SENTENCE = re.compile(
    r"\d[\d\s.,]*\s*(?:%|€|\$|£|eur|euros?|kwh|kwc|kwp|wc|wp|m²|m2|ans?|jaar|years?)"
    r"|(?<!\d)(?:19|20)\d{2}(?!\d)",
    re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NUMBER = re.compile(r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d{2,})")

_TOPIC_MATCH_MIN = 2
# Two readings of one sentence count as equally strong within this margin. Below
# it the difference is not evidence of anything, and the verdict is a tie.
_MATCH_MARGIN = 0.05

# What judged a verdict, recorded on the row it produces. The margin is in the
# string on purpose: it is the knob that decides every arbitration, and a
# re-judgement under a different setting must read as a different engine rather
# than as an unexplained reversal.
ENGINE_VERSION = f"factual_qa_v2/arbitration-{_MATCH_MARGIN}/segments-3"
# Conflicting evidence blocks by default; a vertical may downgrade it to an
# explicit unresolved note instead.
_CONFLICT_POLICY_BLOCK = True


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _numbers(text: str) -> set[str]:
    found = {_digits(m.group(1)) for m in _NUMBER.finditer(text)}
    return {n for n in found if n and not (len(n) == 4 and 1900 <= int(n) <= 2100)}


def _content_words(text: str) -> set[str]:
    return {w for w in normalize_query(text).split() if len(w) > 4}


# ── Segments à risque (2026-09-03) ───────────────────────────────────────────
# L'arbitrage comparait des ressemblances de phrase ENTIÈRE. Mesuré sur l'article
# 8a1f6e46 publié : « rentabilisée au bout de 5 ans, même avec l'entrée en
# vigueur du tarif prosumer, qui vise à faire contribuer équitablement… » a
# remporté son duel grâce à sa longue queue, reprise presque mot pour mot d'un
# passage étayé sur le MÉCANISME du tarif — pendant que sa tête, « 5 ans »,
# n'était couverte par rien. Trois demandes… non : une page publique affirmant
# un retour sur investissement qu'aucune source ne porte.
#
# Un chiffre, une durée, un pourcentage, une règle datée sont des segments à
# risque : c'est EUX que la lecture étayée doit couvrir, pas la phrase autour.
# Une lecture rivale qui ne porte pas les figures de la phrase ne peut pas
# l'absoudre, quelle que soit sa ressemblance ailleurs.
_RISKY_UNIT = (r"ans?\b|mois\b|jours?\b|%|€|eur\b|euros?\b|kwh\b|kwc\b|kwp\b|"
               r"m²|m2\b|personnes?\b|kva\b|kwe\b|kw\b|wc\b|wp\b")
_QUANTITY = r"\d+(?:[  .,]\d{3})*(?:[.,]\d+)?"
_RISKY_SEGMENT = re.compile(
    rf"(?<![\w/])({_QUANTITY})\s*(?:{_RISKY_UNIT})", re.IGNORECASE)
# « entre 7 et 11 ans », « 2 à 3 personnes » : le premier chiffre d'une
# fourchette n'a pas d'unité à lui, il emprunte celle du second.
# « entre 7,3% et 8,4% » : the first end may carry its own unit.
_RISKY_RANGE = re.compile(
    rf"(?<![\w/])({_QUANTITY})\s*(?:{_RISKY_UNIT})?\s*(?:à|a|-|–|et|ou)\s*"
    rf"({_QUANTITY})\s*(?:{_RISKY_UNIT})",
    re.IGNORECASE)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
# The unit a figure carries is part of the figure (2026-09-03, second
# regenerated draft): « rentabilisée au bout de 5 ans » was read as covered by
# a supported passage that stated a 5 of another kind. Digits alone are not a
# statement; « 5 kWc » does not source « 5 ans ».
_UNIT_CLASSES: tuple[tuple[str, re.Pattern], ...] = (
    ("duration", re.compile(r"^(?:ans?|mois|jours?|years?|jaar)$", re.I)),
    ("percent", re.compile(r"^%$")),
    ("money", re.compile(r"^(?:€|eur|euros?)$", re.I)),
    ("energy", re.compile(r"^(?:kwh)$", re.I)),
    ("power", re.compile(r"^(?:kwc|kwp|kva|kwe|kw|wc|wp)$", re.I)),
    ("area", re.compile(r"^(?:m²|m2)$", re.I)),
    ("persons", re.compile(r"^personnes?$", re.I)),
)
BARE = "bare"
YEAR = "year"


def _unit_class(unit: str) -> str:
    unit = unit.strip()
    for name, pattern in _UNIT_CLASSES:
        if pattern.match(unit):
            return name
    return BARE


_ANY_QUANTITY = re.compile(rf"(?<![\w/])({_QUANTITY})")
# « 1.000 kWh X 5 kWe = 5.000 kWh » : un calcul explicite porte ses propres
# chiffres ; ils n'ont pas à être sourcés un par un.
# Units and parentheses sit between the operands in the CWaPE's own layout —
# « (1.000 kWh X 5 kWe) = 5.000 kWh » — so the operands are matched loosely
# and the « = » followed by a figure is what makes it a calculation.
_ARITHMETIC = re.compile(
    rf"{_QUANTITY}[^=\n]{{0,30}}[x×*+/–-][^=\n]{{0,30}}{_QUANTITY}[^=\n]{{0,20}}"
    rf"=\s*\(?{_QUANTITY}", re.IGNORECASE)
# Ce qui fait d'une phrase une affirmation de retour sur investissement, quelle
# que soit la catégorie où le classifieur a rangé l'affirmation qu'elle reprend.
# « sans soutien public », « sans aide ni subside », « malgré l'arrêt des
# primes » — a statement about the present of public support.
_SUPPORT_FREE = re.compile(
    r"\b(?:sans|malgr[ée]\s+(?:l['’]arr[êe]t|la\s+fin|la\s+suppression|"
    r"la\s+disparition)\s+(?:des?|du|de\s+la|de\s+l['’]|de)?)\s*"
    r"(?:tout\s+|toute\s+|aucun[e]?\s+)?"
    r"(?:soutien(?:\s+public)?|aides?(?:\s+publiques?|\s+financi[èe]res?)?|"
    r"subsides?|primes?|subventions?)\b", re.IGNORECASE)
_ROI_SHAPE = re.compile(
    r"rentabilis|amorti|retour sur investissement|temps de retour|payback|"
    r"rentabilit[ée]\s+(?:est|atteint|comprise|de|des|d')|taux de rendement|"
    r"rendement\s+(?:financier|annuel|de l'investissement)", re.IGNORECASE)


# What the writer must actually write. Three regenerated drafts in a row
# (2026-09-03) failed the same sentence on the same rule while the finding
# named the region as « BE-WAL » and the writer answered with « y ».
_REGION_FRENCH = {"BE-WAL": "en Wallonie", "BE-BRU": "à Bruxelles",
                  "BE-VLG": "en Flandre", "BE": "en Belgique"}


def risky_segments(text: str) -> set[str]:
    """The figures of a sentence that a source must carry: quantities with a
    unit, both ends of a range, and years (a dated rule is a figure too)."""
    segments: set[str] = set()
    for m in _RISKY_SEGMENT.finditer(text):
        segments.add(_digits(m.group(1)))
    for m in _RISKY_RANGE.finditer(text):
        segments.add(_digits(m.group(1)))
        segments.add(_digits(m.group(2)))
    for m in _YEAR.finditer(text):
        segments.add(m.group(1))
    return {seg for seg in segments if seg}


def _quantities(text: str) -> set[str]:
    """Every figure a claim states, in the digit form `risky_segments` uses."""
    found = {_digits(m.group(1)) for m in _ANY_QUANTITY.finditer(text)}
    found |= set(_YEAR.findall(text))
    return {f for f in found if f}


def _range_spans(text: str) -> list[tuple[int, int, str, str, str]]:
    """(start, end, low, high, unit class) for every range a text states."""
    out = []
    for m in _RISKY_RANGE.finditer(text):
        unit = m.group(0)[m.end(2) - m.start():]
        out.append((m.start(), m.end(), _digits(m.group(1)),
                    _digits(m.group(2)), _unit_class(unit)))
    return out


def risky_ranges(text: str) -> set[tuple[str, str, str]]:
    """The ranges a text states, as (low, high, unit class)."""
    return {(lo, hi, cls) for _, _, lo, hi, cls in _range_spans(text)
            if lo and hi}


def risky_units(text: str) -> dict[str, set[str]]:
    """Each risky segment of a sentence → the unit class(es) it carries."""
    units: dict[str, set[str]] = {}
    for m in _RISKY_SEGMENT.finditer(text):
        unit = m.group(0)[m.end(1) - m.start():]
        units.setdefault(_digits(m.group(1)), set()).add(_unit_class(unit))
    for _, _, lo, hi, cls in _range_spans(text):
        units.setdefault(lo, set()).add(cls)
        units.setdefault(hi, set()).add(cls)
    for year in _YEAR.findall(text):
        units.setdefault(year, set()).add(YEAR)
    return {k: v for k, v in units.items() if k}


def claim_figures(text: str) -> tuple[dict[str, set[str]],
                                      set[tuple[str, str, str]]]:
    """What a claim states: its standalone figures (with their unit classes)
    and its ranges.

    A figure that appears only as one end of a range is NOT a standalone
    figure. Measured 2026-09-03 on the second draft of the payback article:
    the writer read « rentabilisation en 5 à 7 ans » and wrote « rentabilisée
    au bout de 5 ans » — the low end of a range, presented as the value.
    The « 5 » existed in the ledger; the statement did not.
    """
    spans = _range_spans(text)
    ranges = {(lo, hi, cls) for _, _, lo, hi, cls in spans if lo and hi}
    standalone: dict[str, set[str]] = {}
    unit_bearing = {m.start(): m for m in _RISKY_SEGMENT.finditer(text)}
    for m in _ANY_QUANTITY.finditer(text):
        if any(start <= m.start() < end for start, end, *_ in spans):
            continue
        digits = _digits(m.group(1))
        if not digits:
            continue
        seg = unit_bearing.get(m.start())
        cls = (_unit_class(seg.group(0)[seg.end(1) - seg.start():])
               if seg is not None else BARE)
        standalone.setdefault(digits, set()).add(cls)
    for year in _YEAR.findall(text):
        standalone.setdefault(year, set()).add(YEAR)
    return standalone, ranges


def covers(claim: dict, segments: set[str],
           ranges: set[tuple[str, str, str]] | frozenset = frozenset(),
           units: dict[str, set[str]] | None = None) -> bool:
    """Whether a claim carries every risky segment of a sentence.

    A segment is carried by a standalone figure of the claim of the same
    unit class, or by a range of the claim that the sentence states in full
    (`ranges` are the sentence's own). One end of a range is not the range;
    a figure of another unit is another figure. With `units` absent the
    class is not checked — the lenient form the explain report uses to show
    what was excluded and why.
    """
    standalone, claim_ranges = claim_figures(str(claim.get("claim", "")))
    for segment in segments:
        wanted = (units or {}).get(segment)
        if segment in standalone and (wanted is None
                                      or standalone[segment] & wanted):
            continue
        if any(segment in (lo, hi) and (lo, hi, cls) in ranges
               and (wanted is None or cls in wanted)
               for lo, hi, cls in claim_ranges):
            continue
        return False
    return True


def endpoint_only(claim: dict, segment: str) -> bool:
    """Whether a claim carries this figure only as one end of a range."""
    standalone, claim_ranges = claim_figures(str(claim.get("claim", "")))
    return segment not in standalone and any(segment in (lo, hi)
                                             for lo, hi, _ in claim_ranges)


def unit_only(claim: dict, segment: str, units: dict[str, set[str]]) -> bool:
    """Whether a claim carries this figure only under another unit."""
    standalone, _ = claim_figures(str(claim.get("claim", "")))
    wanted = units.get(segment) or set()
    return segment in standalone and not (standalone[segment] & wanted)


def quantity_labels(text: str) -> dict[str, str]:
    """Each figure of a text in digit form → as the text writes it (« 7,3% »
    rather than « 73 »), for rendering a source with the figures it carries."""
    labels: dict[str, str] = {}
    for m in _RISKY_SEGMENT.finditer(text):
        labels.setdefault(_digits(m.group(1)), m.group(0).strip())
    for m in _RISKY_RANGE.finditer(text):
        unit = m.group(0)[m.end(2) - m.start():].strip()
        labels.setdefault(_digits(m.group(1)), f"{m.group(1)} {unit}".strip())
        labels.setdefault(_digits(m.group(2)), f"{m.group(2)} {unit}".strip())
    for m in _YEAR.finditer(text):
        labels.setdefault(m.group(1), m.group(1))
    for m in _ANY_QUANTITY.finditer(text):
        labels.setdefault(_digits(m.group(1)), m.group(1))
    return {k: v for k, v in labels.items() if k}


def sentence_is_sourced(sentence: str, supported: list[dict]) -> bool:
    """Whether the ledger carries a sentence: every risky figure covered by
    one SUPPORTED claim (same unit, full range), or — for a figure-less
    sentence — a SUPPORTED claim it lexically matches. The deterministic
    answer to « is this sourced? », for anyone who would answer otherwise."""
    segments = risky_segments(sentence)
    if segments:
        ranges, units = risky_ranges(sentence), risky_units(sentence)
        return any(covers(c, segments, ranges, units) for c in supported)
    return any(_matches_claim(sentence, c) for c in supported)


def body_segments(body: str) -> set[str]:
    """Every risky segment a body states, over all its sentences."""
    segments: set[str] = set()
    for sentence in _all_sentences(body):
        segments |= risky_segments(sentence)
    return segments


def body_ranges(body: str) -> set[tuple[str, str, str]]:
    ranges: set[tuple[str, str, str]] = set()
    for sentence in _all_sentences(body):
        ranges |= risky_ranges(sentence)
    return ranges


def body_units(body: str) -> dict[str, set[str]]:
    units: dict[str, set[str]] = {}
    for sentence in _all_sentences(body):
        for digits, classes in risky_units(sentence).items():
            units.setdefault(digits, set()).update(classes)
    return units


def _clean_markdown(body: str) -> str:
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s+", "", body, flags=re.M)
    cleaned = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", cleaned, flags=re.M)
    return cleaned


def _region_of(claim: dict) -> Region:
    try:
        return Region(str(claim.get("region") or "").upper())
    except ValueError:
        return Region.UNKNOWN


def _finding(code: str, message: str, *, blocking: bool, detail: str = "") -> dict:
    return {"code": code, "message": message, "blocking": blocking,
            "detail": detail[:300]}


def _all_sentences(body: str) -> list[str]:
    cleaned = _clean_markdown(body)
    return [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]


def extract_draft_claims(body: str) -> list[str]:
    return [s for s in _all_sentences(body) if _FACTUAL_SENTENCE.search(s)][:60]


def _matches_claim(sentence: str, claim: dict) -> bool:
    """Whether a draft sentence corresponds to a ledger claim."""
    claim_text = str(claim.get("claim", ""))
    shared = len(_content_words(sentence) & _content_words(claim_text))
    sentence_numbers = _numbers(sentence)

    # Phase 3.4: "Le panneau seul coûte entre 130 € et 170 €/m²" failed against
    # "Le panneau seul revient à 130 € – 170 €/m²" — same figures, same subject,
    # one shared long word, so the draft was blocked for asserting exactly what
    # the evidence said. Reproducing every figure of a claim, on a shared topic
    # term, is stronger correspondence than two shared words and no numbers, so
    # it carries the match on its own.
    if (sentence_numbers and shared >= 1
            and sentence_numbers <= _numbers(claim_text)):
        return True

    if shared < _TOPIC_MATCH_MIN:
        return False
    if not sentence_numbers:
        return True
    # A quantified sentence must carry a figure the claim actually contains.
    return bool(sentence_numbers & _numbers(claim_text))


# ── Which claim is a sentence actually stating? ──────────────────────────────
# `_matches_claim` answers "could this sentence be that claim", and a sentence
# can answer yes for several claims at once. The blocking checks below read that
# as "the draft asserts this claim", which is a different sentence entirely.
#
# Measured on draft 8a1f6e46: factual score 100 — every factual sentence matched
# a SUPPORTED claim — while five of those same sentences were blocked for
# asserting UNSUPPORTED ones. Both readings were true of the same text, and the
# draft was rejected for the ledger claim it happened to also resemble.
#
# So when a sentence matches both a blockable claim and a supported one, the two
# readings are compared and only the stronger is acted on. The comparison is
# deliberately shallow — shared vocabulary and reproduced figures — because a
# deeper one would be a second matcher with its own failure modes.
#
# Ties are BLOCKED, not waved through: the arbitration exists to stop mistaken
# blame, never to launder an unsupported assertion past the gate. Preferring the
# supported reading on principle is exactly the failure this must not become. An
# undecidable case therefore blocks under its own code, so an operator reads it
# as a matcher case rather than a drafting fault.
_ASSERTED = "ASSERTED"      # the blockable claim is the better reading
_RIVAL = "RIVAL"            # a supported claim is the better reading
_AMBIGUOUS = "AMBIGUOUS"    # neither wins; block and say so
# The sentence states neither reading: the contested claim only faintly, and
# no supported claim carries its figures. There is nothing to be ambiguous
# between — what there is, is a figure without a source, and check 3 says so
# in those words. Measured 2026-09-03: one sentence, « rentabilisée au bout de
# 5 ans », drew ten AMBIGUOUS_MATCH findings, one per contested claim it
# faintly resembled, and every one of them forbade the rewrite that would
# have fixed it.
_UNREAD = "UNREAD"


def _match_strength(sentence: str, claim: dict) -> float:
    """How strongly a sentence corresponds to a claim; 0.0 when it does not.

    Only ever read as a comparison between two readings of the SAME sentence, so
    the absolute value means nothing on its own.
    """
    if not _matches_claim(sentence, claim):
        return 0.0
    claim_text = str(claim.get("claim", ""))
    sentence_words, claim_words = _content_words(sentence), _content_words(claim_text)
    union = sentence_words | claim_words
    topic = len(sentence_words & claim_words) / len(union) if union else 0.0
    sentence_numbers = _numbers(sentence)
    if sentence_numbers:
        figures = (len(sentence_numbers & _numbers(claim_text))
                   / len(sentence_numbers))
    else:
        # No figure to arbitrate on. The same constant for every rival reading of
        # this sentence, so it cancels out of the comparison it feeds.
        figures = 0.5
    return 0.6 * topic + 0.4 * figures


def _best_rival(sentence: str, claim: dict,
                supported: list[dict]) -> tuple[float, dict | None, set[str]]:
    """The strongest supported reading that carries the sentence's own figures.

    A candidate that resembles the sentence but does not state its risky
    segments is not a reading of it — it is a reading of the words around
    them. It is skipped here, whatever its strength, and `explain_arbitration`
    shows it as the nearest non-covering reading so the exclusion is visible.
    """
    segments = risky_segments(sentence)
    ranges = risky_ranges(sentence)
    units = risky_units(sentence)
    best, rival = 0.0, None
    for candidate in supported:
        if candidate is claim:
            continue
        strength = _match_strength(sentence, candidate)
        if strength <= 0.0:
            continue
        if segments and not covers(candidate, segments, ranges, units):
            continue
        if strength > best:
            best, rival = strength, candidate
    return best, rival, segments


def _arbitrate(sentence: str, claim: dict,
               supported: list[dict]) -> tuple[str, dict | None]:
    """Compare this sentence read as `claim` against its best supported reading."""
    this = _match_strength(sentence, claim)
    best, rival, _ = _best_rival(sentence, claim, supported)
    if this - best > _MATCH_MARGIN:
        return _ASSERTED, rival
    if best - this > _MATCH_MARGIN:
        return _RIVAL, rival
    if rival is None:
        return _UNREAD, None
    # The symmetric rule (2026-09-03, sixth regenerated draft): a supported
    # reading carries the sentence's figures and the contested one does not.
    # « Retour sur investissement en 2026 » is not what « rentabilisée au
    # bout de 5 ans » asserts, however much the two resemble each other; the
    # tie is not between two readings of the figure. Fourteen findings on one
    # sentence, and a forbidden rewrite, came out of calling it one.
    segments = risky_segments(sentence)
    if segments and not covers(claim, segments, risky_ranges(sentence),
                               risky_units(sentence)):
        return _RIVAL, rival
    return _AMBIGUOUS, rival


def _reading(sentences: list[str], claim: dict,
             supported: list[dict]) -> tuple[str, str, dict | None]:
    """The strongest verdict the whole draft carries about one claim.

    One asserting sentence is enough to block, so `_ASSERTED` wins over a tie
    found earlier in the body.
    """
    ambiguous: tuple[str, str, dict | None] | None = None
    for sentence in sentences:
        if not _matches_claim(sentence, claim):
            continue
        verdict, rival = _arbitrate(sentence, claim, supported)
        if verdict == _ASSERTED:
            return _ASSERTED, sentence, rival
        if verdict == _AMBIGUOUS and ambiguous is None:
            ambiguous = (_AMBIGUOUS, sentence, rival)
    return ambiguous or (_RIVAL, "", None)


def _ambiguous_finding(sentence: str, claim: dict, rival: dict | None,
                       withheld_code: str) -> dict:
    return _finding(
        "AMBIGUOUS_MATCH",
        f"A sentence matches the {claim.get('category')} claim {withheld_code} "
        f"would block and a SUPPORTED claim equally well. The matcher cannot say "
        f"which one the draft states, so it blocks — but this is an ambiguity of "
        f"matching, not a drafting fault. Read the two candidates below before "
        f"asking for a rewrite.",
        blocking=True,
        detail=(f"sentence: {sentence[:110]} :: contested: "
                f"{str(claim.get('claim'))[:80]} :: supported: "
                f"{str((rival or {}).get('claim') or '(none)')[:80]}"))


# The three checks that consult the arbitration, and the code each of them
# would raise if the contested reading won. Kept beside `explain_arbitration`
# so a check added later is a visible omission rather than a silent one.
_ARBITRATED_CHECKS = ("HIGH_RISK_CLAIM_ASSERTED", "REGIONAL_SCOPE_NOT_STATED",
                      "CONFLICTING_EVIDENCE_ASSERTED")


def explain_arbitration(draft: dict, package: dict,
                        profile: VerticalProfile) -> list[dict]:
    """Every place the arbitration was consulted, and what it decided.

    Read-only, and answers a question the verdict cannot: `run_factual_qa_v2`
    reports five findings or none, and either number is compatible with an
    arbitration that is doing real work and with one that has quietly stopped
    blocking anything. This shows the two strengths and the gap between them,
    so the margin can be judged instead of trusted.

    One row per (check, claim) the OLD unarbitrated logic would have raised —
    that is, every claim some factual sentence matches. What changed is which
    of those become findings.
    """
    body = (draft.get("body") or "").strip()
    claims = package.get("claims") or []
    supported = [c for c in claims
                 if c.get("evidence_status") == EvidenceStatus.SUPPORTED.value]
    sentences = extract_draft_claims(body) if body else []

    rows: list[dict] = []

    def row(check: str, claim: dict, sentence: str) -> None:
        contested = _match_strength(sentence, claim)
        best, rival, segments = _best_rival(sentence, claim, supported)
        # The nearest reading of any kind, covering or not: when it differs
        # from `rival`, the report shows exactly which figure excluded it.
        nearest_strength, nearest = 0.0, None
        for candidate in supported:
            if candidate is claim:
                continue
            strength = _match_strength(sentence, candidate)
            if strength > nearest_strength:
                nearest_strength, nearest = strength, candidate
        verdict, _ = _arbitrate(sentence, claim, supported)
        ranges = risky_ranges(sentence)
        units = risky_units(sentence)
        rows.append({
            "risky_segments": sorted(segments),
            "risky_units": {k: sorted(v) for k, v in units.items()},
            "rival_covers_segments": bool(rival) and covers(rival, segments,
                                                            ranges, units),
            "nearest_supported_claim": (str(nearest.get("claim"))[:200]
                                        if nearest is not None else None),
            "nearest_excluded_for": (
                sorted(s for s in segments
                       if not covers(nearest, {s}, ranges, units))
                if nearest is not None and nearest is not rival else []),
            "check": check,
            "verdict": verdict,
            "would_have_blocked_before": True,
            "blocks_now": verdict in (_ASSERTED, _AMBIGUOUS),
            "sentence": sentence[:200],
            "contested_claim": str(claim.get("claim"))[:200],
            "contested_status": claim.get("evidence_status"),
            "contested_category": claim.get("category"),
            "contested_strength": round(contested, 4),
            "supported_claim": str((rival or {}).get("claim") or "")[:200] or None,
            "supported_strength": round(best, 4),
            "gap": round(abs(contested - best), 4),
            "margin": _MATCH_MARGIN,
            # Twice the margin. Not a rule the code enforces — a band where the
            # comparison decided something on very little, and a human should
            # look before trusting it.
            "narrow": abs(contested - best) < 2 * _MATCH_MARGIN,
        })

    for claim in claims:
        status = claim.get("evidence_status")
        risk = claim.get("claim_risk")

        if risk == ClaimRisk.HIGH and status != EvidenceStatus.SUPPORTED.value:
            for sentence in sentences:
                if _matches_claim(sentence, claim):
                    row("HIGH_RISK_CLAIM_ASSERTED", claim, sentence)
                    break

        claim_region = _region_of(claim)
        if (claim.get("regionally_determined") and claim_region.is_subnational
                and body):
            for sentence in sentences:
                if not _matches_claim(sentence, claim):
                    continue
                if not names_region(sentence, claim_region):
                    row("REGIONAL_SCOPE_NOT_STATED", claim, sentence)
                break

        if status == EvidenceStatus.CONFLICTING.value:
            for sentence in sentences:
                if _matches_claim(sentence, claim):
                    row("CONFLICTING_EVIDENCE_ASSERTED", claim, sentence)
                    break

    return rows


def run_factual_qa_v2(draft: dict, package: dict,
                      profile: VerticalProfile) -> dict:
    """Evaluate a draft against the package's atomic claim ledger."""
    body = (draft.get("body") or "").strip()
    claims = package.get("claims") or []
    supported = [c for c in claims
                 if c.get("evidence_status") == EvidenceStatus.SUPPORTED.value]

    findings: list[dict] = []
    blocking: list[dict] = []

    def add(finding: dict) -> None:
        findings.append(finding)
        if finding["blocking"]:
            blocking.append(finding)

    draft_sentences = extract_draft_claims(body) if body else []

    # ── 1. Ledger-level policy, independent of what the draft says ───────────
    for claim in claims:
        status = claim.get("evidence_status")
        risk = claim.get("claim_risk")

        if risk == ClaimRisk.HIGH and status != EvidenceStatus.SUPPORTED.value:
            # Only blocks if the draft actually asserts it — an unresolved claim
            # sitting unused in the ledger is a research gap, not a draft defect.
            verdict, sentence, rival = _reading(draft_sentences, claim, supported)
            if verdict == _ASSERTED:
                add(_finding(
                    "HIGH_RISK_CLAIM_ASSERTED",
                    f"The draft asserts a HIGH-risk {claim.get('category')} claim "
                    f"that the evidence set could not establish "
                    f"({status}): {claim.get('reason', '')[:160]}",
                    blocking=True, detail=str(claim.get("claim"))[:280]))
            elif verdict == _AMBIGUOUS:
                add(_ambiguous_finding(sentence, claim, rival,
                                       "HIGH_RISK_CLAIM_ASSERTED"))

        # ── A regional figure stated as the country's ────────────────────
        # This check exists because of a change made beside it: a claim naming
        # no region, in a category this market sets regionally, is now scoped to
        # the region its evidence covers instead of dying on the country-wide
        # bar. That makes seventeen payback claims provable — and it makes a new
        # failure possible, where the writer states a Walloon figure flat and the
        # page tells a Flemish reader something false about their own region.
        #
        # So the region must survive into the sentence. Naming it is what makes
        # the claim true; dropping it is false by omission, and no amount of
        # sourcing repairs that.
        claim_region = _region_of(claim)
        if (claim.get("regionally_determined") and claim_region.is_subnational
                and body):
            for sentence in draft_sentences:
                if not _matches_claim(sentence, claim):
                    continue
                if names_region(sentence, claim_region):
                    break
                verdict, rival = _arbitrate(sentence, claim, supported)
                if verdict in (_RIVAL, _UNREAD):
                    # The sentence is really stating another supported claim —
                    # or none at all; the scope of this one is not what it
                    # failed to name.
                    break
                if verdict == _AMBIGUOUS:
                    add(_ambiguous_finding(sentence, claim, rival,
                                           "REGIONAL_SCOPE_NOT_STATED"))
                    break
                add(_finding(
                    "REGIONAL_SCOPE_NOT_STATED",
                    f"The draft states a {claim.get('category')} figure that "
                    f"holds for {claim_region.value} without naming the "
                    f"region. Written flat it reads as country-wide, and no "
                    f"source establishes it for the country. Name the region "
                    f"IN THIS SENTENCE — « {_REGION_FRENCH.get(claim_region.value, claim_region.value)} » — "
                    f"not by a pronoun and not in a previous sentence.",
                    blocking=True, detail=sentence[:280]))
                break

        if status == EvidenceStatus.CONFLICTING.value:
            verdict, sentence, rival = _reading(draft_sentences, claim, supported)
            if verdict == _ASSERTED:
                add(_finding(
                    "CONFLICTING_EVIDENCE_ASSERTED",
                    f"The draft asserts a claim whose evidence conflicts: "
                    f"{claim.get('reason', '')[:160]}",
                    blocking=_CONFLICT_POLICY_BLOCK,
                    detail=str(claim.get("claim"))[:280]))
            elif verdict == _AMBIGUOUS and _CONFLICT_POLICY_BLOCK:
                add(_ambiguous_finding(sentence, claim, rival,
                                       "CONFLICTING_EVIDENCE_ASSERTED"))

    if not body:
        return _verdict(findings, blocking, claims, 0)

    # ── 2. Every factual sentence must trace to a SUPPORTED claim ────────────
    draft_claims = draft_sentences
    unmatched: list[str] = []
    for sentence in draft_claims:
        if any(_matches_claim(sentence, claim) for claim in supported):
            continue
        unmatched.append(sentence)

    if unmatched:
        add(_finding(
            "UNSUPPORTED_DRAFT_CLAIM",
            f"{len(unmatched)} factual sentence(s) in the draft do not correspond "
            f"to any SUPPORTED claim in the evidence ledger.",
            blocking=True,
            detail=" | ".join(s[:90] for s in unmatched[:3])))

    # ── 3. Un chiffre sans source, quelle que soit la phrase ──────────────
    # Mesuré le 2026-09-03 : « rentabilisée au bout de 5 ans » est passée
    # parce que le « 5 » — un seul chiffre — n'était pas un nombre pour
    # `_numbers`, et parce que la phrase ressemblait à autre chose. Chaque
    # segment à risque du rendu doit se retrouver dans une affirmation
    # étayée, ou dans un calcul explicite. Rien d'autre ne le couvre.
    extracted_any = False
    for sentence in _all_sentences(body):
        segments = risky_segments(sentence)
        ranges = risky_ranges(sentence)
        units = risky_units(sentence)
        extracted_any = extracted_any or bool(segments) or bool(_numbers(sentence))
        if not segments or _ARITHMETIC.search(sentence):
            continue
        missing = sorted(s for s in segments
                         if not any(covers(c, {s}, ranges, units)
                                    for c in supported))
        if missing:
            # A figure the ledger carries only as one end of a range is the
            # case worth naming: the writer did not invent it, it collapsed a
            # range to its edge, and the fix is to state the range.
            collapsed = sorted(s for s in missing
                               if any(endpoint_only(c, s) for c in supported))
            other_unit = sorted(s for s in missing if s not in collapsed
                                and any(unit_only(c, s, units) for c in supported))
            hint = (f" Figure(s) {', '.join(collapsed)} exist in the evidence "
                    f"only as one end of a range: state the range, not its "
                    f"edge." if collapsed else "")
            hint += (f" Figure(s) {', '.join(other_unit)} exist in the "
                     f"evidence only with another unit: a 5 of one kind does "
                     f"not source a 5 of another." if other_unit else "")
            add(_finding(
                "NUMBER_WITHOUT_SOURCE",
                f"The draft states figure(s) {', '.join(missing)} that no "
                f"SUPPORTED claim carries and no explicit calculation "
                f"produces. A number the evidence does not state is a "
                f"number the page invents.{hint}",
                blocking=True, detail=sentence[:280]))
    # The canary: a body that contains digits from which the extractor read
    # no figure at all is an extractor that stopped working, not a body
    # without figures. It must fail loudly rather than certify by absence.
    if re.search(r"\d", _clean_markdown(body)) and not extracted_any:
        add(_finding(
            "NUMERIC_EXTRACTION_FAILED",
            "The body contains digits but the numeric extractor found no "
            "figure to check. The coverage check cannot vouch for anything.",
            blocking=True))

    # ── 4. Every return-on-investment statement needs DATED support ───────
    # The classifier ranged « rentabilisation en 5 à 7 ans » under GENERAL,
    # where freshness is not required; the sentence quoting it was a payback
    # promise all the same. What a sentence asserts is read from the
    # sentence, not from the category of the claim it happens to resemble.
    for sentence in draft_sentences:
        if not _ROI_SHAPE.search(sentence):
            continue
        segments = risky_segments(sentence)
        ranges = risky_ranges(sentence)
        units = risky_units(sentence)
        # The claims that could carry this statement: those stating its
        # figures — or, for a figure-less one, those it lexically matches.
        candidates = ([c for c in supported
                       if covers(c, segments, ranges, units)]
                      if segments
                      else [c for c in supported if _matches_claim(sentence, c)])
        if not candidates:
            continue   # nothing supports it at all: the checks above say so
        if not any(c.get("has_dated_support", False) for c in candidates):
            add(_finding(
                "ROI_WITHOUT_DATED_SOURCE",
                f"A return-on-investment statement rests only on claims whose "
                f"support carries no date and no current-tense marker "
                f"({', '.join(sorted({str(c.get('category')) for c in candidates}))}). "
                f"Payback depends on prices and support schemes that move; an "
                f"undated figure cannot describe the present.",
                blocking=True, detail=sentence[:280]))

    # ── 5. « Rentable sans soutien public » : official, textually, or gone ──
    # Owner's rule B.4 (2026-09-03). The sentence carries no figure, so no
    # numeric check sees it, and the model-assisted reviewer stopped
    # flagging it once it saw the sourced facts. It is a SUBSIDY statement
    # about the present that only a public authority may make: it must
    # match a SUPPORTED claim whose best source is OFFICIAL and whose own
    # text says the same thing about support.
    for sentence in _all_sentences(body):
        if not _SUPPORT_FREE.search(sentence):
            continue
        carriers = [
            c for c in supported
            if _matches_claim(sentence, c)
            and _SUPPORT_FREE.search(str(c.get("claim", "")))
            and str(c.get("best_source_quality") or "").upper() == "OFFICIAL"]
        if not carriers:
            add(_finding(
                "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE",
                "The draft states that an installation pays off without public "
                "support (or despite the end of a scheme). No SUPPORTED claim "
                "from an OFFICIAL source says so in those terms; delete the "
                "statement rather than soften it.",
                blocking=True, detail=sentence[:280]))

    if not supported and draft_claims:
        add(_finding(
            "NO_SUPPORTED_CLAIMS",
            f"The draft makes {len(draft_claims)} factual claim(s) but the package "
            f"carries no SUPPORTED claim at all.",
            blocking=True))

    matched = len(draft_claims) - len(unmatched)
    score = int(round(100 * matched / len(draft_claims))) if draft_claims else 100
    return _verdict(findings, blocking, claims, score)


def _verdict(findings: list[dict], blocking: list[dict], claims: list[dict],
             score: int) -> dict:
    counts: dict[str, int] = {}
    for claim in claims:
        status = str(claim.get("evidence_status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1

    return {
        "status": "FAILED" if blocking else "PASSED",
        "score": score,
        "findings": findings,
        "blocking_issues": blocking,
        "claim_ledger": {
            "total": len(claims),
            "by_status": counts,
            "supported": counts.get(EvidenceStatus.SUPPORTED.value, 0),
            "partially_supported": counts.get(
                EvidenceStatus.PARTIALLY_SUPPORTED.value, 0),
            "unsupported": counts.get(EvidenceStatus.UNSUPPORTED.value, 0),
            "conflicting": counts.get(EvidenceStatus.CONFLICTING.value, 0),
        },
    }
