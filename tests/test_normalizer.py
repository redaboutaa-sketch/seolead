"""Last30Days normalization.

The tests that matter here are the ones asserting what must NOT happen: a degraded
source must not look like an empty one, an unknown date must not become a date, and
a contradicted claim must not be recorded as observed.
"""
from __future__ import annotations

import pytest

from app.core.enums import FreshnessVerdict, Observability, SourceState
from app.core.errors import ResearchContractError
from app.providers.research.last30days_normalizer import normalize


@pytest.fixture
def result(envelope):
    return normalize(envelope, query="prix panneaux solaires Belgique",
                     market="BE", language="fr")


def test_all_ten_source_states_are_preserved(result):
    states = {o.source_type: o.state for o in result.source_outcomes}
    assert states == {
        "web": SourceState.OK,
        "reddit": SourceState.PARTIAL,
        "youtube": SourceState.NO_RESULTS,
        "hackernews": SourceState.RATE_LIMITED,
        "x": SourceState.AUTH_FAILED,
        "github": SourceState.UNREACHABLE,
        "techmeme": SourceState.TIMEOUT,
        "arxiv": SourceState.SCHEMA_DRIFT,
        "polymarket": SourceState.SKIPPED_UNCONFIGURED,
        "stocktwits": SourceState.ERROR,
    }


def test_only_no_results_counts_as_clean_empty(result):
    """The central rule. Six sources produced nothing; only one did so cleanly."""
    clean = {o.source_type for o in result.clean_empty_sources}
    assert clean == {"youtube"}

    degraded = {o.source_type for o in result.degraded_sources}
    assert degraded == {"hackernews", "x", "github", "techmeme", "arxiv", "stocktwits"}

    unconfigured = {o.source_type for o in result.unconfigured_sources}
    assert unconfigured == {"polymarket"}


def test_degraded_sources_make_the_run_partial(result):
    assert result.is_partial is True
    assert result.status == "PARTIAL"


def test_unconfigured_source_is_not_a_failure(result):
    """Nobody asked polymarket for anything; it did not fail."""
    polymarket = next(o for o in result.source_outcomes if o.source_type == "polymarket")
    assert polymarket.state.was_attempted is False
    assert polymarket.state.is_degraded is False
    assert polymarket.state.is_clean_empty is False


def test_missing_published_at_stays_none(result):
    """l30d-005 omits published_at upstream. It must not be invented."""
    undated = next(s for s in result.sources if s.candidate_id == "l30d-005")
    assert undated.published_at is None


def test_undated_item_is_estimated_not_observed(envelope):
    """We saw it, but cannot place it in time — so it is not an observation.

    The fixture's undated item also carries an `unsupported` verdict, which is a
    stronger downgrade. This test isolates the date rule by removing the verdict,
    so a regression in either rule cannot hide behind the other.
    """
    envelope["report"]["freshness_verdicts"] = [
        v for v in envelope["report"]["freshness_verdicts"]
        if v["candidate_id"] != "l30d-005"
    ]
    result = normalize(envelope, query="q", market="BE", language="fr")
    fact = next(f for f in result.facts if f.source_ref == "l30d-005")
    assert fact.observability is Observability.ESTIMATED


def test_unsupported_verdict_overrides_the_date_rule(result):
    """`unsupported` outranks 'undated': the engine checked and found nothing."""
    fact = next(f for f in result.facts if f.source_ref == "l30d-005")
    assert fact.observability is Observability.UNKNOWN


def test_contradicted_claim_is_unknown(result):
    """The engine checked and could not stand it up. It may not be asserted."""
    fact = next(f for f in result.facts if f.source_ref == "l30d-004")
    assert fact.observability is Observability.UNKNOWN


def test_stale_claim_is_downgraded_to_estimated(result):
    fact = next(f for f in result.facts if f.source_ref == "l30d-003")
    assert fact.observability is Observability.ESTIMATED


def test_current_dated_claim_is_observed(result):
    fact = next(f for f in result.facts if f.source_ref == "l30d-001")
    assert fact.observability is Observability.OBSERVED


def test_freshness_verdicts_join_on_candidate_id(result):
    verdicts = {s.candidate_id: s.freshness_verdict for s in result.sources}
    assert verdicts["l30d-001"] is FreshnessVerdict.CURRENT
    assert verdicts["l30d-004"] is FreshnessVerdict.CONTRADICTED


def test_unresolved_data_names_every_unobservable_source(result):
    joined = " ".join(result.unresolved_data)
    for source in ("hackernews", "x", "github", "techmeme", "arxiv", "stocktwits"):
        assert source in joined
    assert "polymarket" in joined
    # The clean-empty source is NOT an unresolved gap — it answered.
    assert "youtube" not in joined


def test_engine_identity_is_carried_through(result):
    assert result.engine_commit == "52f53312ff2f272e16bbc1785e1c04f9d9c19b31"
    assert result.engine_version == "1.4.2"


def test_unknown_source_state_becomes_schema_drift(envelope):
    envelope["report"]["source_status"]["web"] = "invented-state"
    result = normalize(envelope, query="q", market="BE", language="fr")
    web = next(o for o in result.source_outcomes if o.source_type == "web")
    assert web.state is SourceState.SCHEMA_DRIFT
    # Critically: drift is not treated as a clean empty result.
    assert web.state.is_clean_empty is False


def test_unparseable_date_is_dropped_not_defaulted(envelope):
    envelope["report"]["results"][0]["published_at"] = "not-a-date"
    result = normalize(envelope, query="q", market="BE", language="fr")
    source = next(s for s in result.sources if s.candidate_id == "l30d-001")
    assert source.published_at is None


class TestContractVersioning:
    def test_missing_schema_version_is_rejected(self, envelope):
        del envelope["report"]["schema_version"]
        with pytest.raises(ResearchContractError):
            normalize(envelope, query="q", market="BE", language="fr")

    def test_different_major_is_rejected_and_not_retryable(self, envelope):
        envelope["report"]["schema_version"] = "2.0"
        with pytest.raises(ResearchContractError) as exc:
            normalize(envelope, query="q", market="BE", language="fr")
        assert exc.value.retryable is False

    def test_minor_below_minimum_is_rejected(self, envelope):
        envelope["report"]["schema_version"] = "1.1"
        with pytest.raises(ResearchContractError):
            normalize(envelope, query="q", market="BE", language="fr")

    def test_higher_minor_is_accepted(self, envelope):
        envelope["report"]["schema_version"] = "1.9"
        result = normalize(envelope, query="q", market="BE", language="fr")
        assert result.facts

    def test_unknown_fields_are_ignored(self, envelope):
        envelope["report"]["a_field_from_the_future"] = {"nested": True}
        envelope["report"]["results"][0]["new_field"] = 1
        result = normalize(envelope, query="q", market="BE", language="fr")
        assert result.facts

    def test_missing_report_is_rejected(self):
        with pytest.raises(ResearchContractError):
            normalize({"run_id": "x"}, query="q", market="BE", language="fr")
