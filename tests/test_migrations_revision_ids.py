"""Every Alembic revision id must fit the `alembic_version.version_num` column.

Measured on the host the 2026-09-03: the upgrade to 0014 ran its DDL, then
failed on `UPDATE alembic_version SET version_num='0014_fingerprint_and_
research_resolution'` — 40 characters into a VARCHAR(32) — and rolled the
whole migration back. The API had already been restarted on the new model.
Nothing in the repository checked the one property of a revision id that
Postgres checks.
"""
from __future__ import annotations

import pathlib
import re

import pytest

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
# Alembic's default column: `version_num VARCHAR(32) NOT NULL`.
ALEMBIC_VERSION_NUM_WIDTH = 32
_REVISION = re.compile(r'^revision(?::\s*str)?\s*=\s*"([^"]+)"', re.M)
_DOWN = re.compile(r'^down_revision(?::[^=]+)?\s*=\s*(?:"([^"]+)"|None)', re.M)


def _migrations() -> list[tuple[str, str, str | None]]:
    rows = []
    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        revision = _REVISION.search(text)
        down = _DOWN.search(text)
        assert revision, f"{path.name} declares no revision"
        rows.append((path.name, revision.group(1), down.group(1) if down else None))
    return rows


@pytest.mark.parametrize("name,revision,_down", _migrations(),
                         ids=[m[0] for m in _migrations()])
def test_revision_id_fits_the_alembic_version_column(name, revision, _down):
    assert len(revision) <= ALEMBIC_VERSION_NUM_WIDTH, (
        f"{name}: revision id {revision!r} is {len(revision)} characters; "
        f"alembic_version.version_num holds {ALEMBIC_VERSION_NUM_WIDTH}. The "
        f"upgrade would apply its DDL and then roll back on the bookkeeping "
        f"UPDATE, as 0014 did on 2026-09-03.")


def test_every_down_revision_names_an_existing_revision():
    rows = _migrations()
    known = {r for _, r, _ in rows}
    for name, _revision, down in rows:
        if down is not None:
            assert down in known, f"{name}: down_revision {down!r} is not a revision"


def test_the_failure_that_was_measured_would_have_been_caught():
    # The exact id that broke the host, kept as the mutation this test kills.
    assert len("0014_fingerprint_and_research_resolution") > ALEMBIC_VERSION_NUM_WIDTH
