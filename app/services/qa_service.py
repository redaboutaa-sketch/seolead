"""SEO and factual QA.

Two layers, and only one of them is trusted.

The deterministic layer produces *blocking* issues. It is mechanical, auditable and
cannot be talked out of a finding.

The LLM layer produces *advisory* findings only. A model asked "is this factually
accurate?" will answer confidently either way, and treating that answer as proof
would be the exact failure this pipeline exists to prevent. Its output is recorded
as a separate QAReview row with `qa_type=LLM_ASSISTED` and never blocks on its own.

The numeric check deserves a note. It extracts numbers from the body and asks
whether each appears in the evidence. A page about solar prices that states "6 000 €"
when no retrieved source said so is the single most damaging output this system
could produce, so an unsupported number is blocking rather than advisory. Years,
small counts and figures inside the primary query are excluded — they generate
noise without carrying risk.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from app.core.enums import QAStatus
from app.core.errors import SeoLeadError
from app.providers.llm.base import LLMCapability, LLMProvider, LLMRequest
from app.services.intent import normalize_query
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)

_PLACEHOLDER_PATTERNS = (
    re.compile(r"lorem ipsum", re.I),
    re.compile(r"\bTODO\b"),
    re.compile(r"\bTBD\b"),
    re.compile(r"\[INSERT[^\]]*\]", re.I),
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"\bXX+\b"),
    re.compile(r"\bplaceholder\b", re.I),
)

# Numbers worth checking: anything with a decimal, a thousands separator, a
# percent sign, a currency symbol, or four-plus digits.
_NUMBER_PATTERN = re.compile(
    r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d{4,})\s*(?:%|€|\$|£)?"
)
_STANDALONE_PERCENT = re.compile(r"(?<![\w/])(\d{1,3}(?:[.,]\d+)?)\s*%")

_META_TITLE_MAX = 60
_META_DESCRIPTION_MAX = 155
_KEYWORD_DENSITY_MAX = 0.025          # 2.5% of body words
_MIN_BODY_WORDS = 150


def _finding(code: str, message: str, *, blocking: bool, detail: str = "") -> dict:
    return {"code": code, "message": message, "blocking": blocking,
            "detail": detail[:300]}


def _digits(text: str) -> str:
    """Canonical numeric form: digits only.

    "6 000", "6.000" and "6,000" are the same quantity written three ways across
    fr-BE, nl-BE and en. Comparing digit strings avoids failing a page for a
    locale's thousands separator.
    """
    return re.sub(r"\D", "", text)


def _evidence_numbers(package: dict) -> set[str]:
    corpus = " ".join(
        [str(f.get("fact", "")) for f in package.get("facts") or []]
        + [str(s.get("title") or "") for s in package.get("sources") or []]
    )
    found = {_digits(m.group(1)) for m in _NUMBER_PATTERN.finditer(corpus)}
    found |= {_digits(m.group(1)) for m in _STANDALONE_PERCENT.finditer(corpus)}
    return {n for n in found if n}


def run_deterministic_qa(
    draft: dict, brief: dict, package: dict, profile: VerticalProfile,
    *, existing_titles: Iterable[str] = (),
) -> dict:
    """Return {status, score, findings, blocking_issues}. Pure and testable."""
    findings: list[dict] = []

    title = (draft.get("title") or "").strip()
    body = (draft.get("body") or "").strip()
    meta_title = (draft.get("meta_title") or "").strip()
    meta_description = (draft.get("meta_description") or "").strip()

    # ── Presence ─────────────────────────────────────────────────────────────
    if not title:
        findings.append(_finding("MISSING_TITLE", "Draft has no title", blocking=True))
    if not body:
        findings.append(_finding("MISSING_BODY", "Draft has no body", blocking=True))
    if not meta_title:
        findings.append(_finding("MISSING_META_TITLE", "No meta title", blocking=True))
    elif len(meta_title) > _META_TITLE_MAX:
        findings.append(_finding(
            "META_TITLE_TOO_LONG",
            f"Meta title is {len(meta_title)} chars (max {_META_TITLE_MAX})",
            blocking=False))
    if not meta_description:
        findings.append(_finding("MISSING_META_DESCRIPTION", "No meta description",
                                 blocking=True))
    elif len(meta_description) > _META_DESCRIPTION_MAX:
        findings.append(_finding(
            "META_DESCRIPTION_TOO_LONG",
            f"Meta description is {len(meta_description)} chars "
            f"(max {_META_DESCRIPTION_MAX})", blocking=False))

    if not body:
        return _verdict(findings)

    words = body.split()
    if len(words) < _MIN_BODY_WORDS:
        findings.append(_finding(
            "BODY_TOO_SHORT",
            f"Body has {len(words)} words (minimum {_MIN_BODY_WORDS})", blocking=True))

    # ── Heading structure ────────────────────────────────────────────────────
    h1s = re.findall(r"^#\s+.+$", body, re.M)
    h2s = re.findall(r"^##\s+.+$", body, re.M)
    if len(h1s) == 0:
        findings.append(_finding("NO_H1", "Body has no H1 heading", blocking=True))
    elif len(h1s) > 1:
        findings.append(_finding("MULTIPLE_H1",
                                 f"Body has {len(h1s)} H1 headings, expected 1",
                                 blocking=True))
    if len(h2s) < 2:
        findings.append(_finding("WEAK_STRUCTURE",
                                 f"Body has {len(h2s)} H2 sections, expected at least 2",
                                 blocking=False))

    # ── Placeholder leakage ──────────────────────────────────────────────────
    for pattern in _PLACEHOLDER_PATTERNS:
        match = pattern.search(body)
        if match:
            findings.append(_finding("PLACEHOLDER_LEAKED",
                                     "Body contains unfilled placeholder text",
                                     blocking=True, detail=match.group(0)))
            break

    # ── Forbidden phrases (vertical policy) ──────────────────────────────────
    normalized_body = normalize_query(body)
    for phrase in profile.forbidden_phrases:
        if normalize_query(phrase) in normalized_body:
            findings.append(_finding("FORBIDDEN_PHRASE",
                                     f"Body contains a forbidden phrase: {phrase!r}",
                                     blocking=True))

    # ── Unsupported numeric claims ───────────────────────────────────────────
    known_numbers = _evidence_numbers(package)
    query_numbers = {_digits(m.group(1))
                     for m in _NUMBER_PATTERN.finditer(brief.get("primary_query", ""))}
    unsupported: list[str] = []
    for match in _NUMBER_PATTERN.finditer(body):
        raw = match.group(1)
        canonical = _digits(raw)
        if not canonical or canonical in known_numbers or canonical in query_numbers:
            continue
        # Four-digit values in a plausible year range are almost always years.
        if len(canonical) == 4 and 1900 <= int(canonical) <= 2100:
            continue
        unsupported.append(raw.strip())
    for match in _STANDALONE_PERCENT.finditer(body):
        canonical = _digits(match.group(1))
        if canonical and canonical not in known_numbers:
            unsupported.append(match.group(0).strip())

    if unsupported:
        unique = sorted(set(unsupported))[:10]
        findings.append(_finding(
            "UNSUPPORTED_NUMERIC_CLAIM",
            f"{len(set(unsupported))} numeric value(s) appear in the body but in no "
            f"retrieved source", blocking=True, detail=", ".join(unique)))

    # ── Restricted topics asserted without evidence ──────────────────────────
    for claim in brief.get("cautionary_claims", []):
        if claim.get("has_supported_evidence"):
            continue
        topic = normalize_query(str(claim.get("topic", "")))
        if not topic or topic not in normalized_body:
            continue
        # Mentioning a restricted topic is allowed; attaching a number to it is not.
        window_pattern = re.compile(
            re.escape(topic) + r".{0,120}?\d|\d.{0,120}?" + re.escape(topic),
            re.S,
        )
        if window_pattern.search(normalized_body):
            findings.append(_finding(
                "RESTRICTED_CLAIM_QUANTIFIED",
                f"Restricted topic {claim['topic']!r} appears with a figure but no "
                f"dated source supports it", blocking=True))

    # ── Required facts actually used ─────────────────────────────────────────
    required = brief.get("required_facts") or []
    if required:
        used = sum(1 for f in required
                   if _fact_echoed(str(f.get("fact", "")), normalized_body))
        if used == 0:
            findings.append(_finding(
                "REQUIRED_FACTS_UNUSED",
                f"None of the {len(required)} supported facts appear in the body",
                blocking=True))
        elif used < max(1, len(required) // 3):
            findings.append(_finding(
                "REQUIRED_FACTS_UNDERUSED",
                f"Only {used} of {len(required)} supported facts appear in the body",
                blocking=False))
    else:
        # No supported facts at all: the draft cannot be evidence-based.
        findings.append(_finding(
            "NO_SUPPORTED_EVIDENCE",
            "The research package contained no supported facts, so this draft "
            "cannot be evidence-based", blocking=True))

    # ── Source traceability ──────────────────────────────────────────────────
    if not (brief.get("required_sources") or []):
        findings.append(_finding(
            "NO_TRACEABLE_SOURCES",
            "Brief carries no source URLs, so no claim in the draft is traceable",
            blocking=True))

    # ── Keyword stuffing ─────────────────────────────────────────────────────
    primary = normalize_query(brief.get("primary_query", ""))
    if primary and words:
        occurrences = normalized_body.count(primary)
        density = (occurrences * len(primary.split())) / len(words)
        if density > _KEYWORD_DENSITY_MAX:
            findings.append(_finding(
                "KEYWORD_STUFFING",
                f"Primary query appears {occurrences} times "
                f"({density:.1%} of body words, max {_KEYWORD_DENSITY_MAX:.1%})",
                blocking=True))

    # ── Duplicate title ──────────────────────────────────────────────────────
    normalized_title = normalize_query(title)
    for existing in existing_titles:
        if normalize_query(existing) == normalized_title:
            findings.append(_finding("DUPLICATE_TITLE",
                                     "A draft with this title already exists",
                                     blocking=True))
            break

    # ── CTA present ──────────────────────────────────────────────────────────
    cta = brief.get("cta_strategy") or {}
    if not cta.get("code"):
        findings.append(_finding(
            "NO_CTA",
            "No conversion strategy is defined; a page that only ranks is not "
            "publishable", blocking=True))

    return _verdict(findings)


def _fact_echoed(fact: str, normalized_body: str) -> bool:
    """Whether a fact's substance shows up in the body.

    Exact-substring matching would fail on any rewording, which is most of them.
    Instead: does a majority of the fact's distinctive words appear?
    """
    tokens = [t for t in normalize_query(fact).split() if len(t) > 4]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in normalized_body)
    return hits >= max(2, len(tokens) // 2)


def _verdict(findings: list[dict]) -> dict:
    blocking = [f for f in findings if f["blocking"]]
    advisory = [f for f in findings if not f["blocking"]]
    # Score is a coarse signal for operators, not a gate. The gate is `blocking`.
    score = max(0, 100 - 25 * len(blocking) - 5 * len(advisory))
    return {
        "status": (QAStatus.FAILED if blocking else QAStatus.PASSED).value,
        "score": score,
        "findings": findings,
        "blocking_issues": blocking,
    }


_QA_SYSTEM = (
    "You review a draft web page against its brief. You are an advisor, not a "
    "gate: report concerns, do not approve. Judge only: search-intent alignment, "
    "usefulness to the reader, repetition, keyword stuffing, unsupported claims, "
    "and whether the call to action fits. Reply with JSON only: "
    "{\"findings\": [{\"code\": str, \"message\": str, \"severity\": "
    "\"low\"|\"medium\"|\"high\"}]}"
)


async def run_llm_qa(
    draft: dict, brief: dict, *, llm: LLMProvider, correlation_id: str,
) -> dict:
    """Advisory only. Its findings are never blocking, by construction."""
    if not llm.configured:
        return {"status": QAStatus.SKIPPED.value, "score": None,
                "findings": [], "blocking_issues": []}

    prompt = json.dumps({
        "primary_query": brief["primary_query"],
        "search_intent": brief["search_intent"],
        "content_type": brief["content_type"],
        "target_audience": brief["target_audience"],
        "call_to_action": brief["cta_strategy"],
        "title": draft.get("title"),
        "meta_description": draft.get("meta_description"),
        "body": (draft.get("body") or "")[:12000],
    }, ensure_ascii=False)

    try:
        response = await llm.generate(LLMRequest(
            capability=LLMCapability.SEO_QA, system=_QA_SYSTEM, prompt=prompt,
            response_format="json", temperature=0.1, max_tokens=1500,
            correlation_id=correlation_id,
        ))
        parsed = json.loads(response.content)
        raw_findings = parsed.get("findings") or []
    except (SeoLeadError, json.JSONDecodeError, TypeError, AttributeError) as exc:
        logger.warning("LLM QA skipped: %s", type(exc).__name__,
                       extra={"correlation_id": correlation_id})
        return {"status": QAStatus.SKIPPED.value, "score": None,
                "findings": [], "blocking_issues": []}

    findings = [
        {"code": str(f.get("code", "LLM_FINDING"))[:64],
         "message": str(f.get("message", ""))[:500],
         "severity": str(f.get("severity", "low"))[:16],
         # Always false. An LLM does not get to block, and does not get to pass.
         "blocking": False}
        for f in raw_findings if isinstance(f, dict)
    ][:25]

    return {"status": QAStatus.PASSED.value, "score": None,
            "findings": findings, "blocking_issues": []}


# ─────────────────────────────────────────────────────────────────────────────
# SEO QA V2 (Phase 3)
# ─────────────────────────────────────────────────────────────────────────────
# Layered on top of `run_deterministic_qa` rather than folded into it. The Phase 2
# checks are load-bearing and well covered by tests; changing their behaviour to
# add new ones would have meant editing those tests to match, which is how a
# regression suite quietly stops being one.
#
# V2 adds the checks the mission asks for that need Phase 3 inputs: coverage of
# the questions Google actually surfaces, intent alignment, and content-type fit.
# Its additions are advisory unless they indicate the page answers a different
# question than the one it targets.

def run_seo_qa_v2(
    draft: dict, brief: dict, package: dict, profile: VerticalProfile,
    *, existing_titles: Iterable[str] = (),
) -> dict:
    """Phase 2 checks, plus SERP-aware coverage and fit. Actionable findings."""
    base = run_deterministic_qa(draft, brief, package, profile,
                                existing_titles=existing_titles)
    findings = list(base["findings"])

    body = (draft.get("body") or "").strip()
    title = (draft.get("title") or "").strip()
    if not body:
        return base

    normalized_body = normalize_query(body)
    normalized_title = normalize_query(title)

    # ── Coverage of the questions Google surfaces ────────────────────────────
    # PAA is the clearest available statement of what searchers also want to
    # know. Missing all of it means the page answers a narrower question than the
    # SERP says is being asked.
    questions = [q for q in (package.get("user_questions") or []) if q][:12]
    if questions:
        covered = [q for q in questions if _question_covered(q, normalized_body)]
        ratio = len(covered) / len(questions)
        if ratio == 0:
            findings.append(_finding(
                "PAA_COVERAGE_NONE",
                f"The draft addresses none of the {len(questions)} questions Google "
                f"surfaces for this query. Consider covering: "
                f"{'; '.join(questions[:3])}",
                blocking=False))
        elif ratio < 0.34:
            findings.append(_finding(
                "PAA_COVERAGE_LOW",
                f"The draft addresses {len(covered)} of {len(questions)} questions "
                f"Google surfaces. Uncovered: "
                f"{'; '.join(q for q in questions if q not in covered)[:200]}",
                blocking=False))

    # ── Intent alignment ─────────────────────────────────────────────────────
    intent = str(brief.get("search_intent") or "")
    if intent in ("COMMERCIAL", "TRANSACTIONAL"):
        commercial_hit = any(
            normalize_query(term) in normalized_body
            for term in profile.commercial_terms
        )
        if not commercial_hit:
            findings.append(_finding(
                "INTENT_MISALIGNED",
                f"Brief targets {intent} intent but the body never addresses cost, "
                f"price or quotation. A searcher with buying intent will bounce.",
                blocking=True))

    # ── Title carries the topic ──────────────────────────────────────────────
    primary = normalize_query(brief.get("primary_query", ""))
    if primary and normalized_title:
        topic_tokens = {t for t in primary.split() if len(t) > 3}
        if topic_tokens and not (topic_tokens & set(normalized_title.split())):
            findings.append(_finding(
                "TITLE_OFF_TOPIC",
                "The title shares no distinctive term with the target query.",
                blocking=True))

    # ── Content-type fit ─────────────────────────────────────────────────────
    content_type = str(brief.get("content_type") or "")
    if content_type == "COMPARISON" and body.count("|") < 4 and \
            len(re.findall(r"^\s*[-*]\s+", body, re.M)) < 4:
        findings.append(_finding(
            "COMPARISON_UNSTRUCTURED",
            "A COMPARISON page carries neither a table nor a comparative list.",
            blocking=False))

    # ── Repetition ───────────────────────────────────────────────────────────
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s) > 40]
    if sentences:
        seen: dict[str, int] = {}
        for sentence in sentences:
            key = normalize_query(sentence)[:80]
            seen[key] = seen.get(key, 0) + 1
        repeats = sum(1 for n in seen.values() if n > 1)
        if repeats:
            findings.append(_finding(
                "REPETITION",
                f"{repeats} sentence opening(s) repeat almost verbatim.",
                blocking=False))

    # ── Outbound links ───────────────────────────────────────────────────────
    # The Phase 3.3 live draft emitted a markdown link to a commercial competitor
    # page. Sources belong in the evidence ledger, not as links in the copy: a
    # published page linking a competitor sends the reader away, and the writer
    # was never asked to cite by hyperlink.
    external_links = re.findall(r"\]\((https?://[^)]+)\)", body)
    if external_links:
        findings.append(_finding(
            "EXTERNAL_LINK_IN_BODY",
            f"The draft emits {len(external_links)} outbound link(s). Sources "
            f"belong in the evidence ledger, not in the copy.",
            blocking=True, detail=", ".join(external_links[:3])))

    # ── Did it actually answer a quantified question? ────────────────────────
    # Factual QA passing means "asserted nothing false". For a price query it can
    # also mean "asserted nothing at all" — the live draft was titled "Prix des
    # panneaux solaires" and contained no price. That is not a factual failure,
    # so it is reported here, where usefulness is judged.
    if intent in ("COMMERCIAL", "TRANSACTIONAL"):
        quantified = re.search(
            r"\d[\d\s.,]*\s*(?:%|€|\$|£|eur|euros?|kwh|kwc|kwp|ans?)",
            body, re.IGNORECASE)
        if not quantified:
            findings.append(_finding(
                "NO_QUANTIFIED_ANSWER",
                f"Brief targets {intent} intent but the body states no figure at "
                f"all. The page may be honest and still not answer the query.",
                blocking=False))

    # ── Content gap the SERP revealed ────────────────────────────────────────
    for gap in (package.get("content_gap") or [])[:3]:
        findings.append(_finding("SERP_CONTENT_GAP", f"Opportunity: {gap}",
                                 blocking=False))

    return _verdict(findings)


def _question_covered(question: str, normalized_body: str) -> bool:
    """Whether the body plausibly addresses a PAA question.

    Matching on the question's distinctive words rather than its wording: a page
    can answer "combien coûte une installation" without containing that phrase.
    """
    tokens = [t for t in normalize_query(question).split() if len(t) > 4]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in normalized_body)
    return hits >= max(2, len(tokens) // 2)
