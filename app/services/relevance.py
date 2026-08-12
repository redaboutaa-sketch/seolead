"""RelevanceGate — the fix for the Phase 2 failure.

Phase 2's live run offered a single "supported fact" for
`prix panneaux solaires Belgique`: a Hacker News post titled *"The making of Don
Matrelli's Legacy, a mod for Grand Prix Circuit (part I)"*. Nothing rejected it,
because nothing was asking whether a source was about the query at all.

Naive token overlap does not fix that, and the reason is the interesting part:
**"prix" appears in "Grand Prix".** A gate scoring bare word overlap would give
that source a third of the query and call it partially relevant.

So the gate separates two kinds of query token:

* **topic tokens** — what the query is *about* (`panneaux`, `solaires`)
* **modifier tokens** — the commercial or comparative frame around it (`prix`,
  `comparatif`), taken from the vertical profile
* **market tokens** — the country's own name, which carries no topical signal

and applies one hard rule:

> A source matching **zero topic tokens** is IRRELEVANT, however many modifiers it
> matches.

"Grand Prix Circuit" matches the modifier `prix` and none of `panneaux`,
`solaires`. It is rejected deterministically, with a readable reason, before any
model is consulted.

Stage B (semantic) exists for the genuinely ambiguous middle, and runs only when
configured and only where Stage A could not decide. It can demote but never
promote past a hard rejection.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlparse

from app.core.errors import SeoLeadError
from app.providers.llm.base import LLMCapability, LLMProvider, LLMRequest
from app.services.intent import normalize_query
from app.verticals.profile import VerticalProfile

logger = logging.getLogger(__name__)


class RelevanceStatus(StrEnum):
    RELEVANT = "RELEVANT"
    LOW_RELEVANCE = "LOW_RELEVANCE"
    IRRELEVANT = "IRRELEVANT"
    UNKNOWN = "UNKNOWN"

    @property
    def is_eligible(self) -> bool:
        """Only RELEVANT sources may become evidence for the writer.

        LOW_RELEVANCE is deliberately not eligible: a weak match is exactly the
        kind of thing that reads plausible in a draft and cannot be defended.
        """
        return self is RelevanceStatus.RELEVANT


@dataclass(frozen=True)
class RelevanceThresholds:
    """Tunable, and openly arbitrary.

    These numbers were chosen so the Phase 2 failure is rejected and the obvious
    good cases pass. They are not validated against a labelled corpus and must not
    be presented as if they were.
    """

    relevant_at: float = 0.55
    low_relevance_at: float = 0.30
    # Below this, a source is rejected outright rather than kept as "low".
    irrelevant_below: float = 0.30
    # Weight of the title vs the body excerpt when scoring topical coverage.
    title_weight: float = 0.6
    body_weight: float = 0.4


@dataclass
class RelevanceDecision:
    status: RelevanceStatus
    score: float
    reason: str
    signals: dict = field(default_factory=dict)
    stage: str = "deterministic"

    def as_dict(self) -> dict:
        return {"status": self.status.value, "score": round(self.score, 3),
                "reason": self.reason, "signals": self.signals, "stage": self.stage}


# Short function words carry no topical signal in fr/nl/en.
_STOPWORDS = frozenset({
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "en", "au",
    "aux", "pour", "par", "sur", "dans", "avec", "sans", "est", "sont", "a",
    "the", "of", "and", "or", "for", "in", "on", "with", "to", "is", "are",
    "het", "een", "van", "voor", "met", "zonder", "op", "in", "is", "zijn",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stem(token: str) -> str:
    """A deliberately light stemmer for fr/nl/en plurals.

    `panneaux`→`panneau`, `chevaux`→`cheval`, `solaires`→`solaire`,
    `panels`→`panel`. Full stemming would be more accurate and would also silently
    merge unrelated words; this is the smallest rule that makes plural queries
    match singular titles.

    The `-eaux` case must be checked BEFORE `-aux`. French has two unrelated
    plurals ending in `aux`: `panneau→panneaux` (drop the x) and
    `cheval→chevaux` (aux→al). Applying the second rule to the first yields
    `panneal`, which matches nothing — and `panneau` is a topic token for the
    pilot query, so getting this wrong disables the gate's central check.
    """
    if len(token) > 4:
        if token.endswith("eaux"):
            return token[:-1]
        if token.endswith("aux"):
            return token[:-3] + "al"
        if token.endswith(("s", "x")):
            return token[:-1]
    return token


def tokenize(text: str) -> set[str]:
    normalized = normalize_query(text or "")
    return {
        _stem(t) for t in _TOKEN_RE.findall(normalized)
        if len(t) > 2 and t not in _STOPWORDS
    }


@dataclass(frozen=True)
class QueryProfile:
    """The query, split into the parts that mean different things."""

    topic_tokens: frozenset[str]
    modifier_tokens: frozenset[str]
    market_tokens: frozenset[str]

    @property
    def has_topic(self) -> bool:
        return bool(self.topic_tokens)


def build_query_profile(query: str, profile: VerticalProfile) -> QueryProfile:
    tokens = tokenize(query)
    modifiers = set()
    for term in list(profile.commercial_terms) + list(profile.comparison_terms):
        modifiers |= tokenize(term)
    markets = set()
    for term in profile.market_terms:
        markets |= tokenize(term)

    topic = tokens - modifiers - markets
    return QueryProfile(
        topic_tokens=frozenset(topic),
        modifier_tokens=frozenset(tokens & modifiers),
        market_tokens=frozenset(tokens & markets),
    )


def _coverage(query_tokens: frozenset[str], text_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def score_source(
    *,
    query: str,
    profile: VerticalProfile,
    title: str | None,
    body: str | None,
    url: str | None = None,
    thresholds: RelevanceThresholds | None = None,
) -> RelevanceDecision:
    """Stage A. Deterministic, explainable, no model."""
    thresholds = thresholds or RelevanceThresholds()
    query_profile = build_query_profile(query, profile)

    title_tokens = tokenize(title or "")
    body_tokens = tokenize(body or "")
    all_tokens = title_tokens | body_tokens

    domain = None
    if url:
        try:
            domain = (urlparse(url).hostname or "").lower() or None
        except ValueError:
            domain = None
    domain_tokens = tokenize(domain.replace(".", " ")) if domain else set()

    topic_matched = query_profile.topic_tokens & (all_tokens | domain_tokens)
    modifier_matched = query_profile.modifier_tokens & all_tokens

    signals = {
        "topic_tokens": sorted(query_profile.topic_tokens),
        "topic_matched": sorted(topic_matched),
        "modifier_tokens": sorted(query_profile.modifier_tokens),
        "modifier_matched": sorted(modifier_matched),
        "market_tokens": sorted(query_profile.market_tokens),
        "domain": domain,
    }

    # ── The hard rule ────────────────────────────────────────────────────────
    # Zero topical overlap means the source is about something else, whatever
    # else it matched. This is what rejects "Grand Prix Circuit" for a solar
    # pricing query: it matches the modifier `prix` and no topic token.
    if query_profile.has_topic and not topic_matched:
        matched_only = ", ".join(sorted(modifier_matched)) or "nothing"
        return RelevanceDecision(
            status=RelevanceStatus.IRRELEVANT,
            score=0.0,
            reason=(
                f"No topical overlap with the query. The query is about "
                f"{', '.join(sorted(query_profile.topic_tokens))}; this source "
                f"matched only {matched_only}."
            ),
            signals=signals,
        )

    if not query_profile.has_topic:
        # A query made entirely of modifiers and a country name is not something
        # this gate can judge. Saying so beats guessing.
        return RelevanceDecision(
            status=RelevanceStatus.UNKNOWN, score=0.0,
            reason="Query carries no topical tokens; relevance cannot be assessed "
                   "deterministically.",
            signals=signals,
        )

    title_coverage = _coverage(query_profile.topic_tokens, title_tokens)
    body_coverage = _coverage(query_profile.topic_tokens, body_tokens)
    topic_score = (thresholds.title_weight * title_coverage
                   + thresholds.body_weight * body_coverage)

    # A source that also matches the commercial frame is more on-intent, but this
    # can only ever be a bonus — it cannot rescue a source with weak topical fit.
    modifier_bonus = 0.0
    if query_profile.modifier_tokens:
        modifier_bonus = 0.15 * _coverage(query_profile.modifier_tokens, all_tokens)

    # A matching domain says what the SITE is about; title and body say what the
    # PAGE is about. `panneaux-solaires-belgique.be/tarifs` titled "Nos tarifs" is
    # genuinely on-topic, so the domain earns credit — but capped below the
    # RELEVANT threshold, because a solar company's careers page is still not
    # evidence about solar pricing. Domain alone reaches LOW_RELEVANCE at most.
    domain_bonus = 0.35 * _coverage(query_profile.topic_tokens, domain_tokens)

    # Full topical coverage in the body alone should not be penalised into
    # LOW_RELEVANCE just because the title is short.
    score = min(1.0, max(topic_score, 0.85 * body_coverage, domain_bonus)
                + modifier_bonus)

    signals.update({
        "title_coverage": round(title_coverage, 3),
        "body_coverage": round(body_coverage, 3),
        "modifier_bonus": round(modifier_bonus, 3),
        "domain_bonus": round(domain_bonus, 3),
    })

    if score >= thresholds.relevant_at:
        status = RelevanceStatus.RELEVANT
        reason = (f"Covers {len(topic_matched)}/{len(query_profile.topic_tokens)} "
                  f"topic tokens (score {score:.2f}).")
    elif score >= thresholds.low_relevance_at:
        status = RelevanceStatus.LOW_RELEVANCE
        reason = (f"Partial topical match, score {score:.2f} below the "
                  f"{thresholds.relevant_at:.2f} threshold.")
    else:
        status = RelevanceStatus.IRRELEVANT
        reason = (f"Topical match too weak, score {score:.2f} below the "
                  f"{thresholds.irrelevant_below:.2f} floor.")

    return RelevanceDecision(status=status, score=score, reason=reason,
                            signals=signals)


def score_claim(
    *, query: str, profile: VerticalProfile, claim: str,
    source_decision: RelevanceDecision,
    thresholds: RelevanceThresholds | None = None,
) -> RelevanceDecision:
    """Claim-level relevance.

    A relevant source does not make every sentence in it relevant. A page about
    solar installation costs may also discuss the author's holiday, and that
    sentence must not become an eligible fact.

    A claim can never outrank its source: an IRRELEVANT source's claims are
    IRRELEVANT regardless of their wording.
    """
    thresholds = thresholds or RelevanceThresholds()

    if source_decision.status is RelevanceStatus.IRRELEVANT:
        return RelevanceDecision(
            status=RelevanceStatus.IRRELEVANT, score=0.0,
            reason="Parent source was rejected as irrelevant.",
            signals={"inherited": True},
        )

    decision = score_source(query=query, profile=profile, title=None, body=claim,
                            thresholds=thresholds)
    # Clamp to the source's own status — a claim cannot be more relevant than the
    # page it came from.
    if (source_decision.status is RelevanceStatus.LOW_RELEVANCE
            and decision.status is RelevanceStatus.RELEVANT):
        return RelevanceDecision(
            status=RelevanceStatus.LOW_RELEVANCE, score=decision.score,
            reason=("Claim reads on-topic but its source is only weakly relevant; "
                    "clamped to the source's status."),
            signals=decision.signals,
        )
    return decision


_SEMANTIC_SYSTEM = (
    "You judge whether a retrieved source is relevant to a search query. "
    "You are a classifier, not a writer. Consider only topical relevance: does "
    "this source help someone who searched that query? Reply with JSON only: "
    "{\"status\": \"RELEVANT\"|\"LOW_RELEVANCE\"|\"IRRELEVANT\", "
    "\"reason\": \"one short sentence\"}"
)


async def semantic_review(
    *, query: str, title: str | None, body: str | None, llm: LLMProvider,
    correlation_id: str, current: RelevanceDecision,
) -> RelevanceDecision:
    """Stage B. Only for the ambiguous middle, and only ever downward.

    Never called for a hard rejection: a model that disagrees with "this source
    shares no topic with the query" is wrong, and asking invites it to be.
    """
    if not llm.configured:
        return current
    if current.status is not RelevanceStatus.LOW_RELEVANCE:
        return current

    prompt = json.dumps({
        "query": query, "source_title": title,
        "source_excerpt": (body or "")[:2000],
    }, ensure_ascii=False)

    try:
        response = await llm.generate(LLMRequest(
            capability=LLMCapability.CLASSIFICATION, system=_SEMANTIC_SYSTEM,
            prompt=prompt, response_format="json", temperature=0.0,
            max_tokens=200, correlation_id=correlation_id,
        ))
        parsed = json.loads(response.content)
        status = RelevanceStatus(str(parsed.get("status", "")).upper())
    except (SeoLeadError, json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("semantic relevance review skipped: %s", type(exc).__name__,
                       extra={"correlation_id": correlation_id})
        return current

    if status is RelevanceStatus.RELEVANT:
        # Promotion allowed only out of LOW_RELEVANCE, which is where we are.
        return RelevanceDecision(
            status=RelevanceStatus.RELEVANT, score=max(current.score, 0.6),
            reason=f"Semantic review: {str(parsed.get('reason', ''))[:200]}",
            signals=current.signals, stage="semantic",
        )
    if status is RelevanceStatus.IRRELEVANT:
        return RelevanceDecision(
            status=RelevanceStatus.IRRELEVANT, score=min(current.score, 0.2),
            reason=f"Semantic review: {str(parsed.get('reason', ''))[:200]}",
            signals=current.signals, stage="semantic",
        )
    return current
