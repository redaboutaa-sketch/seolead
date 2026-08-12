"""Last30Days agent-contract → normalized model.

Two upstream rules drive every line here, and both are load-bearing:

1. *Unknown fields are omitted, not emitted as null.* Nothing indexes; everything
   uses `.get()`. A result legitimately has no `published_at`, and a `KeyError` on
   healthy data would be our bug, not theirs.

2. *Only `no-results` means a source completed cleanly with zero matches.* The
   other nine states are preserved distinctly. Collapsing `auth-failed` into "no
   discussion found" would assert something about the world that we never observed
   — and three steps later an LLM would write it down as fact.

Contract version policy matches upstream: major 1 required, minor >= 2 required
(`candidate_id` arrived in 1.2 and freshness verdicts join on it), unknown fields
ignored, different major refused outright and never retried.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.enums import FreshnessVerdict, Observability, SourceState
from app.core.errors import ResearchContractError
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)

logger = logging.getLogger(__name__)

SUPPORTED_MAJOR = 1
MINIMUM_MINOR = 2


def _parse_schema_version(report: Mapping[str, Any]) -> tuple[int, int]:
    raw = report.get("schema_version")
    if raw is None:
        raise ResearchContractError("report has no schema_version")
    try:
        major_s, _, minor_s = str(raw).partition(".")
        major, minor = int(major_s), int(minor_s or 0)
    except ValueError as exc:
        raise ResearchContractError(f"malformed schema_version: {raw!r}") from exc

    if major != SUPPORTED_MAJOR:
        # Not retryable: a retry cannot change the engine's version.
        raise ResearchContractError(
            f"unsupported contract major {major} (supported: {SUPPORTED_MAJOR})"
        )
    if minor < MINIMUM_MINOR:
        raise ResearchContractError(
            f"contract minor {minor} below minimum {MINIMUM_MINOR}"
        )
    return major, minor


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp, or return None.

    Returning None on an unparseable value is deliberate. The alternative —
    substituting `now()` — would manufacture a publication date, which is exactly
    the class of invented fact this pipeline exists to prevent.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable timestamp discarded: %r", value[:40])
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _coerce_state(raw: Any) -> SourceState:
    try:
        return SourceState(str(raw))
    except ValueError:
        # An unrecognised state is drift, and drift is not "ok". Treating it as
        # SCHEMA_DRIFT keeps it out of the "produced items" and "clean empty" sets.
        logger.warning("unknown source state %r — recording as schema-drift", raw)
        return SourceState.SCHEMA_DRIFT


def _coerce_verdict(raw: Any) -> FreshnessVerdict | None:
    try:
        return FreshnessVerdict(str(raw))
    except ValueError:
        return None


def normalize(
    envelope: Mapping[str, Any],
    *,
    query: str,
    market: str,
    language: str,
) -> ResearchProviderResult:
    """Map one runner envelope into the provider-neutral result.

    `envelope` is the runner's response: {run_id, engine_commit, …, report{…}}.
    """
    report = envelope.get("report")
    if not isinstance(report, Mapping):
        raise ResearchContractError("envelope has no report object")

    _parse_schema_version(report)

    # ── Per-source outcomes ──────────────────────────────────────────────────
    raw_status = report.get("source_status")
    if not isinstance(raw_status, Mapping):
        raise ResearchContractError("report has no source_status map")

    outcomes: dict[str, SourceOutcome] = {}
    item_counts: dict[str, int] = {}
    states: dict[str, SourceState] = {
        str(name): _coerce_state(state) for name, state in raw_status.items()
    }

    # ── Freshness verdicts, joined on candidate_id ───────────────────────────
    verdicts: dict[str, FreshnessVerdict] = {}
    for entry in report.get("freshness_verdicts") or []:
        if not isinstance(entry, Mapping):
            continue
        candidate = entry.get("candidate_id")
        verdict = _coerce_verdict(entry.get("verdict"))
        if candidate and verdict:
            verdicts[str(candidate)] = verdict

    # ── Results → sources + facts ────────────────────────────────────────────
    sources: list[NormalizedSource] = []
    facts: list[NormalizedFact] = []

    for item in report.get("results") or []:
        if not isinstance(item, Mapping):
            continue
        source_type = str(item.get("source") or "unknown")
        state = states.get(source_type, SourceState.OK)
        candidate_id = item.get("candidate_id")
        candidate_key = str(candidate_id) if candidate_id else None
        verdict = verdicts.get(candidate_key) if candidate_key else None

        url = item.get("url")
        published_at = _parse_dt(item.get("published_at"))

        sources.append(NormalizedSource(
            source_type=source_type,
            state=state,
            url=str(url) if url else None,
            title=(str(item["title"]) if item.get("title") else None),
            published_at=published_at,
            retrieved_at=_parse_dt(report.get("generated_at")),
            summary=(str(item["summary"]) if item.get("summary") else None),
            confidence=_as_float(item.get("relevance_score")),
            freshness_verdict=verdict,
            candidate_id=candidate_key,
            metadata={
                "last30days": {
                    "engagement": item.get("engagement"),
                    "cluster": item.get("cluster"),
                    "relevance_score": item.get("relevance_score"),
                }
            },
        ))
        item_counts[source_type] = item_counts.get(source_type, 0) + 1

        # A retrieved item with a URL is an OBSERVED statement by that source.
        # It is NOT a verified claim about the world — `evidence_type` says
        # "reported", and a stale or contradicted verdict downgrades it.
        summary = item.get("summary") or item.get("title")
        if summary and url:
            facts.append(NormalizedFact(
                fact=str(summary),
                evidence_type="reported",
                observability=_observability_for(verdict, published_at),
                confidence=_as_float(item.get("relevance_score")),
                source_ref=candidate_key,
            ))

    # Every source that was asked gets an outcome row, item or no item.
    for source_type, state in states.items():
        outcomes[source_type] = SourceOutcome(
            source_type=source_type,
            state=state,
            item_count=item_counts.get(source_type, 0),
        )

    # ── Cluster summaries become user-facing themes, not facts ───────────────
    user_questions: list[str] = []
    for cluster in report.get("clusters") or []:
        if isinstance(cluster, Mapping) and cluster.get("title"):
            user_questions.append(str(cluster["title"]))

    # ── Unresolved: what we could not observe, stated plainly ────────────────
    unresolved: list[str] = []
    for source_type, outcome in sorted(outcomes.items()):
        if outcome.state.is_degraded:
            unresolved.append(
                f"Source '{source_type}' could not be observed ({outcome.state.value}); "
                f"absence of results from it is not evidence of absence."
            )
        elif not outcome.state.was_attempted:
            unresolved.append(
                f"Source '{source_type}' was not configured and was never queried."
            )

    status = "PARTIAL" if any(o.state.is_degraded for o in outcomes.values()) else "SUCCEEDED"
    if not facts and status == "SUCCEEDED" and not any(
        o.state.is_clean_empty for o in outcomes.values()
    ):
        # No facts, nothing degraded, and nothing reported a clean empty result:
        # the report is internally inconsistent. Say so rather than call it success.
        status = "PARTIAL"

    return ResearchProviderResult(
        provider="last30days",
        query=query,
        market=market,
        language=language,
        status=status,
        sources=sources,
        facts=facts,
        source_outcomes=sorted(outcomes.values(), key=lambda o: o.source_type),
        user_questions=user_questions,
        unresolved_data=unresolved,
        provider_metadata={
            "last30days": {
                "run_id": envelope.get("run_id"),
                "correlation_id": envelope.get("correlation_id"),
                "schema_version": report.get("schema_version"),
                "window_days": report.get("window_days"),
                "generated_at": report.get("generated_at"),
                "idempotent_replay": envelope.get("idempotent_replay"),
                "runner_version": envelope.get("runner_version"),
            }
        },
        duration_ms=_as_int(envelope.get("duration_ms")),
        engine_commit=_as_str(envelope.get("engine_commit")),
        engine_version=_as_str(envelope.get("engine_version")),
        warnings=[str(w)[:300] for w in (envelope.get("warnings") or [])][:20],
    )


def _observability_for(
    verdict: FreshnessVerdict | None, published_at: datetime | None
) -> Observability:
    """Map a freshness verdict onto how much we know.

    `contradicted` and `unsupported` never become OBSERVED: the engine actively
    checked and could not stand the claim up. An undated item is ESTIMATED at best
    — we saw it, but we cannot place it in time, and a price or regulation without
    a date is not something a reader can rely on.
    """
    if verdict is FreshnessVerdict.CONTRADICTED:
        return Observability.UNKNOWN
    if verdict is FreshnessVerdict.UNSUPPORTED:
        return Observability.UNKNOWN
    if verdict is FreshnessVerdict.STALE:
        return Observability.ESTIMATED
    if published_at is None:
        return Observability.ESTIMATED
    return Observability.OBSERVED


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str | None:
    return str(value) if value else None
