"""Factual QA V2 — claim → evidence association.

V1 asked one question: does every number in the draft appear somewhere in the
evidence? That catches outright fabrication and nothing else.

V2 walks the draft's factual sentences and tries to bind each to a specific piece
of eligible evidence, producing a status per claim:

    SUPPORTED            bound to evidence that clears its risk bar
    PARTIALLY_SUPPORTED  bound, but the evidence is weaker than the risk demands
    UNSUPPORTED          nothing in the evidence set backs it
    CONFLICTING          evidence exists on the topic and disagrees on the number

The blocking rule is narrow on purpose: **HIGH-risk and not SUPPORTED blocks.**
A wrong sentence about panel orientation is a quality problem; a wrong sentence
about a subsidy is a legal one, and only the second should stop a draft reaching a
human. Everything else is reported for the reviewer to weigh.
"""
from __future__ import annotations

import re

from app.services.claim_risk import ClaimRisk, SupportStatus, classify_claim
from app.services.intent import normalize_query
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile

# A sentence carrying a number with a unit, currency or percent is a factual claim
# worth binding. Prose without figures is judged by the SEO layer, not this one.
_FACTUAL_SENTENCE = re.compile(
    r"\d[\d\s.,]*\s*(?:%|€|\$|£|eur|euros?|kwh|kwc|kwp|wc|wp|m²|m2|ans?|jaar|years?)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d{2,})")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Overlap of distinctive words needed before a claim and a piece of evidence are
# treated as being about the same thing.
_TOPIC_MATCH_MIN = 2


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _numbers(text: str) -> set[str]:
    found = {_digits(m.group(1)) for m in _NUMBER.finditer(text)}
    return {n for n in found if n and not (len(n) == 4 and 1900 <= int(n) <= 2100)}


def _content_words(text: str) -> set[str]:
    return {w for w in normalize_query(text).split() if len(w) > 4}


def extract_claims(body: str) -> list[str]:
    """Sentences that assert something checkable."""
    # Strip markdown headings and list markers so a heading is not read as a claim.
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s+", "", body, flags=re.M)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.M)
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    return [s for s in sentences if _FACTUAL_SENTENCE.search(s)][:60]


def assess_claim(
    claim: str, evidence: list[dict], profile: VerticalProfile,
) -> dict:
    """Bind one claim to the eligible evidence set."""
    risk = classify_claim(claim, profile)
    claim_numbers = _numbers(claim)
    claim_words = _content_words(claim)

    on_topic: list[dict] = []
    for item in evidence:
        fact_words = _content_words(str(item.get("fact", "")))
        if len(claim_words & fact_words) >= _TOPIC_MATCH_MIN:
            on_topic.append(item)

    if not on_topic:
        return _result(claim, risk, SupportStatus.UNSUPPORTED, None,
                       "No eligible evidence discusses this claim.")

    # Among on-topic evidence, does any carry the same figure?
    matching = [
        item for item in on_topic
        if not claim_numbers or (claim_numbers & _numbers(str(item.get("fact", ""))))
    ]

    if claim_numbers and not matching:
        # Evidence exists on the topic and none of it carries this number. That is
        # a stronger signal than "unsupported" — it is a disagreement.
        return _result(
            claim, risk, SupportStatus.CONFLICTING, on_topic[0],
            f"{len(on_topic)} source(s) discuss this topic but none states "
            f"{', '.join(sorted(claim_numbers))}.")

    best = max(matching or on_topic,
               key=lambda i: SourceQuality(i.get("source_quality",
                                                 "UNKNOWN")).rank)
    quality = SourceQuality(best.get("source_quality", "UNKNOWN"))

    if quality.rank >= risk.minimum_source_quality.rank:
        return _result(claim, risk, SupportStatus.SUPPORTED, best,
                       f"Bound to a {quality.value} source.")

    return _result(
        claim, risk, SupportStatus.PARTIALLY_SUPPORTED, best,
        f"Bound to a {quality.value} source, but a {risk.value}-risk claim needs "
        f"at least {risk.minimum_source_quality.value}.")


def _result(claim: str, risk: ClaimRisk, status: SupportStatus,
            evidence: dict | None, reason: str) -> dict:
    return {
        "claim": claim[:400],
        "claim_risk": risk.value,
        "support_status": status.value,
        "evidence_ref": (evidence or {}).get("source_ref"),
        "evidence_url": (evidence or {}).get("url"),
        "source_quality": (evidence or {}).get("source_quality"),
        "reason": reason,
    }


def run_factual_qa(draft: dict, package: dict, profile: VerticalProfile) -> dict:
    """Return {status, score, findings, blocking_issues, claims}."""
    body = (draft.get("body") or "").strip()
    evidence = [f for f in (package.get("facts") or []) if f.get("supported")]

    # Eligible sources carry the URL and quality that the fact rows reference.
    by_ref = {s.get("ref"): s for s in (package.get("eligible_evidence") or [])}
    for item in evidence:
        source = by_ref.get(item.get("source_ref")) or {}
        item.setdefault("url", source.get("url"))

    claims = [assess_claim(c, evidence, profile) for c in extract_claims(body)]

    findings: list[dict] = []
    blocking: list[dict] = []

    for claim in claims:
        status = SupportStatus(claim["support_status"])
        risk = ClaimRisk(claim["claim_risk"])

        if status is SupportStatus.SUPPORTED:
            continue

        # The one rule that blocks. A HIGH-risk claim is a subsidy, a tax rate, a
        # legal obligation or a guarantee — wrong there is not a quality problem.
        is_blocking = risk is ClaimRisk.HIGH
        finding = {
            "code": f"CLAIM_{status.value}",
            "message": f"{risk.value}-risk claim is {status.value}: {claim['reason']}",
            "blocking": is_blocking,
            "detail": claim["claim"][:300],
        }
        findings.append(finding)
        if is_blocking:
            blocking.append(finding)

    if not evidence and claims:
        finding = {
            "code": "NO_ELIGIBLE_EVIDENCE",
            "message": (f"The draft makes {len(claims)} factual claim(s) but the "
                        f"package carries no supported evidence."),
            "blocking": True, "detail": "",
        }
        findings.append(finding)
        blocking.append(finding)

    supported = sum(1 for c in claims
                    if c["support_status"] == SupportStatus.SUPPORTED.value)
    score = int(round(100 * supported / len(claims))) if claims else 100

    return {
        "status": "FAILED" if blocking else "PASSED",
        "score": score,
        "findings": findings,
        "blocking_issues": blocking,
        "claims": claims,
    }
