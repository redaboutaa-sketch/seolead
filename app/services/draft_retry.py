"""Re-emitting the draft, and only the draft.

A run that reaches QA has already bought everything expensive: the SERP, the
research passes, the passage extraction, the evidence decisions. What failed is
the last step — one model call that turned all of it into prose. Throwing the
run away and starting over pays for the research a second time to fix a writing
fault, and it changes the subject: the second draft is then judged against a
different evidence set, so nothing can be compared.

So the retry re-emits the draft call alone, against the same sealed brief and
package, carrying the blocking findings of the attempt before it into the prompt.
Two extra attempts, no more. A third would not be a retry policy, it would be
sampling until the gate looks away — and a gate you can outlast is not a gate.

Not every blocking finding is a writing fault, and the ones that are not must
never be retried:

    INSUFFICIENT_SUPPORTED_EVIDENCE   the package holds fewer supported facts
    NO_SUPPORTED_EVIDENCE             than the vertical requires. No rewrite
    NO_SUPPORTED_CLAIMS               creates evidence; asking for one is asking
    NO_TRACEABLE_SOURCES              the writer to invent it.

    DUPLICATE_TITLE                   another page already occupies this ground.
                                      The slug comes from the keyword, so a new
                                      title does not resolve the collision — a
                                      person decides which page survives.

    AMBIGUOUS_MATCH                   the finding says in its own message that
                                      it is a matcher case and not a drafting
                                      fault. Re-rolling on it asks the writer to
                                      change a sentence that may well be right,
                                      blind, and would eventually produce one
                                      the matcher happens to like. That is the
                                      failure this whole file exists to avoid.

Everything else is a writing fault the same evidence can answer differently: a
claim asserted that the ledger refused, a Walloon figure stated flat, supported
facts left on the table.
"""
from __future__ import annotations

from dataclasses import dataclass

# The first draft plus two re-emissions.
MAX_ATTEMPTS = 3

NOT_RETRIABLE = frozenset({
    "INSUFFICIENT_SUPPORTED_EVIDENCE",
    "NO_SUPPORTED_EVIDENCE",
    "NO_SUPPORTED_CLAIMS",
    "NO_TRACEABLE_SOURCES",
    "DUPLICATE_TITLE",
    "AMBIGUOUS_MATCH",
})


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    reason: str
    attempt: int
    attempts_left: int
    blocked_by: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"retry": self.retry, "reason": self.reason,
                "attempt": self.attempt, "attempts_left": self.attempts_left,
                "blocked_by": list(self.blocked_by)}


def codes(findings: list[dict] | None) -> list[str]:
    return [str(f.get("code")) for f in findings or []]


def decide(blocking: list[dict] | None, *, attempt: int,
           max_attempts: int = MAX_ATTEMPTS) -> RetryDecision:
    """Whether to spend one more draft call on this brief.

    `attempt` is 1-based and counts the draft just judged.
    """
    left = max(0, max_attempts - attempt)
    present = codes(blocking)

    if not present:
        return RetryDecision(False, "the draft passed both deterministic gates",
                             attempt, left)

    refused = tuple(sorted({c for c in present if c in NOT_RETRIABLE}))
    if refused:
        return RetryDecision(
            False,
            "at least one blocking finding is not a writing fault, so no "
            "rewrite can answer it",
            attempt, left, refused)

    if left <= 0:
        return RetryDecision(
            False,
            f"the writer had {max_attempts} attempts on this brief and the gate "
            f"still refuses the draft; a further attempt would be sampling, "
            f"not correcting",
            attempt, 0, tuple(sorted(set(present))))

    return RetryDecision(True, "every blocking finding is one a different draft "
                               "of the same evidence can answer",
                         attempt, left, tuple(sorted(set(present))))


# What to do about a finding, in the writer's terms. Measured 2026-09-03: four
# regenerations, and at every one the writer answered REGIONAL_SCOPE_NOT_STATED
# by naming the region in the sentence BEFORE the figure, or by « y ». The
# finding said what was wrong; nobody had said what to write.
FIXES: dict[str, str] = {
    "REGIONAL_SCOPE_NOT_STATED": (
        "Rewrite the sentence quoted in `in_your_text` so that the region's "
        "name (for example « en Wallonie ») appears in that sentence, or open "
        "its paragraph with the region; « y » alone does not name a region."),
    "REQUIRED_FACTS_UNDERUSED": (
        "Add sentences that state the unused facts listed in `in_your_text`, "
        "each with its region; do not rewrite the facts you already used."),
    "NUMBER_WITHOUT_SOURCE": (
        "Remove the figure, or state the full range the evidence gives — never "
        "one end of it alone."),
    "ROI_WITHOUT_DATED_SOURCE": (
        "Remove the payback statement, or attribute it to the dated official "
        "figure the facts supply."),
    "SUPPORT_FREE_CLAIM_WITHOUT_OFFICIAL_SOURCE": (
        "Delete the statement about profitability without public support."),
    "HIGH_RISK_CLAIM_ASSERTED": (
        "Drop the assertion; the evidence does not carry it in any wording."),
    "CONFLICTING_EVIDENCE_ASSERTED": (
        "Drop the figure; the sources disagree on it."),
    "UNSUPPORTED_DRAFT_CLAIM": (
        "Drop the sentence, or restate it as one of the supplied facts."),
    "RESTRICTED_CLAIM_QUANTIFIED": (
        "Mention the topic without any figure."),
}


def carried(blocking: list[dict] | None, *, limit: int = 12) -> list[dict]:
    """The findings handed to the next attempt, smallest useful form: the
    code, the problem in the gate's words, the sentence concerned, and what
    to do about it."""
    out = []
    for f in (blocking or [])[:limit]:
        code = str(f.get("code"))
        out.append({"code": code, "problem": str(f.get("message") or ""),
                    "in_your_text": str(f.get("detail") or ""),
                    "fix": FIXES.get(code, "Change what you write so that this "
                                           "finding cannot be raised again.")})
    return out
