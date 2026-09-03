"""Réserves de clôture du 2026-09-03 : pièces, pas rapports.

5. Le détecteur de fraîcheur lit « à partir du 14 février 2025 » sur une page
   qui mentionne aussi « jusqu'au 13/02/2025 » (fin de l'ancien régime) comme
   une validité terminée. La direction du défaut est prouvée ici : la source
   est REFUSÉE, jamais acceptée comme périmée passée inaperçue. Le test qui
   dit ce que serait la lecture juste est marqué comme défaut connu.
2. Une date déclarée par une personne sur un document que la page ne date
   pas est rendue avec sa base — jamais comme une date énoncée par la page.
3. Toute source est nommée par son hôte, en texte, sans lien.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import freshness
from app.site.publication import render_sources

NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
PRIME_HABITATION = (
    "Prime pour son habitation (à partir du 14 février 2025). Les demandes "
    "relevant de l'ancien régime restaient recevables jusqu'au 13/02/2025."
)


class TestFreshnessDefectDirection:
    def test_the_page_is_refused_not_accepted(self):
        verdict = freshness.assess(PRIME_HABITATION, now=NOW)
        assert verdict.status is freshness.FreshnessStatus.DATED_EXPIRED
        assert verdict.effective_from == "14 février 2025"
        assert verdict.effective_until == "13/02/2025"
        # Refused: nothing about the present can rest on it.
        assert verdict.status not in (freshness.FreshnessStatus.DATED_CURRENT,
                                      freshness.FreshnessStatus.UNDATED_CURRENT)

    def test_a_truly_expired_page_is_refused_too(self):
        verdict = freshness.assess(
            "Cette prime était valable jusqu'au 13/02/2025.", now=NOW)
        assert verdict.status is freshness.FreshnessStatus.DATED_EXPIRED

    @pytest.mark.xfail(strict=True, reason=(
        "défaut connu (2026-09-03) : la fin de l'ancien régime est lue comme "
        "la fin du nouveau ; la lecture juste serait DATED_CURRENT depuis le "
        "14 février 2025. À corriger avant l'article primes."))
    def test_what_the_right_reading_would_be(self):
        verdict = freshness.assess(PRIME_HABITATION, now=NOW)
        assert verdict.status is freshness.FreshnessStatus.DATED_CURRENT


class TestEverySourceIsNamed:
    def test_a_commercial_source_is_named_by_its_host_without_a_link(self):
        claim = {"claim": "Une famille de 4 personnes consomme 5000 kWh.",
                 "evidence_status": "SUPPORTED", "region": "BE",
                 "evidence": [{"url": "https://www.un-installateur.be/blog/x",
                               "source_quality": "COMMERCIAL", "supports": True,
                               "published_at": None, "freshness_status": "UNDATED"}]}
        sources = render_sources("Une famille de 4 personnes consomme 5000 kWh.", [claim])
        assert sources[0]["name"] == "un-installateur.be"
        assert "url" not in sources[0] and "http" not in str(sources[0])
