"""Phase 3.1 evidence model — passages, atomic claims, authority, support.

Every test here corresponds to a defect the Phase 3 live run exposed, or to a
property the new model must guarantee.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums import (AuthorityRequirement, ClaimCategory, EvidenceStatus,
                            FreshnessRequirement, ObservationStatus)
from app.services.claim_extraction import extract_claim_set, extract_claims
from app.services.claim_policy import (ClaimRisk, authority_is_sufficient,
                                       classify_category, requirements_for)
from app.services.evidence_model import (EvidenceRef, build_candidates,
                                         evaluate_claim, passage_supports_claim,
                                         summarize, unresolved_high_risk)
from app.services.passage_extraction import Passage, extract_passages
from app.services.relevance import RelevanceStatus
from app.services.research_planner import plan_authoritative_research
from app.services.source_quality import SourceQuality

# The real shape of a Tavily excerpt, from the live run of 2026-08-12.
LIVE_EXCERPT = """Aller au contenu

Energy Village

# Prix Panneaux Solaires 2026 en Belgique : Coûts par kWc, m² & Devis

Le prix des panneaux solaires en Belgique en 2026 varie entre 1,1 € et 1,8 € par
Watt-crête installé. Une installation résidentielle de 5 kWc représente donc un
investissement d'environ 5 000 €. La prime régionale s'élève à 1 750 € en Wallonie.

La boutique ne fonctionnera pas correctement dans le cas où les cookies sont
désactivés.

ChatGPTClaudePerplexityGoogle AI Mode

