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

_FACTUAL_SENTENCE = re.compile(
    r"\d[\d\s.,]*\s*(?:%|€|\$|£|eur|euros?|kwh|kwc|kwp|wc|wp|m²|m2|ans?|jaar|years?)",
    re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NUMBER = re.compile(r"(?<![\w/])(\d{1,3}(?:[  ., ]\d{3})+|\d+[.,]\d+|\d{2,})")

_TOPIC_MATCH_MIN = 2
# Two readings of one sentence count as equally strong within this margin. Below
# it the difference is not evidence of anything, and the verdict is a tie.
_MATCH_MARGIN = 0.05
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


def _region_of(claim: dict) -> Region:
    try:
        return Region(str(claim.get("region") or "").upper())
    except ValueError:
        return Region.UNKNOWN


def _finding(code: str, message: str, *, blocking: bool, detail: str = "") -> dict:
    return {"code": code, "message": message, "blocking": blocking,
            "detail": detail[:300]}


def extract_draft_claims(body: str) -> list[str]:
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s+", "", body, flags=re.M)
    cleaned = re.sub(r"^\s*[-*+]\s+", "", cleaned, flags=re.M)
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    return [s for s in sentences if _FACTUAL_SENTENCE.search(s)][:60]


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


def _arbitrate(sentence: str, claim: dict,
               supported: list[dict]) -> tuple[str, dict | None]:
    """Compare this sentence read as `claim` against its best supported reading."""
    this = _match_strength(sentence, claim)
    best, rival = 0.0, None
    for candidate in supported:
        if candidate is claim:
            continue
        strength = _match_strength(sentence, candidate)
        if strength > best:
            best, rival = strength, candidate
    if this - best > _MATCH_MARGIN:
        return _ASSERTED, rival
    if best - this > _MATCH_MARGIN:
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
        best, rival = 0.0, None
        for candidate in supported:
            if candidate is claim:
                continue
            strength = _match_strength(sentence, candidate)
            if strength > best:
                best, rival = strength, candidate
        verdict, _ = _arbitrate(sentence, claim, supported)
        rows.append({
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
                if verdict == _RIVAL:
                    # The sentence is really stating another supported claim; the
                    # scope of this one is not what it failed to name.
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
                    f"source establishes it for the country.",
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
