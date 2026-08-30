"""The registry is a trust gate, so entering it is a decision, not an edit.

An entry lets a domain establish HIGH-risk claims — subsidies, grid rules,
profitability. Who belongs in it is for the person answerable for what the site
publishes. A candidate is carried in configuration, described, and probeable,
and it is absent from every registry the pipeline consults until that person
removes the flag.
"""
from __future__ import annotations

import pytest

from app.core.enums import ClaimCategory
from app.services.authority_probe import (date_forensics, domains_for,
                                          host_of, summarize)
from app.services.authority_registry import build_registry
from app.services.region import Region
from app.schemas.research import NormalizedSource
from app.core.enums import SourceState
from app.verticals.profile import load_profile

PENDING = {"plan.be", "statbel.fgov.be"}


@pytest.fixture
def profile():
    return load_profile("SOLAR_BE")


class TestPendingEntriesAreInert:
    def test_the_pipeline_registry_excludes_them(self, profile):
        active = build_registry(profile)
        assert not [e for e in active.entries if e.pending_ratification]
        assert PENDING.isdisjoint(set(active.domains))

    def test_the_probe_registry_includes_them(self, profile):
        probed = build_registry(profile, include_pending=True)
        assert PENDING.issubset(set(probed.domains))

    def test_they_are_never_queried_by_the_authoritative_pass(self, profile):
        """`for_category` on the active registry is what the pass restricts to."""
        active = build_registry(profile)
        for category in ClaimCategory:
            domains = {e.domain for e in active.for_category(category)}
            assert PENDING.isdisjoint(domains), category.value

    def test_a_pending_domain_cannot_make_a_page_official(self, profile):
        """The registry lookup is what promotes a page to OFFICIAL."""
        active = build_registry(profile)
        assert active.lookup("https://plan.be/publications/energy") is None

    def test_ratifying_is_removing_one_flag(self, profile):
        """The act is explicit and its effect is exactly one entry."""
        probed = build_registry(profile, include_pending=True)
        candidate = next(e for e in probed.entries if e.domain == "plan.be")
        assert candidate.pending_ratification is True
        assert candidate.region is Region.BE
        assert ClaimCategory.ROI in candidate.claim_categories


class TestWhyTheCandidatesExist:
    def test_a_belgium_wide_roi_claim_is_unsatisfiable_today(self, profile):
        """The measurement that motivated the proposal, pinned.

        ROI requires 2 corroborating sources and the region rule refuses a
        Walloon source for a Belgium-wide claim. One registered domain covers
        BE, so the claim fails on arithmetic, whatever the pages say.
        """
        active = build_registry(profile)
        covering_be = [e for e in active.for_category(ClaimCategory.ROI)
                       if e.region is Region.BE or e.region is Region.UNKNOWN]
        assert len(covering_be) == 1
        assert covering_be[0].domain == "apere.org"

    def test_ratification_would_make_it_arithmetically_possible(self, profile):
        """Not that it would succeed — that it would stop being impossible."""
        probed = build_registry(profile, include_pending=True)
        covering_be = [e for e in probed.for_category(ClaimCategory.ROI)
                       if e.region is Region.BE or e.region is Region.UNKNOWN]
        assert len(covering_be) >= 2


def _source(*, title="t", summary="s", published_at=None):
    return NormalizedSource(source_type="official", state=SourceState.OK,
                            url="https://example.be/p", title=title,
                            summary=summary, published_at=published_at)


class TestDateForensics:
    def test_it_reports_each_location_separately(self):
        """Collapsing them would lose the finding: which one is ever populated."""
        dates = date_forensics(_source(
            summary="Publié le 17 avril 2025. Valable jusqu'au 31/12/2027."))
        assert dates["provider_published_at"] is None
        assert "fr_long" in dates["dates_in_text"]
        assert "numeric" in dates["dates_in_text"]
        assert dates["any_date_in_text"] is True

    def test_a_page_with_no_date_says_so(self):
        dates = date_forensics(_source(summary="Les panneaux produisent."))
        assert dates["any_date_in_text"] is False
        assert dates["dates_in_text"] == {}

    def test_dates_are_reported_as_written_not_parsed(self):
        """Parsing "31 december 2029" here would hide the ambiguity measured."""
        dates = date_forensics(_source(summary="Geldig tot 31 december 2029."))
        assert dates["dates_in_text"]["nl_long"] == ["31 december 2029"]

    def test_the_summary_counts_what_decides_the_mechanism(self):
        rows = [
            {"host": "a.be", "in_registry": True, "dates": date_forensics(
                _source(summary="Mis à jour le 2025-01-05."))},
            {"host": "b.be", "in_registry": True, "dates": date_forensics(
                _source(summary="Aucune date ici."))},
        ]
        counts = summarize(rows)
        assert counts["sources"] == 2
        assert counts["with_provider_date"] == 0
        assert counts["with_date_in_text"] == 1
        assert counts["by_text_date_kind"]["iso"] == 1
        assert counts["by_host"] == {"a.be": 1, "b.be": 1}


class TestAnUnregisteredHostIsCountedNotFatal:
    """The crash of 2026-08-30, which threw away a paid provider call.

    `--domain plan.be` without `--include-pending` names a domain the registry
    does not carry, so the lookup returns None. Grouping the report on the
    registry entry then ran `sorted({None, "apere.org"})` and raised — losing
    the seven sources the probe had just paid for, and the answer with them.

    The probe exists to examine domains the registry does NOT trust yet. A
    report that cannot describe one is useless exactly where it is needed.
    """

    def _row(self, url, *, in_registry):
        return {"host": host_of(url), "in_registry": in_registry,
                "dates": date_forensics(_source())}

    def test_a_mix_of_registered_and_unregistered_hosts_summarizes(self):
        counts = summarize([
            self._row("https://www.apere.org/etude", in_registry=True),
            self._row("https://www.plan.be/publication", in_registry=False),
        ])
        assert counts["by_host"] == {"www.apere.org": 1, "www.plan.be": 1}
        assert counts["unregistered_hosts"] == ["www.plan.be"]

    def test_every_host_is_named_even_with_no_url(self):
        """A source with no url is a real provider outcome, not a crash."""
        counts = summarize([self._row(None, in_registry=False)])
        assert counts["sources"] == 1
        assert list(counts["by_host"]) == ["(sans url)"]

    @pytest.mark.parametrize("url,expected", [
        ("https://WWW.Plan.BE/x", "www.plan.be"),
        ("https://energie.wallonie.be/a/b.html", "energie.wallonie.be"),
        (None, "(sans url)"),
        ("", "(sans url)"),
    ])
    def test_the_host_is_read_from_the_url_and_normalised(self, url, expected):
        assert host_of(url) == expected


class TestProbeTargeting:
    def test_explicit_domains_override_the_category(self, profile):
        registry = build_registry(profile, include_pending=True)
        assert domains_for(registry, ClaimCategory.ROI,
                           explicit=["creg.be"]) == ["creg.be"]

    def test_without_an_override_it_uses_the_category(self, profile):
        registry = build_registry(profile, include_pending=True)
        domains = domains_for(registry, ClaimCategory.ROI)
        assert "apere.org" in domains
        assert "plan.be" in domains
