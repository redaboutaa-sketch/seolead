"""Writer contract and factual QA V2 — Phase 3.1.

The writer contract is a containment boundary: whatever the evidence model
decides, the writer must be structurally unable to see material the model
rejected. These tests check the boundary holds, not merely that it is intended.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.enums import EvidenceStatus, SearchIntent, SourceState
from app.schemas.research import (NormalizedFact, NormalizedSource,
                                  ResearchProviderResult, SourceOutcome)
from app.services.factual_qa_v2 import extract_draft_claims, run_factual_qa_v2
from app.services.package_builder_v3 import build_package_v3, writer_payload

NOW = datetime.now(timezone.utc)

RACING_TITLE = ("The making of Don Matrelli's Legacy, a mod for Grand Prix "
                "Circuit (part I)")


def _result(sources, facts=None) -> ResearchProviderResult:
    return ResearchProviderResult(
        provider="tavily", query="prix panneaux solaires Belgique", market="BE",
        language="fr", status="SUCCEEDED", sources=sources, facts=facts or [],
        source_outcomes=[SourceOutcome(source_type="web", state=SourceState.OK,
                                       item_count=len(sources))])


def _source(ref: str, url: str, title: str, summary: str, *,
            published=None) -> NormalizedSource:
    return NormalizedSource(source_type="web", state=SourceState.OK, url=url,
                            title=title, summary=summary, published_at=published,
                            retrieved_at=NOW, candidate_id=ref)


def _package(sources, profile) -> dict:
    return build_package_v3(
        query="prix panneaux solaires Belgique", market="BE", language="fr",
        intent=SearchIntent.COMMERCIAL, profile=profile, serp=None,
        serp_analysis=None, keyword_metrics=[],
        research_results=[_result(sources)])


GOOD_SOURCE = _source(
    "good", "https://guide-photovoltaique.be/prix",
    "Prix des panneaux solaires en Belgique",
    "Le prix d'une installation de panneaux solaires dépend de la puissance "
    "installée, du type de toiture et de la complexité de la pose. "
    "L'orientation du toit influence directement la production annuelle.")

RACING_SOURCE = _source(
    "racing", "https://marnetto.net/dml", RACING_TITLE,
    "Building a modification for the classic racing game Grand Prix Circuit, "
    "covering track editing and sprite work in detail.")


class TestWriterContract:
    def test_writer_never_receives_rejected_sources(self, solar_profile):
        package = _package([GOOD_SOURCE, RACING_SOURCE], solar_profile)
        view = writer_payload(package)

        blob = str(view)
        assert "Grand Prix" not in blob
        assert "marnetto" not in blob
        assert "racing" not in blob.lower()

    def test_writer_never_receives_raw_excerpts(self, solar_profile):
        package = _package([GOOD_SOURCE], solar_profile)
        view = writer_payload(package)
        # Only the four contract keys, nothing resembling a source dump.
        assert set(view) == {"supported_claims", "partially_supported_claims",
                             "unresolved_facts", "forbidden_claims"}
        assert "eligible_evidence" not in view
        assert "sources" not in view

    def test_only_supported_claims_are_offered_by_default(self, solar_profile):
        package = _package([GOOD_SOURCE], solar_profile)
        view = writer_payload(package)
        assert view["partially_supported_claims"] == []
        for claim in view["supported_claims"]:
            assert claim["evidence_status"] == EvidenceStatus.SUPPORTED.value

    def test_partial_claims_are_labelled_when_policy_allows(self, solar_profile):
        subsidy = _source(
            "sub", "https://energie.wallonie.be/primes",
            "Primes photovoltaïques en Wallonie",
            "La prime régionale pour une installation photovoltaïque s'élève à "
            "1 750 euros en Wallonie selon le portail énergie régional.")
        package = _package([subsidy], solar_profile)
        view = writer_payload(package, allow_partial=True)
        for claim in view["partially_supported_claims"]:
            assert claim["evidence_status"] == \
                EvidenceStatus.PARTIALLY_SUPPORTED.value
            assert claim["caveat"], "a partial claim must carry its caveat"

    def test_forbidden_claims_are_named(self, solar_profile):
        commercial_subsidy = _source(
            "vendor", "https://installateur-solaire.be/primes",
            "Primes panneaux solaires",
            "La prime régionale s'élève à 1 750 euros pour toute installation "
            "photovoltaïque résidentielle en Wallonie cette année.")
        package = _package([commercial_subsidy], solar_profile)
        view = writer_payload(package)
        categories = {c["topic"] for c in view["forbidden_claims"]}
        assert "SUBSIDY" in categories

    def test_supported_claims_carry_their_sources(self, solar_profile):
        package = _package([GOOD_SOURCE], solar_profile)
        view = writer_payload(package)
        assert view["supported_claims"]
        for claim in view["supported_claims"]:
            assert claim["sources"]
            for source in claim["sources"]:
                assert source["url"]
                assert source["passage"]


class TestPackageV3Integration:
    def test_racing_source_is_rejected_and_contributes_no_claims(self,
                                                                  solar_profile):
        package = _package([GOOD_SOURCE, RACING_SOURCE], solar_profile)
        rejected_refs = {r["ref"] for r in package["rejected_evidence"]}
        assert "racing" in rejected_refs
        assert all(c["source_ref"] != "racing" for c in package["claims"])

    def test_one_excerpt_yields_several_atomic_claims(self, solar_profile):
        package = _package([GOOD_SOURCE], solar_profile)
        assert package["claim_extraction"]["claims"] >= 2

    def test_passage_extraction_is_reported(self, solar_profile):
        noisy = _source(
            "noisy", "https://x.be/a", "Prix des panneaux solaires",
            "Aller au contenu\n\nMenu\n\nLe prix d'une installation de panneaux "
            "solaires dépend de la puissance installée et du type de toiture.\n\n"
            "La boutique ne fonctionnera pas correctement dans le cas où les "
            "cookies sont désactivés.")
        package = _package([noisy], solar_profile)
        stats = package["passage_extraction"]
        assert stats and stats[0]["dropped"] >= 1

    def test_undated_source_still_produces_supported_claims(self, solar_profile):
        """The Phase 3 blocker, at package level.

        Every Tavily source is undated. If that alone prevented support, the
        package would carry zero usable claims for any query.
        """
        package = _package([GOOD_SOURCE], solar_profile)
        assert all(s["observation_status"] == "ESTIMATED"
                   for s in package["eligible_evidence"])
        assert package["confidence_summary"]["supported"] >= 1

    def test_package_is_version_3(self, solar_profile):
        package = _package([GOOD_SOURCE], solar_profile)
        assert package["provider_provenance"]["package_version"] == 3

    def test_authoritative_plan_appears_when_high_risk_is_unresolved(self,
                                                                     solar_profile):
        commercial_subsidy = _source(
            "vendor", "https://installateur-solaire.be/primes",
            "Primes panneaux solaires",
            "La prime régionale s'élève à 1 750 euros pour une installation "
            "photovoltaïque résidentielle en Wallonie cette année.")
        package = _package([commercial_subsidy], solar_profile)
        plan = package["authoritative_research_plan"]
        assert plan["queries"], plan
        assert any("energie.wallonie.be" in q["domains"] for q in plan["queries"])


class TestFactualQAV2:
    def _ledger(self, status: str, risk: str = "HIGH",
                category: str = "SUBSIDY") -> dict:
        return {"claims": [{
            "claim": "La prime régionale s'élève à 1 750 euros en Wallonie.",
            "evidence_status": status, "claim_risk": risk, "category": category,
            "reason": "test", "evidence": []}]}

    def test_high_risk_unsupported_claim_asserted_in_the_draft_blocks(
            self, solar_profile):
        draft = {"body": "# T\n\nLa prime régionale s'élève à 1 750 euros en "
                         "Wallonie selon les autorités."}
        verdict = run_factual_qa_v2(draft, self._ledger("UNSUPPORTED"),
                                    solar_profile)
        assert verdict["status"] == "FAILED"
        assert any(f["code"] == "HIGH_RISK_CLAIM_ASSERTED"
                   for f in verdict["blocking_issues"])

    def test_unresolved_claim_not_asserted_does_not_block(self, solar_profile):
        """A research gap is not a draft defect."""
        draft = {"body": "# T\n\nLe prix dépend de la puissance installée de "
                         "3 kWc et du type de toiture choisi."}
        ledger = self._ledger("UNSUPPORTED")
        ledger["claims"].append({
            "claim": "Le prix dépend de la puissance installée de 3 kWc.",
            "evidence_status": "SUPPORTED", "claim_risk": "LOW",
            "category": "GENERAL", "reason": "", "evidence": []})
        verdict = run_factual_qa_v2(draft, ledger, solar_profile)
        assert not any(f["code"] == "HIGH_RISK_CLAIM_ASSERTED"
                       for f in verdict["blocking_issues"])

    def test_conflicting_evidence_blocks(self, solar_profile):
        draft = {"body": "# T\n\nLa prime régionale s'élève à 1 750 euros en "
                         "Wallonie aujourd'hui."}
        verdict = run_factual_qa_v2(draft, self._ledger("CONFLICTING"),
                                    solar_profile)
        assert any(f["code"] == "CONFLICTING_EVIDENCE_ASSERTED"
                   for f in verdict["blocking_issues"])

    def test_draft_claim_with_no_matching_supported_claim_blocks(self,
                                                                  solar_profile):
        draft = {"body": "# T\n\nUne installation coûte 12 345 euros en moyenne."}
        package = {"claims": [{
            "claim": "Le prix dépend de la puissance installée.",
            "evidence_status": "SUPPORTED", "claim_risk": "LOW",
            "category": "GENERAL", "reason": "", "evidence": []}]}
        verdict = run_factual_qa_v2(draft, package, solar_profile)
        assert any(f["code"] == "UNSUPPORTED_DRAFT_CLAIM"
                   for f in verdict["blocking_issues"])

    def test_supported_claim_restated_faithfully_passes(self, solar_profile):
        draft = {"body": "# T\n\nUne installation résidentielle de 5 kWc coûte "
                         "environ 5 000 euros."}
        package = {"claims": [{
            "claim": "Une installation résidentielle de 5 kWc coûte environ "
                     "5 000 euros.",
            "evidence_status": "SUPPORTED", "claim_risk": "MEDIUM",
            "category": "MARKET_PRICE", "reason": "", "evidence": []}]}
        verdict = run_factual_qa_v2(draft, package, solar_profile)
        assert verdict["status"] == "PASSED", verdict["blocking_issues"]

    def test_ledger_counts_are_reported(self, solar_profile):
        verdict = run_factual_qa_v2({"body": ""}, self._ledger("UNSUPPORTED"),
                                    solar_profile)
        assert verdict["claim_ledger"]["total"] == 1
        assert verdict["claim_ledger"]["unsupported"] == 1

    def test_draft_with_no_supported_claims_at_all_blocks(self, solar_profile):
        draft = {"body": "# T\n\nUne installation coûte environ 5 000 euros."}
        verdict = run_factual_qa_v2(draft, {"claims": []}, solar_profile)
        assert verdict["status"] == "FAILED"

    def test_only_factual_sentences_are_extracted(self):
        body = ("# Titre\n\nLes panneaux sont orientés vers le sud. "
                "Une installation coûte 5 000 €. Le rendement atteint 20 %.")
        claims = extract_draft_claims(body)
        assert len(claims) == 2
