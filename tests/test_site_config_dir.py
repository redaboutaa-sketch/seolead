"""L'override du répertoire de configs — QA locale uniquement.

`SEOLEAD_SITE_CONFIG_DIR` permet au crawl de pré-publication de servir une
COPIE de la config avec `staging` basculé, sans toucher au fichier suivi et
sans aucun chemin de code qui bascule une porte en place. Le test vérifie
les deux sens : l'override sert la copie, son absence sert le dépôt.
"""
from __future__ import annotations

from pathlib import Path

from app.site import config as site_config


def _reload_cache():
    site_config.load_site.cache_clear()


def test_the_override_serves_a_copy_and_only_a_copy(tmp_path, monkeypatch):
    # Depuis le lancement (2026-08-31), le fichier suivi est staging: false ;
    # la copie de QA referme les DEUX portes (un staging qui indexe serait
    # refusé par le chargeur — et c'est le bon refus).
    source = Path("config/sites/solar_be.yaml").read_text(encoding="utf-8")
    assert "staging: false" in source, "le dépôt est lancé"
    copy = source.replace("staging: false", "staging: true") \
                 .replace("allow_indexing: true", "allow_indexing: false")
    (tmp_path / "solar_be.yaml").write_text(copy, encoding="utf-8")

    monkeypatch.setenv("SEOLEAD_SITE_CONFIG_DIR", str(tmp_path))
    _reload_cache()
    try:
        assert site_config.load_site("solar_be").staging is True
        assert site_config.available_sites() == ["solar_be"]
    finally:
        monkeypatch.delenv("SEOLEAD_SITE_CONFIG_DIR")
        _reload_cache()

    # Sans l'override, le fichier suivi reprend la main — lancé.
    assert site_config.load_site("solar_be").staging is False
