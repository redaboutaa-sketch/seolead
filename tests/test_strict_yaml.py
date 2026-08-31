"""Le chargeur strict, épinglé sur les pathologies mesurées.

Chaque cas « pathologie » ci-dessous a été mesuré en PyYAML par défaut le
2026-08-31 avec le type 1.1 en commentaire — c'est exactement ce que
`strict_load` doit refuser de refaire. Les cas « canoniques » vérifient que
les types voulus survivent : un vrai booléen, un entier, un flottant, un null.
"""
from __future__ import annotations

import datetime

import pytest
import yaml

from app.core.strict_yaml import strict_load


class TestPathologiesMeasured:
    """Les cinq scalaires qui changeaient de type en silence."""

    @pytest.mark.parametrize("raw, legacy_value", [
        ("YES", True),                        # bool 1.1 — le bug battery_interest
        ("0123", 83),                         # octal 1.1
        ("2026-08-31", datetime.date(2026, 8, 31)),  # timestamp implicite
        ("12:30", 750),                       # sexagésimal 1.1
        ("Off", False),                       # bool 1.1
    ])
    def test_the_legacy_loader_really_did_this(self, raw, legacy_value):
        # Le témoin : sans cette mesure, le test d'à côté ne prouve rien.
        assert yaml.safe_load(f"v: {raw}")["v"] == legacy_value

    @pytest.mark.parametrize("raw", ["YES", "0123", "2026-08-31", "12:30", "Off"])
    def test_strict_load_keeps_the_string_as_written(self, raw):
        assert strict_load(f"v: {raw}") == {"v": raw}

    @pytest.mark.parametrize("raw", [
        "yes", "no", "No", "NO", "on", "On", "ON", "off", "OFF",
        "True", "TRUE", "False", "FALSE", "Yes", "y", "n",
    ])
    def test_every_1_1_boolean_spelling_stays_a_string(self, raw):
        assert strict_load(f"v: {raw}") == {"v": raw}

    def test_sexagesimal_with_seconds_stays_a_string(self):
        assert strict_load("v: 1:02:03") == {"v": "1:02:03"}

    def test_datetime_stays_a_string(self):
        assert strict_load("v: 2026-08-31T12:30:00") == {
            "v": "2026-08-31T12:30:00"}


class TestCanonicalTypesSurvive:
    @pytest.mark.parametrize("raw, expected", [
        ("true", True),
        ("false", False),
        ("42", 42),
        ("-7", -7),
        ("0", 0),
        ("1.5", 1.5),
        ("-0.25", -0.25),
        ("~", None),
        ("null", None),
        ("", None),
    ])
    def test_scalar(self, raw, expected):
        assert strict_load(f"v: {raw}") == {"v": expected}

    def test_quoted_scalars_are_always_strings(self):
        assert strict_load('v: "true"') == {"v": "true"}
        assert strict_load('v: "42"') == {"v": "42"}

    def test_structures_load_normally(self):
        loaded = strict_load("a:\n  - 1\n  - x\nb:\n  c: true\n")
        assert loaded == {"a": [1, "x"], "b": {"c": True}}

    def test_the_site_config_loads_with_the_strict_loader(self):
        from pathlib import Path
        text = Path("config/sites/solar_be.yaml").read_text(encoding="utf-8")
        loaded = strict_load(text)
        assert isinstance(loaded, dict) and loaded["site_id"] == "solar_be"
