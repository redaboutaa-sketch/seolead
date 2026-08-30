"""Phase 3.2 — authority registry, region scope, freshness, conflict, executor.

Every test maps to a rule the mission states. No network, no credentials.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import ClaimCategory, EvidenceStatus, ObservationStatus
from app.services.authority_registry import (AuthorityType, build_registry)
from app.services.authoritative_research import execute_plan
from app.services.claim_extraction import AtomicClaim
from app.services.conflict import ConflictKind, classify as classify_conflict
from app.services.evidence_model import EvidenceRef, evaluate_claim
from app.services.freshness import FreshnessStatus, assess
from app.services.provider_usage import UsageRecorder
from app.services.region import Region, detect_region, scope_is_compatible
from app.services.relevance import RelevanceStatus
from app.services.research_planner import plan_authoritative_research
from app.services.source_quality import SourceQuality
from app.schemas.research import (NormalizedSource, ResearchProviderResult,
                                  SourceOutcome)
from app.core.enums import SourceState

NOW = datetime.now(timezone.utc)


def _claim(text: str) -> AtomicClaim:
    return AtomicClaim(text=text, passage=text, source_ref="s1", offset=0)


def _ref(text: str, quality: SourceQuality, *, region: Region = Region.UNKNOWN,
         freshness: FreshnessStatus | None = None, published=None,
         source_ref: str = "s1", supports: bool = True,
         agrees: bool | None = None) -> EvidenceRef:
    return EvidenceRef(
        source_ref=source_ref, passage=text, url=f"https://{source_ref}.be/x",
        source_type="web", quality=quality, relevance=RelevanceStatus.RELEVANT,
        observation=(ObservationStatus.OBSERVED if published
                     else ObservationStatus.ESTIMATED),
        published_at=published, retrieved_at=NOW, provider="tavily",
        supports=supports, agrees_numerically=agrees, region=region,
        freshness_status=freshness)


# ─── Authority registry ──────────────────────────────────────────────────────

class TestAuthorityRegistry:
    def test_registry_is_built_from_configuration(self, solar_profile):
        registry = build_registry(solar_profile)
        assert len(registry.entries) >= 15
        assert "energie.wallonie.be" in registry.domains

    def test_each_domain_carries_authority_metadata(self, solar_profile):
        registry = build_registry(solar_profile)
        entry = registry.lookup("https://cwape.be/tarif-prosumer")
        assert entry is not None
        assert entry.authority_type is AuthorityType.REGULATOR
        assert entry.region is Region.BE_WAL
        assert ClaimCategory.GRID_RULE in entry.claim_categories

    def test_a_commercial_installer_is_never_official(self, solar_profile):
        registry = build_registry(solar_profile)
        assert registry.lookup("https://installateur-solaire.be/primes") is None
        assert registry.is_official("https://installateur-solaire.be/primes") is False

    def test_subdomains_match_their_registered_domain(self, solar_profile):
        registry = build_registry(solar_profile)
        assert registry.lookup("https://www.energie.wallonie.be/fr/prime.html")

    def test_categories_route_to_the_right_authorities(self, solar_profile):
        registry = build_registry(solar_profile)
        grid = {e.domain for e in registry.for_category(ClaimCategory.GRID_RULE)}
        tax = {e.domain for e in registry.for_category(ClaimCategory.TAX)}
        assert {"cwape.be", "vreg.be", "brugel.brussels"} <= grid
        assert "finances.belgium.be" in tax
        # The tax authority does not speak for grid rules.
        assert "finances.belgium.be" not in grid

    def test_region_filtering_narrows_authorities(self, solar_profile):
        registry = build_registry(solar_profile)
        walloon = {e.domain for e in registry.for_category(ClaimCategory.SUBSIDY,
                                                           region=Region.BE_WAL)}
        assert "energie.wallonie.be" in walloon
        assert "energiesparen.be" not in walloon      # Flemish agency

    def test_legacy_flat_domain_list_still_works(self, generic_profile):
        """A vertical not migrated to the richer shape keeps its authorities."""
        profile = generic_profile.model_copy(update={
            "official_source_policy": {"enabled": True,
                                       "domains": ["example.gov"]}})
        registry = build_registry(profile)
        assert registry.lookup("https://example.gov/page") is not None

    def test_authority_types_all_map_to_official(self):
        for authority_type in AuthorityType:
            if authority_type is AuthorityType.UNKNOWN:
                continue
            assert authority_type.source_quality is SourceQuality.OFFICIAL


# ─── Regional scope ──────────────────────────────────────────────────────────

class TestRegionalScope:
    @pytest.mark.parametrize("text,expected", [
        ("La prime en Wallonie s'élève à 1 750 €.", Region.BE_WAL),
        ("Prime à Bruxelles pour le photovoltaïque.", Region.BE_BRU),
        ("De premie in Vlaanderen bedraagt 300 euro.", Region.BE_VLG),
        ("Le prix moyen en Belgique est de 5 000 €.", Region.BE),
    ])
    def test_region_detection(self, text, expected):
        assert detect_region(text).region is expected

    def test_the_most_specific_region_wins(self):
        """A page naming both Belgium and Wallonia describes a Walloon rule."""
        assert detect_region(
            "En Belgique, la prime wallonne s'élève à 1 750 €.").region \
            is Region.BE_WAL

    def test_a_text_naming_several_regions_is_national_not_the_first_one(self):
        """The defect that emptied the evidence set for BE-wide claims.

        Detection returned whichever sub-region came first in the iteration
        order — always BE-WAL. A page comparing the three regional schemes is
        exactly the Belgium-wide source a Belgium-wide claim needs, and it was
        stamped Walloon, then rejected for "regional scope mismatch".
        """
        match = detect_region(
            "Comparatif des primes en Wallonie, à Bruxelles et en Flandre.")
        assert match.region is Region.BE
        # And the reason is legible: all three are named in the evidence.
        assert "wallonie" in match.evidence
        assert "bruxelles" in match.evidence
        assert "flandre" in match.evidence

    def test_two_regions_are_already_enough_to_be_national(self):
        assert detect_region(
            "La prime diffère entre la Wallonie et la Flandre.").region \
            is Region.BE

    def test_a_multi_region_source_can_now_support_a_belgian_claim(self):
        """The consequence, stated as the rule it restores."""
        evidence = detect_region(
            "En Wallonie comme en Flandre, le compteur ne tourne plus à "
            "l'envers.").region
        assert scope_is_compatible(evidence, Region.BE) is True

    def test_national_evidence_covers_a_regional_claim(self):
        assert scope_is_compatible(Region.BE, Region.BE_WAL) is True

    def test_regional_evidence_does_not_cover_a_national_claim(self):
        """The asymmetry that stops a Walloon premium becoming Belgian law."""
        assert scope_is_compatible(Region.BE_WAL, Region.BE) is False

    def test_one_region_does_not_cover_another(self):
        assert scope_is_compatible(Region.BE_WAL, Region.BE_VLG) is False
        assert scope_is_compatible(Region.BE_BRU, Region.BE_WAL) is False

    def test_a_walloon_source_cannot_support_a_belgium_wide_subsidy_claim(
            self, solar_profile):
        claim = _claim("En Belgique, la prime s'élève à 1 750 € pour tous.")
        evidence = [_ref("La prime wallonne s'élève à 1 750 €.",
                         SourceQuality.OFFICIAL, region=Region.BE_WAL,
                         published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.UNSUPPORTED
        assert "Regional scope mismatch" in result.reason

    def test_a_walloon_source_supports_a_walloon_claim(self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [_ref("La prime wallonne s'élève à 1 750 €.",
                         SourceQuality.OFFICIAL, region=Region.BE_WAL,
                         published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED

    def test_a_federal_source_supports_a_regional_claim(self, solar_profile):
        claim = _claim("En Wallonie, le taux de TVA est de 6% sur la rénovation.")
        evidence = [_ref("Le taux de TVA de 6% s'applique en Belgique.",
                         SourceQuality.OFFICIAL, region=Region.BE, published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED


# ─── Freshness ───────────────────────────────────────────────────────────────

class TestFreshness:
    def test_a_dated_page_is_dated_current(self):
        result = assess("Dernière mise à jour : 12 mars 2026. La prime est de "
                        "1 750 €.")
        assert result.status is FreshnessStatus.DATED_CURRENT
        assert result.status.can_support_current_claim

    def test_an_undated_page_presenting_as_in_force_is_distinguished(self):
        """The distinction the mission asks for: undated is not one bucket."""
        result = assess("La prime est actuellement en vigueur pour les "
                        "installations résidentielles.")
        assert result.status is FreshnessStatus.UNDATED_CURRENT
        assert result.status.can_support_current_claim
        assert result.status.is_dated is False

    def test_a_page_with_no_signal_is_plain_undated(self):
        result = assess("Les panneaux solaires convertissent la lumière.")
        assert result.status is FreshnessStatus.UNDATED
        assert result.status.can_support_current_claim is False

    def test_an_archived_page_is_historical(self):
        result = assess("Cette page est archivée. Le régime n'est plus en "
                        "vigueur depuis 2023.")
        assert result.status is FreshnessStatus.HISTORICAL
        assert result.status.can_support_current_claim is False

    def test_an_expired_validity_period_is_detected(self):
        result = assess("Cette prime est valable jusqu'au 31 décembre 2023.")
        assert result.status is FreshnessStatus.DATED_EXPIRED
        assert result.effective_until is not None

    def test_effective_dates_are_preserved_verbatim(self):
        result = assess("Applicable à partir du 1 janvier 2026 jusqu'au "
                        "31 décembre 2027.")
        assert result.effective_from
        assert result.effective_until

    def test_no_date_is_ever_invented(self):
        result = assess("Un texte sans aucune date.")
        assert result.published_at is None
        assert result.updated_at is None
        assert result.effective_from is None

    def test_a_historical_page_cannot_support_a_current_claim(self,
                                                               solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 € en 2026.")
        evidence = [_ref("La prime wallonne était de 1 750 €.",
                         SourceQuality.OFFICIAL, region=Region.BE_WAL,
                         freshness=FreshnessStatus.HISTORICAL)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.PARTIALLY_SUPPORTED
        assert "HISTORICAL" in result.reason

    def test_an_undated_but_current_official_page_supports_a_high_risk_claim(
            self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [_ref("La prime wallonne s'élève actuellement à 1 750 €.",
                         SourceQuality.OFFICIAL, region=Region.BE_WAL,
                         freshness=FreshnessStatus.UNDATED_CURRENT)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED


# ─── Conflict refinement ─────────────────────────────────────────────────────

class TestConflictRefinement:
    def test_different_regions_are_not_a_true_conflict(self):
        assessment = classify_conflict(
            "La prime en Wallonie s'élève à 1 750 €.",
            "La prime à Bruxelles s'élève à 3 000 €.")
        assert assessment.kind is ConflictKind.REGIONAL_DIFFERENCE
        assert assessment.blocks is False

    def test_different_years_are_not_a_true_conflict(self):
        assessment = classify_conflict(
            "En 2026, le prix moyen est de 5 000 €.",
            "En 2021, le prix moyen était de 8 000 €.")
        assert assessment.kind is ConflictKind.TIME_DIFFERENCE
        assert assessment.blocks is False

    def test_different_units_are_a_scope_difference(self):
        assessment = classify_conflict(
            "Le prix est de 1,5 € par watt-crête.",
            "Le prix total est de 5 000 € au total.")
        assert assessment.kind is ConflictKind.SCOPE_DIFFERENCE
        assert assessment.blocks is False

    def test_a_genuine_disagreement_still_blocks(self):
        assessment = classify_conflict(
            "Le prix moyen en Belgique est de 5 000 €.",
            "Le prix moyen en Belgique est de 9 000 €.")
        assert assessment.kind is ConflictKind.TRUE_CONFLICT
        assert assessment.blocks is True

    def test_detection_is_not_weakened_only_classified(self, solar_profile):
        """Everything previously flagged is still flagged, now with a reason."""
        claim = _claim("Le prix moyen en Belgique est de 5 000 €.")
        evidence = [
            _ref("Le prix moyen en Belgique est de 5 000 €.",
                 SourceQuality.SPECIALIST, region=Region.BE, source_ref="a"),
            _ref("Le prix moyen en Belgique est de 9 000 €.",
                 SourceQuality.SPECIALIST, region=Region.BE, source_ref="b",
                 supports=False, agrees=False),
        ]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.CONFLICTING
        assert result.conflict_kind is ConflictKind.TRUE_CONFLICT

    def test_a_regional_difference_does_not_block_the_claim(self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [
            _ref("La prime wallonne s'élève à 1 750 €.", SourceQuality.OFFICIAL,
                 region=Region.BE_WAL, published=NOW, source_ref="wal"),
            _ref("La prime bruxelloise s'élève à 3 000 €.",
                 SourceQuality.OFFICIAL, region=Region.BE_BRU, published=NOW,
                 source_ref="bru", supports=False, agrees=False),
        ]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is not EvidenceStatus.CONFLICTING
        kinds = {c["kind"] for c in result.as_dict()["conflicts"]}
        assert ConflictKind.REGIONAL_DIFFERENCE.value in kinds


# ─── Authority requirement is never relaxed ──────────────────────────────────

class TestAuthorityEnforcement:
    def test_commercial_evidence_cannot_override_an_official_requirement(
            self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [_ref("La prime s'élève à 1 750 €.", SourceQuality.COMMERCIAL,
                         region=Region.BE_WAL, published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.UNSUPPORTED
        assert "OFFICIAL" in result.reason

    def test_an_official_source_satisfies_the_requirement(self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [_ref("La prime wallonne s'élève à 1 750 €.",
                         SourceQuality.OFFICIAL, region=Region.BE_WAL,
                         published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED

    def test_many_commercial_sources_do_not_add_up_to_an_official_one(
            self, solar_profile):
        claim = _claim("En Wallonie, la prime s'élève à 1 750 €.")
        evidence = [_ref("La prime s'élève à 1 750 €.", SourceQuality.COMMERCIAL,
                         region=Region.BE_WAL, published=NOW,
                         source_ref=f"c{i}") for i in range(5)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.UNSUPPORTED


# ─── Executor ────────────────────────────────────────────────────────────────

class StubWeb:
    """Returns whatever it is given, recording the restriction it was asked for."""

    code = "tavily"

    def __init__(self, sources: list[NormalizedSource]):
        self._sources = sources
        self.restricted_calls: list[list[str]] = []
        self._usage = None

    async def research_restricted(self, *, query, market, language,
                                  correlation_id, include_domains):
        self.restricted_calls.append(include_domains)
        return ResearchProviderResult(
            provider="tavily", query=query, market=market, language=language,
            status="SUCCEEDED", sources=self._sources, facts=[],
            source_outcomes=[SourceOutcome(source_type="web",
                                           state=SourceState.OK,
                                           item_count=len(self._sources))])


def _source(url: str, title: str, summary: str, ref: str) -> NormalizedSource:
    return NormalizedSource(source_type="web", state=SourceState.OK, url=url,
                            title=title, summary=summary, retrieved_at=NOW,
                            candidate_id=ref)


class TestExecutor:
    async def _run(self, profile, sources):
        registry = build_registry(profile)
        claim = _claim("La prime régionale s'élève à 1 750 € en Wallonie.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL,
                         region=Region.BE_WAL, published=NOW)], profile)]
        plan = plan_authoritative_research(topic="prix panneaux solaires",
                                           market="BE", unresolved=unresolved,
                                           profile=profile)
        provider = StubWeb(sources)
        usage = UsageRecorder()
        run = await execute_plan(plan, profile=profile, registry=registry,
                                 web_provider=provider, market="BE",
                                 language="fr", correlation_id="t", usage=usage)
        return run, provider

    async def test_official_pages_are_accepted(self, solar_profile):
        run, _ = await self._run(solar_profile, [_source(
            "https://energie.wallonie.be/fr/prime.html",
            "Prime photovoltaïque", "La prime est actuellement de 1 750 €.",
            "o1")])
        # A category may carry regional query variants, so the same stub source
        # can be returned by more than one query. Assert on distinct pages.
        assert {a.source.url for a in run.accepted} == {
            "https://energie.wallonie.be/fr/prime.html"}
        assert all(a.entry.authority_type is AuthorityType.GOVERNMENT
                   for a in run.accepted)
        assert all(a.region is Region.BE_WAL for a in run.accepted)

    async def test_off_domain_pages_are_rejected_even_in_the_official_pass(
            self, solar_profile):
        """Second enforcement: a provider ignoring the restriction cannot smuggle
        a commercial page into the authoritative evidence set."""
        run, _ = await self._run(solar_profile, [_source(
            "https://installateur-solaire.be/primes", "Primes",
            "La prime est de 1 750 €.", "c1")])
        assert run.accepted == []
        assert run.rejected
        assert "not on a configured official domain" in run.rejected[0]["reason"]

    async def test_the_provider_is_asked_to_restrict_domains(self, solar_profile):
        _, provider = await self._run(solar_profile, [])
        assert provider.restricted_calls
        assert "energie.wallonie.be" in provider.restricted_calls[0]

    async def test_an_authority_outside_its_category_is_rejected(self,
                                                                  solar_profile):
        """Finances.belgium.be is a tax authority, not a subsidy authority."""
        run, _ = await self._run(solar_profile, [_source(
            "https://finances.belgium.be/page", "TVA",
            "Le taux de TVA est de 6%.", "t1")])
        assert run.accepted == []
        assert any("not configured as an authority" in r["reason"]
                   for r in run.rejected)

    async def test_results_fold_into_the_standard_provider_shape(self,
                                                                  solar_profile):
        run, _ = await self._run(solar_profile, [_source(
            "https://energie.wallonie.be/fr/prime.html", "Prime",
            "La prime est actuellement de 1 750 €.", "o1")])
        result = run.to_provider_result(query="q", market="BE", language="fr")
        assert result.provider == "tavily_authoritative"
        assert {s.url for s in result.sources} == {
            "https://energie.wallonie.be/fr/prime.html"}

    async def test_an_empty_run_says_so_rather_than_failing(self, solar_profile):
        run, _ = await self._run(solar_profile, [])
        result = run.to_provider_result(query="q", market="BE", language="fr")
        assert result.status == "PARTIAL"
        assert any("no page on a configured official domain" in u
                   for u in result.unresolved_data)


class TestFreshnessRegression:
    """A validity period is not an archival marker.

    The first implementation listed "jusqu'au 31 decembre" as a historical
    marker, which would have flagged a scheme valid until 31 December 2027 as
    archived. Expiry is decided by comparing the stated end year.
    """

    def test_a_future_validity_period_is_not_historical(self):
        future = datetime.now(timezone.utc).year + 1
        result = assess(f"Cette prime est valable jusqu'au 31 décembre {future}.")
        assert result.status is not FreshnessStatus.HISTORICAL
        assert result.status is not FreshnessStatus.DATED_EXPIRED

    def test_a_past_validity_period_is_expired(self):
        result = assess("Cette prime est valable jusqu'au 31 décembre 2019.")
        assert result.status is FreshnessStatus.DATED_EXPIRED
        assert result.status.can_support_current_claim is False

    def test_an_explicit_archival_marker_is_still_historical(self):
        result = assess("Cette page est archivée et n'est plus en vigueur.")
        assert result.status is FreshnessStatus.HISTORICAL


class TestAuthorityRegionPrecedence:
    """Live run, 2026-08-12 (Phase 3.2).

    Page-text region detection overrode the authority's own jurisdiction, so
    `energie.wallonie.be` was tagged BE-BRU because one of its pages referenced
    Brussels. That would let the Walloon energy portal establish a Brussels rule —
    exactly the over-generalisation regional scoping exists to prevent.
    """

    async def test_a_walloon_authority_stays_walloon(self, solar_profile):
        registry = build_registry(solar_profile)
        claim = _claim("La prime régionale s'élève à 1 750 € en Wallonie.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL,
                         region=Region.BE_WAL, published=NOW)], solar_profile)]
        plan = plan_authoritative_research(topic="prime", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        # A Walloon page that talks about Brussels for comparison.
        provider = StubWeb([_source(
            "https://energie.wallonie.be/fr/comparaison.html",
            "Comparaison des primes",
            "En Wallonie la prime est de 1 750 €, contre 3 000 € à Bruxelles.",
            "o1")])
        run = await execute_plan(plan, profile=solar_profile, registry=registry,
                                 web_provider=provider, market="BE",
                                 language="fr", correlation_id="t")
        assert run.accepted
        assert run.accepted[0].region is Region.BE_WAL

    async def test_a_brussels_authority_stays_brussels(self, solar_profile):
        registry = build_registry(solar_profile)
        claim = _claim("La prime régionale s'élève à 3 000 € à Bruxelles.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL,
                         region=Region.BE_BRU, published=NOW)], solar_profile)]
        plan = plan_authoritative_research(topic="prime", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        provider = StubWeb([_source(
            "https://environnement.brussels/etude.html", "Étude régionale",
            "Une étude comparant la Wallonie et la Flandre sur le photovoltaïque.",
            "o1")])
        run = await execute_plan(plan, profile=solar_profile, registry=registry,
                                 web_provider=provider, market="BE",
                                 language="fr", correlation_id="t")
        assert run.accepted
        assert run.accepted[0].region is Region.BE_BRU

    def test_an_unregistered_source_still_uses_text_detection(self):
        """Only registered authorities have a jurisdiction to defer to."""
        assert detect_region(
            "La prime wallonne s'élève à 1 750 €.").region is Region.BE_WAL


class TestRegionalQueryVariants:
    """Phase 3.2 found no Flemish authority at all.

    A single tri-regional French query does not reach `energiesparen.be`, which
    publishes in Dutch — so BE-VLG claims had no official evidence and never could.
    """

    def test_a_regional_variant_is_planned_alongside_the_national_query(
            self, solar_profile):
        claim = _claim("La prime régionale s'élève à 1 750 €.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL, published=NOW)],
            solar_profile)]
        plan = plan_authoritative_research(topic="prime", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        queries = [q.query for q in plan.queries]
        assert any("Vlaanderen" in q for q in queries), queries
        assert any("Wallonie" in q for q in queries), queries

    def test_the_variant_keeps_the_category(self, solar_profile):
        claim = _claim("La prime régionale s'élève à 1 750 €.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL, published=NOW)],
            solar_profile)]
        plan = plan_authoritative_research(topic="prime", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        flemish = [q for q in plan.queries if "Vlaanderen" in q.query]
        assert flemish and flemish[0].category is ClaimCategory.SUBSIDY

    def test_variants_respect_the_ceiling(self, solar_profile):
        claim = _claim("La prime régionale s'élève à 1 750 €.")
        unresolved = [evaluate_claim(
            claim, [_ref(claim.text, SourceQuality.COMMERCIAL, published=NOW)],
            solar_profile)]
        plan = plan_authoritative_research(topic="prime", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        assert len(plan.queries) <= solar_profile.official_source_policy["max_queries"]
