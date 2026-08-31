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
from app.services import claim_policy
from app.services.intent import normalize_query
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)

# See `factual_qa_v2.ENGINE_VERSION`.
ENGINE_VERSION = "seo_qa_v2"

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

# "Ces prix incluent la TVA", "tous ces montants sont TVAC", "these prices
# include VAT" — a plural subject carrying one VAT treatment for the whole list.
_VAT_GENERALISATION = re.compile(
    r"\b(?:ces|les|tous\s+ces|nos)\s+(?:prix|tarifs|montants|budgets)\b[^.!?]{0,80}"
    r"(?:tvac|ttc|incluent\s+la\s+tva|comprennent\s+la\s+tva|tva\s+comprise|"
    r"tva\s+incluse|hors\s+tva|htva)"
    r"|\b(?:these|all)\s+prices\b[^.!?]{0,60}(?:include|exclude)\s+vat",
    re.IGNORECASE)
# ...unless the sentence says the treatment holds only where a source stated it.
# That is the correct qualification, not the overstatement being caught.
_VAT_QUALIFIER = re.compile(
    r"\b(?:lorsqu[e\']|quand|si)\s+(?:cela|c[\']est|elle\s+est|il\s+est)?\s*"
    r"(?:est\s+)?(?:sp[ée]cifi[ée]|pr[ée]cis[ée]|indiqu[ée]|mentionn[ée])"
    r"|\ble\s+cas\s+[ée]ch[ée]ant\b|\bo[uù]\s+(?:cela\s+est\s+)?indiqu[ée]\b"
    r"|\bwhere\s+(?:so\s+)?(?:stated|specified|indicated)\b",
    re.IGNORECASE)

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
    """Numbers a retrieved source actually stated.

    Only SUPPORTED claims count. A V3 package keys its propositions `claim` while
    a V2 package keys its excerpts `fact`, and reading only `fact` meant every
    figure in a V3 package was invisible here — so a correctly sourced price was
    reported as appearing "in no retrieved source". Phase 3.3's draft hid the bug
    by containing no numbers at all.
    """
    # A V2 package carries no support verdict per fact, so its whole fact list is
    # the corpus, exactly as before. Where the V3 builder ran, only claims that
    # reached SUPPORTED count — strictly narrower than the V2 rule.
    entries = package.get("supported_claims")
    if entries is None:
        entries = package.get("facts") or []
    corpus = " ".join(
        [str(f.get("claim") or f.get("fact") or "") for f in entries]
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
        # ── The substance floor ─────────────────────────────────────────
        # This check already existed and had no teeth: its bar was a third of
        # whatever happened to be supplied, and missing it was advisory. That is
        # how a draft scored 100/100 on factual QA while saying almost nothing —
        # every sentence traced to evidence, and there was barely any evidence
        # in it. Traceability was certified; substance was not.
        #
        # The floor is now an absolute the owner ratifies, not a fraction of the
        # supply, and it blocks. `minimum_supported_facts_used: 0` opts a
        # vertical out entirely, which is what an unconfigured one gets.
        floor = int(getattr(profile, "minimum_supported_facts_used", 0) or 0)
        if used == 0:
            findings.append(_finding(
                "REQUIRED_FACTS_UNUSED",
                f"None of the {len(required)} supported facts appear in the body",
                blocking=True))
        elif floor and len(required) < floor:
            # Not the writer's failure: the research never established enough to
            # build on. Blocking all the same — the page would be padding
            # whoever wrote it, and saying so names the real gap.
            findings.append(_finding(
                "INSUFFICIENT_SUPPORTED_EVIDENCE",
                f"Only {len(required)} supported fact(s) were available, below "
                f"the floor of {floor}; the research, not the draft, is what is "
                f"missing", blocking=True))
        elif floor and used < floor:
            findings.append(_finding(
                "REQUIRED_FACTS_UNDERUSED",
                f"The body uses {used} supported fact(s) of {len(required)} "
                f"supplied, below the floor of {floor}. A page that states a "
                f"handful of what was established is padding around them.",
                blocking=True))
        elif not floor and used < max(1, len(required) // 3):
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

# ── Financing promises and offer figures ────────────────────────────────────
# Two failures, two findings, found by the audit of 2026-08-31:
#
# UNCONDITIONAL_FINANCING_PROMISE — « L'installation s'autofinance. » The
# subject is not banned; the promissive, condition-free form of it is. « Selon
# le financement, …, les économies peuvent contribuer à compenser tout ou
# partie de la mensualité » carries its conditions and passes this check (it
# still answers to the claim ledger like any other sentence).
#
# UNREGISTERED_OFFER_FACT — « Les frais de dossier sont de 150 €. » A figure
# presented as OUR offer must exist, validated, in the first-party offer
# registry. The research pipeline can never establish our own offer, so with
# no registry — or a registry not yet publishable — ANY such figure is an
# invention, and the guard blocks on principle rather than on comparison.
_OFFER_SENTENCE = re.compile(
    r"frais\s+de\s+dossier|acompte|\bapport\b"
    r"|(?:notre|nos|chez\s+nous|proposons)\W+(?:\w+\W+){0,6}?mensualite"
    r"|mensualite\W+(?:\w+\W+){0,6}?(?:notre|nos|chez\s+nous|proposons)",
    re.IGNORECASE)
_SENTENCE_SPLIT_QA = re.compile(r"(?<=[.!?])\s+|\n+")
# `_NUMBER_PATTERN` above deliberately ignores figures under four digits (page
# counts, years of warranty). Offer figures live exactly there — 150 € of fees,
# 240 months of term — so the offer check reads its own pattern.
_OFFER_NUMBER = re.compile(r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d{2,})")


def _financing_findings(draft: dict, offer: dict | None) -> list[dict]:
    findings: list[dict] = []
    registered = set((offer or {}).get("registered_numbers") or set())
    version = (offer or {}).get("version") or "absent"

    # The body sentence by sentence — and the three fields a crawler reads
    # FIRST. A meta description saying « gratuit » is the promise at its most
    # visible, and the first version of this check only read the body.
    texts = [s.strip()
             for s in _SENTENCE_SPLIT_QA.split(draft.get("body") or "")]
    texts += [str(draft.get(field) or "")
              for field in ("title", "meta_title", "meta_description")]

    for sentence in texts:
        if not sentence:
            continue

        # The registry is consulted FIRST, because a validated offer fact
        # stated plainly is not a promise: « Les frais de dossier sont de
        # 150 € » with 150 validated in the registry is the page doing its
        # job. The same sentence with no registry behind it is an invention,
        # and gets the finding that names the actual defect.
        numbers = {_digits(m.group(1))
                   for m in _OFFER_NUMBER.finditer(sentence)}
        numbers.discard("")
        if numbers and _OFFER_SENTENCE.search(normalize_query(sentence)):
            strays = numbers - registered
            if strays:
                findings.append(_finding(
                    "UNREGISTERED_OFFER_FACT",
                    f"The draft states a figure as our own offer that the "
                    f"first-party offer registry ({version}) does not carry "
                    f"as a validated fact. Research cannot establish our "
                    f"offer; only the registry can, and it does not.",
                    blocking=True, detail=sentence[:240]))
            continue

        if claim_policy.is_unconditional_financing_promise(sentence):
            findings.append(_finding(
                "UNCONDITIONAL_FINANCING_PROMISE",
                "The draft makes a financing-offer promise with no condition "
                "attached. The subject is allowed; the unconditional form of "
                "it is not — no offer is unconditional, and a page saying so "
                "is wrong before it is checked.",
                blocking=True, detail=sentence[:240]))
    return findings


def run_seo_qa_v2(
    draft: dict, brief: dict, package: dict, profile: VerticalProfile,
    *, existing_titles: Iterable[str] = (), offer: dict | None = None,
) -> dict:
    """Phase 2 checks, plus SERP-aware coverage and fit. Actionable findings.

    `offer` is the first-party offer registry view (`app.site.offer.offer_view`)
    for the vertical's site: which figures a draft may present as OUR offer.
    None is treated exactly like an empty registry — fail-closed — because a
    missing registry must never read as permission.
    """
    base = run_deterministic_qa(draft, brief, package, profile,
                                existing_titles=existing_titles)
    findings = list(base["findings"])

    body = (draft.get("body") or "").strip()
    title = (draft.get("title") or "").strip()
    if not body:
        return base

    findings.extend(_financing_findings(draft, offer))

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
            # Phase 3.4: whether silence is a failure depends entirely on whether
            # the evidence could have spoken. With eligible price evidence in the
            # brief, an unanswered page is a writer failure and must block. With
            # none, silence is the correct outcome and blocking it would only
            # pressure the next run into inventing a figure.
            answerable = bool(brief.get("must_answer_directly"))
            findings.append(_finding(
                "NO_QUANTIFIED_ANSWER",
                (f"The brief supplied "
                 f"{len((brief.get('core_answer_evidence') or {}).get('answers') or [])} "
                 f"evidence-backed figure(s) and required a direct answer to "
                 f"\"{brief.get('core_question')}\", but the body states no figure "
                 f"at all."
                 if answerable else
                 f"Brief targets {intent} intent but the body states no figure at "
                 f"all. The page may be honest and still not answer the query."),
                blocking=answerable))

    # ── VAT generalised across figures that never stated it ──────────────────
    # A blanket "these prices include VAT" restates every figure in the list by
    # up to 21%. The first regenerated Phase 3.4 draft did exactly this: one of
    # six supplied figures was marked TVAC, the other five said nothing.
    answers = (brief.get("core_answer_evidence") or {}).get("answers") or []
    vat_sentence = _VAT_GENERALISATION.search(body)
    if (answers and vat_sentence
            and not _VAT_QUALIFIER.search(
                body[vat_sentence.start():vat_sentence.end() + 60])):
        unknown = [a for a in answers
                   if (a.get("price_context") or {}).get("vat_status") == "UNKNOWN"]
        if unknown:
            findings.append(_finding(
                "VAT_STATUS_GENERALISED",
                f"The body states a VAT treatment for the prices as a group, but "
                f"{len(unknown)} of {len(answers)} supplied figures carry no VAT "
                f"status in their source. VAT belongs to one figure, not a list.",
                blocking=True,
                detail=str(unknown[0].get("claim", ""))[:200]))

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
