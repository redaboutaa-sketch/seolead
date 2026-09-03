"""The second authoritative round persists under its own idempotency key.

Measured on the host the 2026-09-03, first live run of the tranche
structurelle: round 1 (ROI, SUBSIDY, SUBSIDY_VLG, GRID_RULE) persisted under
`<correlation>:tavily_authoritative`; round 2 (ELIGIBILITY) tried the same key
and the job died on `uq_research_run_idempotency` after every query had been
paid for. Nothing was persisted past the first round.
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import SeedKeyword, Vertical
from app.services.authoritative_research import AuthoritativeRunResult
from app.services.pipeline_v2 import _persist_research, second_round_key


def _official_result():
    return AuthoritativeRunResult().to_provider_result(
        query="rentabilité panneaux solaires Belgique", market="BE",
        language="fr")


async def _keyword(session):
    vertical = Vertical(code="SOLAR_BE", name="Solar Belgium", market="BE",
                        default_language="fr", active=True)
    session.add(vertical)
    await session.flush()
    keyword = SeedKeyword(vertical_id=vertical.id,
                          query="rentabilité panneaux solaires Belgique",
                          normalized_query="rentabilite panneaux solaires belgique",
                          market="BE", language="fr")
    session.add(keyword)
    await session.flush()
    return keyword


class TestSecondRoundKey:
    def test_the_first_round_keeps_its_historical_key(self):
        assert second_round_key(1) == ""

    def test_later_rounds_are_distinguished(self):
        assert second_round_key(2) == ":round2"
        assert second_round_key(2) != second_round_key(3)


@pytest.mark.asyncio
class TestTwoRoundsOneJob:
    async def test_two_rounds_of_the_same_provider_both_persist(self, session):
        keyword = await _keyword(session)
        first = await _persist_research(
            session, keyword=keyword, result=_official_result(), decisions={},
            correlation_id="job", key_suffix=second_round_key(1))
        second = await _persist_research(
            session, keyword=keyword, result=_official_result(), decisions={},
            correlation_id="job", key_suffix=second_round_key(2))
        assert first.idempotency_key == "job:tavily_authoritative"
        assert second.idempotency_key == "job:tavily_authoritative:round2"

    async def test_the_measured_failure_without_the_suffix(self, session):
        """The mutation this test kills: same key twice is the host crash."""
        keyword = await _keyword(session)
        await _persist_research(session, keyword=keyword,
                                result=_official_result(), decisions={},
                                correlation_id="job")
        with pytest.raises(IntegrityError):
            await _persist_research(session, keyword=keyword,
                                    result=_official_result(), decisions={},
                                    correlation_id="job")
