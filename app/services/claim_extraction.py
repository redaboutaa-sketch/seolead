"""Atomic claim extraction — the second stage of the evidence model.

A claim is **one materially testable proposition**. The Phase 3 failure was that a
2 KB paragraph mixing pricing, a subsidy, a regulation and an ROI figure became a
single "fact" — so risk classification saw a document, and no downstream stage
could reason about any one assertion in it.

Two rules shape the splitting:

* **Split on assertion boundaries, not just sentences.** A sentence carrying two
  distinct quantified propositions ("l'installation coûte 5 000 € et la prime
  s'élève à 1 500 €") is two claims, because they are checkable against different
  sources and carry different risk.
* **Keep the exact passage.** Every claim points back at the text it came from, so
  "the exact supporting passage" is available to QA and to a human reviewer.

Deterministic. No model participates: an LLM splitting claims would be an LLM
deciding what counts as a fact, which is the thing this pipeline exists to avoid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.passage_extraction import Passage

# A proposition worth testing carries a quantity, a named rule, or a definite
# assertion. Sentences with none of these are context, not claims.
_QUANTITY = re.compile(
    r"(?<![\w/])\d[\d\s.,]*\s*"
    r"(?:%|€|\$|£|eur|euros?|cents?|kwh|kwc|kwp|wc|wp|kw|mwh|m²|m2|"
    r"ans?|années?|mois|jaar|years?|fois)",
    re.IGNORECASE)
_BARE_NUMBER = re.compile(r"(?<![\w/])\d{2,}(?![\w/])")

# Clause separators that usually join two independent assertions.
_CLAUSE_SPLIT = re.compile(
    r"\s*(?:;|\.\s+|\s+(?:et|ou|mais|tandis que|alors que|"
    r"and|or|but|while|whereas|en)\s+(?=(?:la|le|les|un|une|des|il|elle|on|"
    r"the|a|an|it)\s))",
    re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÿ0-9])")

_MIN_CLAIM_CHARS = 25
_MAX_CLAIM_CHARS = 320
_MAX_CLAIMS_PER_PASSAGE = 8

# Interrogative or promotional openings are not assertions.
_NON_ASSERTION = re.compile(
    r"^\s*(?:vous souhaitez|souhaitez-vous|voulez-vous|demandez|contactez|"
    r"découvrez|profitez|cliquez|remplissez|obtenez votre|recevez|"
    r"do you want|would you like|contact us|discover|get your|sign up)\b",
    re.IGNORECASE)
_QUESTION = re.compile(r"\?\s*$")


@dataclass(frozen=True)
class AtomicClaim:
    """One materially testable proposition, bound to the passage it came from."""

    text: str
    passage: str
    source_ref: str
    offset: int
    extraction_method: str = "deterministic_v1"
    quantified: bool = False

    def as_dict(self) -> dict:
        return {
            "text": self.text, "passage": self.passage,
            "source_ref": self.source_ref, "offset": self.offset,
            "extraction_method": self.extraction_method,
            "quantified": self.quantified,
        }


@dataclass
class ClaimSet:
    claims: list[AtomicClaim] = field(default_factory=list)
    skipped: int = 0

    def summary(self) -> dict:
        return {"claims": len(self.claims), "skipped_fragments": self.skipped,
                "quantified": sum(1 for c in self.claims if c.quantified)}


def _is_assertion(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < _MIN_CLAIM_CHARS:
        return False
    if _QUESTION.search(stripped):
        return False
    if _NON_ASSERTION.match(stripped):
        # "Vous souhaitez un devis ?" is a call to action, not a proposition.
        return False
    # Needs at least a handful of real words.
    return len([w for w in stripped.split() if len(w) > 2]) >= 5


def _is_quantified(text: str) -> bool:
    return bool(_QUANTITY.search(text) or _BARE_NUMBER.search(text))


def _split_into_propositions(sentence: str) -> list[str]:
    """Split a sentence carrying several distinct assertions.

    Only splits when the parts are independently testable — a sentence with one
    quantity stays whole, because chopping it would separate the number from what
    it measures.
    """
    quantities = len(_QUANTITY.findall(sentence))
    if quantities <= 1 and len(sentence) <= _MAX_CLAIM_CHARS:
        return [sentence]

    parts = [p.strip() for p in _CLAUSE_SPLIT.split(sentence) if p and p.strip()]
    if len(parts) <= 1:
        return [sentence]

    # Re-join fragments that lost their subject, so a clause like "et la prime
    # s'élève à 1 500 €" does not become a claim with no referent.
    merged: list[str] = []
    for part in parts:
        if merged and len(part.split()) < 4:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


def extract_claims(passage: Passage) -> list[AtomicClaim]:
    """Extract atomic claims from one passage."""
    claims: list[AtomicClaim] = []
    for sentence in _SENTENCE_SPLIT.split(passage.text):
        sentence = sentence.strip()
        if not sentence:
            continue
        for proposition in _split_into_propositions(sentence):
            proposition = proposition.strip(" ,;:")
            if not _is_assertion(proposition):
                continue
            claims.append(AtomicClaim(
                text=proposition[:_MAX_CLAIM_CHARS],
                # The exact passage the claim came from — quotable in QA and by a
                # human reviewer without going back to the live page.
                passage=passage.text[:1000],
                source_ref=passage.source_ref,
                offset=passage.offset,
                quantified=_is_quantified(proposition),
            ))
            if len(claims) >= _MAX_CLAIMS_PER_PASSAGE:
                return claims
    return claims


def extract_claim_set(passages: list[Passage]) -> ClaimSet:
    result = ClaimSet()
    seen: set[str] = set()
    for passage in passages:
        for claim in extract_claims(passage):
            key = " ".join(claim.text.casefold().split())[:160]
            if key in seen:
                # The same sentence repeated across a page is one claim, not two;
                # counting it twice would fake corroboration.
                result.skipped += 1
                continue
            seen.add(key)
            result.claims.append(claim)
    return result
