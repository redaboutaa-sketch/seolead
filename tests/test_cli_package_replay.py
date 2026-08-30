"""`package replay` — re-classify a sealed package under the current policy.

Written for one purpose: after fixing three labelling defects, the only honest
way to say what they were worth is to run the new policy over the claims that
were actually extracted, not over invented examples. The command measures; it
does not touch the package it measures.
"""
from __future__ import annotations

import argparse
import json
import uuid

import pytest

from app.cli import cmd_package_replay
from app.models import ResearchPackage, ResearchRun, SeedKeyword, Vertical
from app.verticals.profile import load_profile

pytestmark = pytest.mark.asyncio


# The claims below are the shapes the live run of 2026-08-30 produced: ordinary
# sentences that had inherited a price or tariff label, and a genuine price claim
# that must keep it.
SEALED_FACTS = [
    {"claim": "Les panneaux solaires n'aiment pas les fortes chaleurs.",
     "category": "MARKET_PRICE", "claim_risk": "MEDIUM",
     "evidence_status": "UNSUPPORTED"},
    {"claim": "La performance n'était plus que de 16,8 kWh par jour.",
     "category": "ENERGY_PRICE", "claim_risk": "HIGH",
     "evidence_status": "UNSUPPORTED"},
    {"claim": "Le prix moyen d'une installation est de 7 000 € en Belgique.",
     "category": "MARKET_AVERAGE", "claim_risk": "MEDIUM",
     "evidence_status": "SUPPORTED"},
]


async def _sealed_package(session, facts: list[dict]) -> ResearchPackage:
    profile = load_profile("SOLAR_BE")
    vertical = Vertical(code=profile.code, name=profile.name,
                        market=profile.market,
                        default_language=profile.default_language, active=True)
    session.add(vertical)
    await session.flush()
    keyword = SeedKeyword(vertical_id=vertical.id,
                          query="rentabilite panneaux solaires belgique",
                          normalized_query="rentabilite panneaux solaires belgique",
                          language="fr", market="BE", status="RESEARCHED")
    session.add(keyword)
    await session.flush()
    run = ResearchRun(keyword_id=keyword.id, provider="tavily", status="SUCCEEDED",
                      idempotency_key=uuid.uuid4().hex, correlation_id="t")
    session.add(run)
    await session.flush()
    package = ResearchPackage(keyword_id=keyword.id, research_run_id=run.id,
                              query=keyword.query, market="BE", language="fr",
                              intent="COMMERCIAL", facts=facts)
    session.add(package)
    await session.commit()
    return package


@pytest.fixture
def replay(monkeypatch, session):
    """Run the command against the test session and return its JSON."""
    import app.cli as cli

    class _Maker:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self_inner):
                    return session

                async def __aexit__(self_inner, *exc):
                    return False
            return _Ctx()

    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _Maker())
    captured: list[dict] = []
    monkeypatch.setattr(cli, "_emit", lambda payload: captured.append(payload))

    async def _run(package_id: str) -> dict:
        await cmd_package_replay(argparse.Namespace(id=package_id))
        return captured[-1]

    return _run


class TestPackageReplay:
    async def test_it_reports_which_claims_change_label(self, session, replay):
        package = await _sealed_package(session, SEALED_FACTS)
        report = await replay(str(package.id))

        assert report["claims"] == 3
        assert report["reclassified"] == 2
        changed = {c["claim"][:20]: c for c in report["changed"]}

        chaleurs = changed["Les panneaux solaire"]
        assert chaleurs["category"] == {"before": "MARKET_PRICE",
                                        "after": "GENERAL"}
        assert chaleurs["risk"] == {"before": "MEDIUM", "after": "LOW"}
        assert chaleurs["min_corroborating_sources"] == 1

        kwh = changed["La performance n'éta"]
        assert kwh["category"]["before"] == "ENERGY_PRICE"
        assert kwh["category"]["after"] != "ENERGY_PRICE"
        assert kwh["risk"] == {"before": "HIGH", "after": "LOW"}

    async def test_a_genuine_price_claim_keeps_its_label(self, session, replay):
        package = await _sealed_package(session, SEALED_FACTS)
        report = await replay(str(package.id))
        assert all("prix moyen" not in c["claim"] for c in report["changed"])
        assert report["category"]["after"]["MARKET_AVERAGE"] == 1

    async def test_the_risk_histogram_shows_what_the_labels_were_costing(
            self, session, replay):
        package = await _sealed_package(session, SEALED_FACTS)
        report = await replay(str(package.id))
        assert report["risk"]["before"] == {"MEDIUM": 2, "HIGH": 1}
        assert report["risk"]["after"] == {"LOW": 2, "MEDIUM": 1}

    async def test_the_package_is_not_modified(self, session, replay):
        """Read-only. A measurement that rewrites its subject measures nothing."""
        package = await _sealed_package(session, SEALED_FACTS)
        before = json.dumps(package.facts, sort_keys=True)
        await replay(str(package.id))
        await session.refresh(package)
        assert json.dumps(package.facts, sort_keys=True) == before

    async def test_it_refuses_to_report_a_support_count(self, session, replay):
        """The sealed package keeps no passage corpus.

        Re-deciding whether a claim is supported needs every eligible source's
        passages, and those are not persisted. Emitting a support count here
        would be an invention, so the command says what it cannot answer.
        """
        package = await _sealed_package(session, SEALED_FACTS)
        report = await replay(str(package.id))
        assert "supported" not in report
        assert "needs the full passage corpus" in report["note"]

    async def test_an_unknown_package_is_an_error_not_a_crash(self, replay):
        report = await replay(str(uuid.uuid4()))
        assert report == {"error": "not found"}
