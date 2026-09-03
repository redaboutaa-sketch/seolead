"""Dates declared for documents that state none in a form the assessor reads.

The Brussels Environment document behind « un ménage bruxellois moyen de 2 à 3
personnes … 8 m² » is dated 2013 on the document itself and states nothing the
freshness assessor parses. The Sources block showed « non datée » for a
document whose date is known: a false value shown as a measurement (owner,
2026-09-03).

A declared date is a human observation with provenance — who read it, where,
when — and it travels to the page with its basis, never as the page's own
statement. Nothing here ever invents a date: an entry without `basis` is
refused at load time.
"""
from __future__ import annotations

import pathlib
import re
from functools import lru_cache

import yaml

DECLARED_DATES_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "sources" / "declared_dates.yaml"

_DATE_SHAPE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?$")


class InvalidDeclaredDate(ValueError):
    pass


@lru_cache(maxsize=1)
def declared_dates(path: pathlib.Path | None = None) -> dict[str, dict]:
    """url (exact) → {date, declared_by, declared_on, basis}."""
    target = path or DECLARED_DATES_PATH
    if not target.is_file():
        return {}
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for entry in raw.get("documents") or []:
        for key in ("url", "date", "declared_by", "declared_on", "basis"):
            if not str(entry.get(key) or "").strip():
                raise InvalidDeclaredDate(
                    f"declared date for {entry.get('url')!r} lacks {key}")
        date = str(entry["date"]).strip()
        if not _DATE_SHAPE.match(date):
            raise InvalidDeclaredDate(
                f"declared date {date!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
        out[str(entry["url"]).strip()] = {
            "date": date, "declared_by": str(entry["declared_by"]).strip(),
            "declared_on": str(entry["declared_on"]).strip(),
            "basis": str(entry["basis"]).strip(),
        }
    return out


def declared_date_for(url: str | None) -> dict | None:
    if not url:
        return None
    return declared_dates().get(str(url).strip())
