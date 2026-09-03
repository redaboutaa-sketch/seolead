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

import pathlib
from datetime import datetime, timezone

import pytest

from app.services import freshness
from app.site import source_dates
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


class TestDeclaredDates:
    def _load(self, tmp_path, text):
        path = tmp_path / "declared_dates.yaml"
        path.write_text(text, encoding="utf-8")
        source_dates.declared_dates.cache_clear()
        return source_dates.declared_dates(path)

    def test_an_entry_needs_its_provenance(self, tmp_path):
        with pytest.raises(source_dates.InvalidDeclaredDate):
            self._load(tmp_path, "documents:\n  - url: https://x/y.pdf\n    date: 2013-03\n")

    def test_a_date_must_be_a_date(self, tmp_path):
        with pytest.raises(source_dates.InvalidDeclaredDate):
            self._load(tmp_path, "documents:\n  - url: https://x/y.pdf\n    date: mars 2013\n"
                                 "    declared_by: owner\n    declared_on: 2026-09-03\n    basis: couverture\n")

    def test_a_declared_date_travels_with_its_basis(self, tmp_path, monkeypatch):
        loaded = self._load(tmp_path, "documents:\n  - url: https://x/y.pdf\n    date: 2013-03\n"
                                      "    declared_by: owner\n    declared_on: 2026-09-03\n"
                                      "    basis: date imprimée sur la couverture\n")
        monkeypatch.setattr(source_dates, "declared_dates", lambda: loaded)
        claim = {"claim": "Une installation de 8 m² fournit un tiers de l'électricité.",
                 "evidence_status": "SUPPORTED", "region": "BE-BRU",
                 "evidence": [{"url": "https://x/y.pdf", "source_quality": "OFFICIAL",
                               "supports": True, "region": "BE-BRU",
                               "authority_type": "PUBLIC_AGENCY",
                               "published_at": None, "effective_from": None,
                               "freshness_status": "UNDATED"}]}
        sources = render_sources("Une installation de 8 m² suffit.", [claim])
        assert sources[0]["date"] == "2013-03"
        assert sources[0]["date_basis"] == "declared"

    def test_a_stated_date_wins_over_a_declared_one(self, tmp_path, monkeypatch):
        loaded = self._load(tmp_path, "documents:\n  - url: https://x/y.pdf\n    date: 2013-03\n"
                                      "    declared_by: owner\n    declared_on: 2026-09-03\n"
                                      "    basis: couverture\n")
        monkeypatch.setattr(source_dates, "declared_dates", lambda: loaded)
        claim = {"claim": "Une installation de 8 m² fournit un tiers de l'électricité.",
                 "evidence_status": "SUPPORTED", "region": "BE-BRU",
                 "evidence": [{"url": "https://x/y.pdf", "source_quality": "OFFICIAL",
                               "supports": True, "published_at": "2014-01-01T00:00:00+00:00",
                               "freshness_status": "OBSERVED"}]}
        sources = render_sources("Une installation de 8 m² suffit.", [claim])
        assert sources[0]["date"] == "2014-01-01"
        assert sources[0]["date_basis"] == "stated"

    def test_the_real_file_loads_or_is_absent(self):
        source_dates.declared_dates.cache_clear()
        loaded = source_dates.declared_dates()
        for url, entry in loaded.items():
            assert entry["basis"] and entry["declared_by"] and entry["declared_on"]


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