Le rendement d'un panneau dépend de son orientation et de son inclinaison.
"""

NOW = datetime.now(timezone.utc)


def _ref(source_ref: str, passage: str, quality: SourceQuality, *,
         supports: bool = True, agrees: bool | None = None,
         published: datetime | None = None,
         relevance: RelevanceStatus = RelevanceStatus.RELEVANT) -> EvidenceRef:
    return EvidenceRef(
        source_ref=source_ref, passage=passage, url=f"https://{source_ref}.be/x",
        source_type="web", quality=quality, relevance=relevance,
        observation=(ObservationStatus.OBSERVED if published
                     else ObservationStatus.ESTIMATED),
        published_at=published, retrieved_at=NOW, provider="tavily",
        supports=supports, agrees_numerically=agrees)


def _claim(text: str, source_ref: str = "s1"):
    from app.services.claim_extraction import AtomicClaim
    return AtomicClaim(text=text, passage=text, source_ref=source_ref, offset=0)


# ─── Passage extraction ──────────────────────────────────────────────────────

class TestPassageExtraction:
    def test_cookie_banner_does_not_survive(self, solar_profile):
        result = extract_passages(LIVE_EXCERPT, source_ref="s1")
        kept = " ".join(p.text for p in result.passages).lower()
        assert "boutique ne fonctionnera pas" not in kept

    def test_navigation_does_not_survive(self):
        result = extract_passages(LIVE_EXCERPT, source_ref="s1")
        kept = " ".join(p.text for p in result.passages).lower()
        assert "aller au contenu" not in kept

    def test_ai_tool_menu_does_not_survive(self):
        result = extract_passages(LIVE_EXCERPT, source_ref="s1")
        kept = " ".join(p.text for p in result.passages).lower()
        assert "perplexity" not in kept

    def test_substantive_text_survives(self):
        result = extract_passages(LIVE_EXCERPT, source_ref="s1")
        kept = " ".join(p.text for p in result.passages).lower()
        assert "watt-crête" in kept or "watt-crete" in kept
        assert "orientation" in kept

    def test_price_tile_is_dropped_as_low_alpha(self):
        """The live Luminus source was a spec tile: '4.400 € 625 €/an 7 ans'."""
        tile = "Prix des panneaux\n\n4.400 €\n\nÉconomies\n\n625 €/an\n\n7 ans\n\n5 kWh"
        result = extract_passages(tile, source_ref="s2")
        assert result.passages == [] or all(
            "4.400" not in p.text for p in result.passages)

    def test_drop_reasons_are_recorded(self):
        result = extract_passages(LIVE_EXCERPT, source_ref="s1")
        assert result.dropped
        assert all(p.drop_reason for p in result.dropped)
        assert result.summary()["dropped"] > 0

    def test_empty_input_is_safe(self):
        assert extract_passages("", source_ref="s1").passages == []

    def test_long_substantive_block_is_kept_not_dropped(self):
        """Conservative by design: ambiguity keeps the text."""
        block = ("Le prix d'une installation dépend de la puissance installée, du "
                 "type de toiture et de la complexité de la pose. " * 3)
        result = extract_passages(block, source_ref="s1")
        assert result.passages


# ─── Atomic claim extraction ─────────────────────────────────────────────────

class TestClaimExtraction:
    def test_a_2kb_excerpt_becomes_multiple_atomic_claims(self):
        """The Phase 3 defect: one excerpt was one 'fact'."""
        passages = extract_passages(LIVE_EXCERPT, source_ref="s1").passages
        claims = extract_claim_set(passages)
        assert len(claims.claims) >= 2, claims.summary()

    def test_price_and_subsidy_do_not_share_a_claim(self):
        """A paragraph mixing pricing and a subsidy must not be one proposition."""
        passages = extract_passages(LIVE_EXCERPT, source_ref="s1").passages
        claims = extract_claim_set(passages)
        texts = [c.text.lower() for c in claims.claims]
        mixed = [t for t in texts if "prime" in t and "watt-crête" in t]
        assert not mixed, f"price and subsidy merged into one claim: {mixed}"

    def test_cookie_text_never_becomes_a_claim(self):
        passages = extract_passages(LIVE_EXCERPT, source_ref="s1").passages
        claims = extract_claim_set(passages)
        assert all("cookie" not in c.text.lower() for c in claims.claims)

    def test_call_to_action_is_not_a_claim(self):
        passage = Passage(
            text=("Vous souhaitez bénéficier d'une estimation personnalisée pour "
                  "vos travaux d'installation en Belgique ?"),
            offset=0, source_ref="s1")
        assert extract_claims(passage) == []

    def test_question_is_not_a_claim(self):
        passage = Passage(text="Quel est le prix des panneaux solaires en 2026 ?",
                          offset=0, source_ref="s1")
        assert extract_claims(passage) == []

    def test_quantified_claims_are_flagged(self):
        passages = extract_passages(LIVE_EXCERPT, source_ref="s1").passages
        claims = extract_claim_set(passages)
        assert any(c.quantified for c in claims.claims)

    def test_each_claim_keeps_its_passage_and_source(self):
        passages = extract_passages(LIVE_EXCERPT, source_ref="s1").passages
        for claim in extract_claim_set(passages).claims:
            assert claim.source_ref == "s1"
            assert claim.passage
            assert claim.extraction_method == "deterministic_v1"

    def test_repeated_sentences_are_deduplicated(self):
        """Counting a repeated sentence twice would fake corroboration."""
        text = "Le prix dépend de la puissance installée et de la toiture."
        passages = [Passage(text=text, offset=0, source_ref="s1"),
                    Passage(text=text, offset=1, source_ref="s1")]
        result = extract_claim_set(passages)
        assert len(result.claims) == 1
        assert result.skipped == 1


# ─── Category, authority, freshness ──────────────────────────────────────────

class TestClaimPolicy:
    @pytest.mark.parametrize("claim,expected", [
        ("La prime régionale s'élève à 1 750 € en Wallonie.", ClaimCategory.SUBSIDY),
        ("Le taux de TVA applicable est de 6%.", ClaimCategory.TAX),
        ("Le tarif prosumer est facturé par le gestionnaire de réseau.",
         ClaimCategory.GRID_RULE),
        ("L'installation est obligatoire selon la réglementation.",
         ClaimCategory.REGULATION),
        ("Le retour sur investissement est de 7 ans.", ClaimCategory.ROI),
        ("Le rendement est garanti pendant 25 ans.",
         ClaimCategory.GUARANTEED_SAVINGS),
    ])
    def test_categories_are_matched_from_vertical_vocabulary(self, claim, expected,
                                                              solar_profile):
        assert classify_category(claim, solar_profile) is expected

    def test_market_average_and_vendor_price_are_different_categories(self,
                                                                       solar_profile):
        market = classify_category(
            "Le prix moyen d'une installation est de 5 000 € en Belgique.",
            solar_profile)
        vendor = classify_category(
            "Nos tarifs pour une installation de 5 kWc sont de 4 400 €.",
            solar_profile)
        assert market is ClaimCategory.MARKET_PRICE
        assert vendor is ClaimCategory.VENDOR_PRICE

    def test_subsidy_requires_official_and_a_date(self, solar_profile):
        requirements = requirements_for("La prime s'élève à 1 750 €.", solar_profile)
        assert requirements.risk == ClaimRisk.HIGH
        assert requirements.authority is AuthorityRequirement.OFFICIAL
        assert requirements.freshness is FreshnessRequirement.REQUIRED

    def test_vendor_price_needs_no_authority_and_no_date(self, solar_profile):
        requirements = requirements_for("Nos tarifs sont de 4 400 €.", solar_profile)
        assert requirements.authority is AuthorityRequirement.ANY
        assert requirements.freshness is not FreshnessRequirement.REQUIRED

    def test_market_price_requires_corroboration(self, solar_profile):
        requirements = requirements_for(
            "Le prix moyen est de 5 000 € en Belgique.", solar_profile)
        assert requirements.min_corroborating_sources >= 3

    def test_timeless_explanation_requires_nothing_special(self, solar_profile):
        requirements = requirements_for(
            "Les panneaux sont généralement orientés vers le sud.", solar_profile)
        assert requirements.risk == ClaimRisk.LOW
        assert requirements.freshness is FreshnessRequirement.NOT_REQUIRED

    def test_commercial_source_cannot_satisfy_official_requirement(self):
        assert not authority_is_sufficient(AuthorityRequirement.OFFICIAL,
                                           SourceQuality.COMMERCIAL)
        assert not authority_is_sufficient(AuthorityRequirement.OFFICIAL,
                                           SourceQuality.SPECIALIST)
        assert authority_is_sufficient(AuthorityRequirement.OFFICIAL,
                                       SourceQuality.OFFICIAL)

    def test_policy_is_per_vertical(self, solar_profile, generic_profile):
        """The generic vertical does not know what a Belgian premium is."""
        assert classify_category("La prime s'élève à 1 750 €.",
                                 solar_profile) is ClaimCategory.SUBSIDY
        generic = requirements_for("A statutory requirement applies.",
                                   generic_profile)
        assert generic.category is ClaimCategory.REGULATION


# ─── Support classification ──────────────────────────────────────────────────

class TestSupportClassification:
    def test_missing_date_does_not_invalidate_a_timeless_claim(self, solar_profile):
        """The Phase 3 defect, stated directly.

        Tavily returns no dates. A timeless explanatory claim from an undated
        specialist source must still be SUPPORTED, or the web-research path
        produces nothing for any query.
        """
        claim = _claim("Les panneaux sont généralement orientés vers le sud pour "
                       "maximiser la production.")
        evidence = [_ref("s1", claim.text, SourceQuality.SPECIALIST,
                         published=None)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED
        assert result.has_dated_support is False

    def test_subsidy_claim_from_a_commercial_source_is_unsupported(self,
                                                                    solar_profile):
        claim = _claim("La prime régionale s'élève à 1 750 € en Wallonie.")
        evidence = [_ref("s1", claim.text, SourceQuality.COMMERCIAL,
                         published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.UNSUPPORTED
        assert "OFFICIAL" in result.reason

    def test_subsidy_claim_from_an_official_dated_source_is_supported(self,
                                                                       solar_profile):
        claim = _claim("La prime régionale s'élève à 1 750 € en Wallonie.")
        evidence = [_ref("official", claim.text, SourceQuality.OFFICIAL,
                         published=NOW)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED

    def test_subsidy_from_an_official_but_undated_source_is_partial(self,
                                                                     solar_profile):
        """Freshness binds where the category says it does — and only there."""
        claim = _claim("La prime régionale s'élève à 1 750 € en Wallonie.")
        evidence = [_ref("official", claim.text, SourceQuality.OFFICIAL,
                         published=None)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.PARTIALLY_SUPPORTED
        assert "no supporting source carries a date" in result.reason

    def test_vendor_price_supports_its_own_price(self, solar_profile):
        claim = _claim("Nos tarifs pour une installation de 5 kWc sont de 4 400 €.")
        evidence = [_ref("vendor", claim.text, SourceQuality.COMMERCIAL,
                         published=None)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED

    def test_a_single_commercial_source_cannot_establish_a_market_average(
            self, solar_profile):
        claim = _claim("Le prix moyen d'une installation est de 5 000 € en Belgique.")
        evidence = [_ref("vendor", claim.text, SourceQuality.COMMERCIAL,
                         published=None)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is not EvidenceStatus.SUPPORTED

    def test_three_specialist_sources_can_establish_a_market_average(self,
                                                                      solar_profile):
        claim = _claim("Le prix moyen d'une installation est de 5 000 € en Belgique.")
        evidence = [_ref(f"s{i}", claim.text, SourceQuality.SPECIALIST)
                    for i in range(3)]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.SUPPORTED
        assert result.corroborating_sources == 3

    def test_conflicting_figures_are_detected(self, solar_profile):
        claim = _claim("Une installation coûte environ 5 000 € en Belgique.")
        evidence = [
            _ref("a", "Une installation coûte environ 5 000 € en Belgique.",
                 SourceQuality.SPECIALIST, supports=True, agrees=True),
            _ref("b", "Une installation coûte environ 9 000 € en Belgique.",
                 SourceQuality.SPECIALIST, supports=False, agrees=False),
        ]
        result = evaluate_claim(claim, evidence, solar_profile)
        assert result.status is EvidenceStatus.CONFLICTING

    def test_no_evidence_is_unsupported(self, solar_profile):
        result = evaluate_claim(_claim("Une affirmation quelconque sur le sujet."),
                                [], solar_profile)
        assert result.status is EvidenceStatus.UNSUPPORTED

    def test_observation_and_evidence_status_are_independent(self, solar_profile):
        """The central Phase 3.1 separation."""
        claim = _claim("Les panneaux sont orientés vers le sud généralement.")
        undated = evaluate_claim(
            claim, [_ref("s1", claim.text, SourceQuality.SPECIALIST)],
            solar_profile)
        assert undated.evidence[0].observation is ObservationStatus.ESTIMATED
        assert undated.status is EvidenceStatus.SUPPORTED


# ─── Claim ↔ source cardinality ──────────────────────────────────────────────

class TestCardinality:
    def test_one_source_can_support_multiple_claims(self, solar_profile):
        sources = {"s1": {"url": "https://x.be/a", "source_quality": "SPECIALIST",
                          "relevance_status": "RELEVANT", "source_type": "web",
                          "observation_status": "ESTIMATED", "provider": "tavily"}}
        passages = {"s1": [
            "Le prix dépend de la puissance installée et du type de toiture.",
            "Le rendement dépend de l'orientation et de l'inclinaison du toit.",
        ]}
        first = build_candidates(
            _claim("Le prix dépend de la puissance installée."), sources, passages)
        second = build_candidates(
            _claim("Le rendement dépend de l'orientation du toit."), sources,
            passages)
        assert first and second
        assert first[0].source_ref == second[0].source_ref == "s1"

    def test_one_claim_can_have_multiple_sources(self, solar_profile):
        text = "Le prix dépend de la puissance installée et de la toiture."
        sources = {
            ref: {"url": f"https://{ref}.be/a", "source_quality": "SPECIALIST",
                  "relevance_status": "RELEVANT", "source_type": "web",
                  "observation_status": "ESTIMATED", "provider": "tavily"}
            for ref in ("s1", "s2", "s3")
        }
        passages = {ref: [text] for ref in sources}
        candidates = build_candidates(_claim(text), sources, passages)
        assert len({c.source_ref for c in candidates}) == 3

    def test_a_rejected_source_never_becomes_a_candidate(self, solar_profile):
        """The relevance gate is upstream of everything and is not re-litigated."""
        text = "Le prix dépend de la puissance installée."
        sources = {"bad": {"url": "https://bad.be/a", "source_quality": "SPECIALIST",
                           "relevance_status": "IRRELEVANT", "source_type": "web",
                           "observation_status": "ESTIMATED", "provider": "tavily"}}
        assert build_candidates(_claim(text), sources, {"bad": [text]}) == []

    def test_low_relevance_source_is_also_excluded(self):
        text = "Le prix dépend de la puissance installée."
        sources = {"weak": {"url": "https://weak.be/a",
                            "source_quality": "SPECIALIST",
                            "relevance_status": "LOW_RELEVANCE",
                            "source_type": "web",
                            "observation_status": "ESTIMATED",
                            "provider": "tavily"}}
        assert build_candidates(_claim(text), sources, {"weak": [text]}) == []


# ─── Passage → claim matching ────────────────────────────────────────────────

class TestPassageMatching:
    def test_on_topic_passage_supports(self):
        supports, agrees = passage_supports_claim(
            "Le prix dépend de la puissance installée.",
            "Le prix d'une installation dépend de la puissance installée au total.")
        assert supports is True
        assert agrees is None

    def test_matching_figure_agrees(self):
        supports, agrees = passage_supports_claim(
            "Une installation coûte environ 5 000 euros.",
            "Une installation résidentielle coûte environ 5 000 euros en Belgique.")
        assert supports is True and agrees is True

    def test_different_figure_disagrees(self):
        supports, agrees = passage_supports_claim(
            "Une installation coûte environ 5 000 euros.",
            "Une installation résidentielle coûte environ 9 000 euros en Belgique.")
        assert supports is False and agrees is False

    def test_off_topic_passage_is_neither(self):
        supports, agrees = passage_supports_claim(
            "Le prix dépend de la puissance installée.",
            "Le track editor supporte vingt circuits différents.")
        assert supports is False and agrees is None


# ─── Targeted authoritative research ─────────────────────────────────────────

class TestResearchPlanner:
    def _unresolved(self, profile, text: str):
        claim = _claim(text)
        return evaluate_claim(
            claim, [_ref("s1", claim.text, SourceQuality.COMMERCIAL,
                         published=NOW)], profile)

    def test_unresolved_subsidy_triggers_a_targeted_query(self, solar_profile):
        unresolved = [self._unresolved(
            solar_profile, "La prime régionale s'élève à 1 750 € en Wallonie.")]
        plan = plan_authoritative_research(
            topic="prix panneaux solaires", market="BE", unresolved=unresolved,
            profile=solar_profile)
        assert plan.queries
        assert plan.queries[0].category is ClaimCategory.SUBSIDY
        assert "energie.wallonie.be" in plan.queries[0].domains

    def test_no_unresolved_claims_means_no_queries(self, solar_profile):
        plan = plan_authoritative_research(topic="x", market="BE", unresolved=[],
                                           profile=solar_profile)
        assert plan.is_empty
        assert plan.skipped_reason == "no unresolved HIGH-risk claims"

    def test_a_vertical_can_disable_targeted_research(self, generic_profile):
        unresolved = [self._unresolved(generic_profile,
                                       "A statutory requirement of 500 applies.")]
        plan = plan_authoritative_research(topic="x", market="FR",
                                           unresolved=unresolved,
                                           profile=generic_profile)
        assert plan.is_empty
        assert "does not enable" in plan.skipped_reason

    def test_queries_are_bounded(self, solar_profile):
        unresolved = [
            self._unresolved(solar_profile, "La prime s'élève à 1 750 €."),
            self._unresolved(solar_profile, "Le taux de TVA est de 6%."),
            self._unresolved(solar_profile,
                             "Le tarif prosumer est de 100 € par an."),
            self._unresolved(solar_profile,
                             "L'installation est obligatoire selon la loi."),
        ]
        plan = plan_authoritative_research(topic="x", market="BE",
                                           unresolved=unresolved,
                                           profile=solar_profile)
        assert len(plan.queries) <= 2      # solar_be sets max_queries: 2

    def test_no_solar_domain_is_hard_coded_in_the_planner(self):
        """Domains come from configuration, never from the module.

        Checks the executable source with the module docstring stripped: the
        docstring cites the live finding by name, which is documentation worth
        keeping, and a blunt substring check over the whole file would forbid
        explaining why the module exists.
        """
        import ast
        import inspect

        from app.services import research_planner

        source = inspect.getsource(research_planner)
        tree = ast.parse(source)
        tree.body = [n for n in tree.body
                     if not (isinstance(n, ast.Expr)
                             and isinstance(n.value, ast.Constant)
                             and isinstance(n.value.value, str))]
        code = ast.unparse(tree).lower()
        for domain in ("wallonie", "vreg", "fluvius", "energiesparen", "solaire"):
            assert domain not in code, f"{domain} is hard-coded in the planner"


# ─── Summary ─────────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_counts_each_status(self, solar_profile):
        claims = [
            evaluate_claim(_claim("Les panneaux sont orientés vers le sud ici."),
                           [_ref("s1", "Les panneaux sont orientés vers le sud ici.",
                                 SourceQuality.SPECIALIST)], solar_profile),
            evaluate_claim(_claim("La prime s'élève à 1 750 € en Wallonie."),
                           [_ref("s2", "La prime s'élève à 1 750 € en Wallonie.",
                                 SourceQuality.COMMERCIAL, published=NOW)],
                           solar_profile),
        ]
        summary = summarize(claims)
        assert summary["claims_total"] == 2
        assert summary["supported"] == 1
        assert summary["high_risk_blocked"] == 1

    def test_unresolved_high_risk_is_extractable(self, solar_profile):
        claims = [evaluate_claim(
            _claim("La prime s'élève à 1 750 € en Wallonie."),
            [_ref("s2", "La prime s'élève à 1 750 € en Wallonie.",
                  SourceQuality.COMMERCIAL, published=NOW)], solar_profile)]
        assert len(unresolved_high_risk(claims)) == 1


class TestCategoryPrecision:
    """Live validation, 2026-08-12 (Phase 3.1).

    Naive substring matching classified "4.000 € TVAC" as a TAX claim, because
    "tva" is inside "TVAC". VAT-inclusive pricing is a price statement, not a
    claim about the tax rate — and misclassifying it pushed ordinary price claims
    to HIGH risk and blocked them.
    """

    @pytest.mark.parametrize("claim", [
        "Entre 4.000 € et 14.000 € TVAC pour une installation de 3 à 10 kWc.",
        "Le coût moyen est d'environ 1 000 € par kWc hors TVA.",
        "Le prix affiché est de 5 000 € TVA comprise.",
        "Prix HTVA de 4 200 € pour une installation standard.",
    ])
    def test_vat_as_a_price_qualifier_is_not_a_tax_claim(self, claim,
                                                          solar_profile):
        assert classify_category(claim, solar_profile) is not ClaimCategory.TAX

    @pytest.mark.parametrize("claim", [
        "Le taux de TVA applicable est de 6%.",
        "La TVA à 6% s'applique aux installations résidentielles.",
    ])
    def test_a_genuine_rate_claim_is_still_TAX(self, claim, solar_profile):
        assert classify_category(claim, solar_profile) is ClaimCategory.TAX

    def test_category_terms_match_whole_words_only(self, solar_profile):
        """"primeur" must not match "prime"."""
        assert classify_category(
            "Le primeur du quartier vend des légumes de saison chaque semaine.",
            solar_profile) is not ClaimCategory.SUBSIDY

    def test_a_real_subsidy_claim_still_matches(self, solar_profile):
        assert classify_category("La prime régionale s'élève à 1 750 €.",
                                 solar_profile) is ClaimCategory.SUBSIDY
