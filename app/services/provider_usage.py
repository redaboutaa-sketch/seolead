"""Provider usage and cost accounting.

Two rules make this useful rather than decorative.

**Never invent a cost.** DataForSEO returns its own `cost` in USD, so that is
recorded as actual. Tavily and OpenAI do not return money, so their cost stays
`None` unless a price table is configured — and a recorded `None` is a different
fact from a recorded `0.0`. `cost_is_actual` says which it is.

**Bound the job.** `JobBudget` caps calls per provider per job, so a bug that loops
over a paid API stops at a readable error instead of at an invoice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.errors import SeoLeadError

logger = logging.getLogger(__name__)


class ProviderBudgetExceeded(SeoLeadError):
    code = "PROVIDER_BUDGET_EXCEEDED"


@dataclass
class UsageEvent:
    provider: str
    operation: str
    correlation_id: str
    requests: int = 1
    units: int | None = None          # tokens, results, whatever the provider bills
    cost_usd: float | None = None
    cost_is_actual: bool = False
    duration_ms: int | None = None

    def as_dict(self) -> dict:
        return {
            "provider": self.provider, "operation": self.operation,
            "correlation_id": self.correlation_id, "requests": self.requests,
            "units": self.units, "cost_usd": self.cost_usd,
            "cost_is_actual": self.cost_is_actual, "duration_ms": self.duration_ms,
        }


class UsageRecorder:
    """Collects usage for one job. Persisted by the pipeline at the end."""

    def __init__(self, budget: "JobBudget | None" = None):
        self.events: list[UsageEvent] = []
        self._budget = budget

    def record(self, *, provider: str, operation: str, correlation_id: str,
               requests: int = 1, units: int | None = None,
               cost_usd: float | None = None, cost_is_actual: bool = False,
               duration_ms: int | None = None) -> None:
        event = UsageEvent(provider=provider, operation=operation,
                           correlation_id=correlation_id, requests=requests,
                           units=units, cost_usd=cost_usd,
                           cost_is_actual=cost_is_actual, duration_ms=duration_ms)
        self.events.append(event)
        logger.info("provider usage", extra={
            "correlation_id": correlation_id, "provider": provider,
            "status": operation, "duration_ms": duration_ms})

    def check_and_consume(self, provider: str) -> None:
        """Call BEFORE a paid request. Raises rather than spending."""
        if self._budget is not None:
            self._budget.consume(provider)

    def has(self, provider: str, operation: str | None = None) -> bool:
        return any(e.provider == provider
                   and (operation is None or e.operation == operation)
                   for e in self.events)

    def ensure_recorded(self, *, provider: str, operation: str,
                        correlation_id: str, duration_ms: int | None = None) -> None:
        """Record a call the adapter did not record itself.

        Adapters record their own usage because they alone know the provider's
        reported cost. But that makes the ledger depend on every adapter
        remembering, and one that forgets is silently absent from the cost report
        — the failure is invisible precisely where money is involved. The
        orchestrator therefore backstops it: a call it made that left no trace
        gets an entry with an unknown cost, which is the honest record.
        """
        if self.has(provider, operation):
            return
        self.record(provider=provider, operation=operation,
                    correlation_id=correlation_id, requests=1, cost_usd=None,
                    cost_is_actual=False, duration_ms=duration_ms)

    def total_cost_usd(self) -> float | None:
        """Sum of costs we actually know. None when nothing was priced.

        Deliberately not `0.0`: a job whose providers report no cost has an
        unknown spend, not a free one.
        """
        known = [e.cost_usd for e in self.events if e.cost_usd is not None]
        return round(sum(known), 6) if known else None

    def summary(self) -> dict:
        by_provider: dict[str, dict] = {}
        for event in self.events:
            entry = by_provider.setdefault(event.provider, {
                "requests": 0, "operations": {}, "cost_usd": None,
                "cost_is_actual": False, "units": 0,
            })
            entry["requests"] += event.requests
            entry["operations"][event.operation] = \
                entry["operations"].get(event.operation, 0) + event.requests
            if event.units:
                entry["units"] += event.units
            if event.cost_usd is not None:
                entry["cost_usd"] = round((entry["cost_usd"] or 0.0) + event.cost_usd, 6)
                entry["cost_is_actual"] = entry["cost_is_actual"] or event.cost_is_actual
        return {
            "by_provider": by_provider,
            "total_cost_usd": self.total_cost_usd(),
            "total_requests": sum(e.requests for e in self.events),
            "priced_events": sum(1 for e in self.events if e.cost_usd is not None),
            "unpriced_events": sum(1 for e in self.events if e.cost_usd is None),
        }


@dataclass
class JobBudget:
    """Per-job call ceilings. A backstop against runaway research loops."""

    max_calls_per_provider: dict[str, int] = field(default_factory=dict)
    default_max_calls: int = 5
    _used: dict[str, int] = field(default_factory=dict)

    def consume(self, provider: str) -> None:
        limit = self.max_calls_per_provider.get(provider, self.default_max_calls)
        used = self._used.get(provider, 0)
        if used >= limit:
            raise ProviderBudgetExceeded(
                f"provider {provider!r} reached its per-job limit of {limit} calls"
            )
        self._used[provider] = used + 1

    def used(self) -> dict[str, int]:
        return dict(self._used)
