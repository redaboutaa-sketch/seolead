"""What a page says about its own validity, and when that is not the present.

Two defects, found by reading the CWaPE probe of 2026-08-30 rather than by
imagining cases.

**`effective_from` was parsed and then ignored.** "Le tarif s'applique à partir
du 01/01/2026" produced `effective_from: 01/01/2026`, recorded it in the
signals, and returned UNDATED — so the strongest thing a regulator's page can
carry, the date its rule came into force, established nothing.

**A range matched neither pattern.** Both `_EFFECTIVE_FROM` and
`_EFFECTIVE_UNTIL` need a lead-in preposition, and "du X au Y" is neither. The
page titled « Les tarifs prosumer 2024-2025 » carries `01/01/2025` and
`31/12/2025` in its text and came back UNDATED with not one signal.

The future case is the one that matters most and the one no test existed for. A
regulator announcing next January's tariff writes about it in the present tense.
The page is right; a claim repeating it as today's number would be false.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services.freshness import FreshnessStatus, as_date, assess

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def _assess(text: str, **kwargs):
    return assess(text, now=NOW, **kwargs)


# ─── A stated start date decides ─────────────────────────────────────────────

class TestEffectiveFromParticipates:
    def test_in_force_since_a_past_date_is_dated_current(self):
        verdict = _assess("Le tarif prosumer s'applique à partir du 01/01/2026.")
        assert verdict.status is FreshnessStatus.DATED_CURRENT
        assert verdict.status.can_support_current_claim
        assert verdict.effective_from == "01/01/2026"

    def test_a_start_date_still_to_come_is_not_the_present(self):
        verdict = _assess("Le nouveau tarif s'applique à partir du 01/01/2027.")
        assert verdict.status is FreshnessStatus.DATED_FUTURE
        assert verdict.status.can_support_current_claim is False

    def test_the_future_beats_a_currency_marker(self):
        """The order that matters, and the reason for it.

        A regulator announcing next January's tariff writes "actuellement" about
        the scheme in the same breath. Letting the marker win would publish
        2027's number as this year's.
        """
        verdict = _assess("Actuellement, le tarif applicable à partir du "
                          "01/01/2027 sera de 0,0545 €/kWh.")
        assert verdict.status is FreshnessStatus.DATED_FUTURE

    def test_a_start_date_this_module_cannot_read_changes_nothing(self):
        """Guessing at "au printemps" would invent what this module refuses to."""
        assert _assess("Le tarif s'applique à partir du printemps 2027.") \
            .status is FreshnessStatus.UNDATED

    def test_the_raw_string_is_still_what_is_kept(self):
        """The promise does not change: a reviewer reads what the page wrote."""
        assert _assess("En vigueur depuis le 30 septembre 2020.") \
            .effective_from == "30 septembre 2020"


# ─── The range form ──────────────────────────────────────────────────────────

class TestTheRangeForm:
    @pytest.mark.parametrize("text,status", [
        ("Tarif prosumer applicable du 01/01/2026 au 31/12/2026.",
         FreshnessStatus.DATED_CURRENT),
        ("Tarif prosumer applicable du 01/01/2025 au 31/12/2025.",
         FreshnessStatus.DATED_EXPIRED),
        ("Tarif prosumer applicable du 01/01/2027 au 31/12/2027.",
         FreshnessStatus.DATED_FUTURE),
    ])
    def test_a_period_is_read_from_both_ends(self, text, status):
        assert _assess(text).status is status

    def test_it_fills_both_ends(self):
        verdict = _assess("Applicable du 1er janvier 2026 au 31 décembre 2026.")
        assert verdict.effective_from == "1er janvier 2026"
        assert verdict.effective_until == "31 décembre 2026"

    def test_a_lead_in_phrase_still_wins_over_the_range(self):
        """The explicit form is the more deliberate one; it is not overwritten."""
        verdict = _assess("En vigueur depuis le 01/03/2026. Barème du "
                          "01/01/2020 au 31/12/2020 pour mémoire.")
        assert verdict.effective_from == "01/03/2026"

    def test_dutch_reads_too(self):
        assert _assess("Prosumententarief van 01/01/2027 tot 31/12/2027.") \
            .status is FreshnessStatus.DATED_FUTURE


# ─── The canary the probe asked for ──────────────────────────────────────────

class TestTheCwapeCanary:
    """cwape.be/node/151, « Les tarifs prosumer 2024-2025 ».

    The probe reported `01/01/2025` and `31/12/2025` in its text, freshness
    UNDATED, signals empty. It did not report the words AROUND those dates, so
    "du … au …" stayed a hypothesis — which is why `date_forensics` now carries
    `date_contexts` and the next probe answers it for free.

    What is pinned here is the consequence either way. If the page uses the
    range form it becomes datable, and datable makes it WORSE for a claim about
    2026, not better: a 2025 period that has ended is DATED_EXPIRED, and the
    gate refuses it for a reason instead of by accident. That is the whole
    difference this piece buys, and it is not the difference one might expect.
    """

    PAGE = ("Les tarifs prosumer 2024-2025. Le tarif prosumer est applicable "
            "du 01/01/2025 au 31/12/2025 par gestionnaire de réseau.")

    def test_the_page_becomes_datable(self):
        verdict = _assess(self.PAGE)
        assert verdict.status.is_dated
        assert verdict.effective_from == "01/01/2025"
        assert verdict.effective_until == "31/12/2025"

    def test_and_being_datable_makes_it_refused_on_purpose(self):
        verdict = _assess(self.PAGE)
        assert verdict.status is FreshnessStatus.DATED_EXPIRED
        assert verdict.status.can_support_current_claim is False
        assert "31/12/2025" in verdict.note

    def test_the_same_page_naming_the_current_period_would_support_a_claim(self):
        """The case the hardening actually buys, stated so it cannot be lost."""
        verdict = _assess(self.PAGE.replace("2025", "2026")
                          .replace("2024-2026", "2025-2026"))
        assert verdict.status is FreshnessStatus.DATED_CURRENT
        assert verdict.status.can_support_current_claim


class TestTheOtherCanaryStaysAtZero:
    """energie.wallonie.be dated 0 of 10 in the Q2 probe, and must keep dating 0.

    Its pages carry no date, no validity period and no currency marker. A
    hardening that started finding dates there would be finding them in the
    price tables and legal citations that made it a canary in the first place.
    """

    @pytest.mark.parametrize("text", [
        "Le tarif prosumer explique la contribution aux coûts du réseau.",
        "Prime de 1500 € pour une installation de 4 kWc, décret du 2 mai 2019 "
        "relatif au marché de l'électricité.",
        "Les certificats verts sont octroyés pendant 10 ans, horizon 2030.",
        "Comparatif 2008-2024 du prix de l'électricité pour un ménage type.",
    ])
    def test_no_date_is_invented(self, text):
        verdict = _assess(text, url="https://energie.wallonie.be/fr/x.html")
        assert verdict.status is FreshnessStatus.UNDATED
        assert verdict.effective_from is None
        assert verdict.effective_until is None


# ─── The parser, and what it refuses ─────────────────────────────────────────

class TestDateParsing:
    @pytest.mark.parametrize("raw,expected", [
        ("01/01/2026", date(2026, 1, 1)),
        ("1-2-2026", date(2026, 2, 1)),
        ("01.01.26", date(2026, 1, 1)),
        ("2026-01-01", date(2026, 1, 1)),
        ("30 septembre 2020", date(2020, 9, 30)),
        ("1er janvier 2026", date(2026, 1, 1)),
        ("1 januari 2026", date(2026, 1, 1)),
    ])
    def test_the_formats_a_belgian_regulator_uses(self, raw, expected):
        assert as_date(raw) == expected

    @pytest.mark.parametrize("raw", [
        None, "", "printemps 2026", "2026", "31/02/2025", "01/13/2026",
        "next January",
    ])
    def test_everything_else_is_none_rather_than_a_guess(self, raw):
        assert as_date(raw) is None

    def test_a_day_first_reading_is_the_only_one(self):
        """`01/02/2026` is 1 February in Belgium and nowhere in this codebase
        is it 2 January. Stated, because a silent locale assumption is how a
        tariff moves by eleven months."""
        assert as_date("01/02/2026") == date(2026, 2, 1)


# ─── The probe must answer the question it raised ────────────────────────────

class TestDateContexts:
    """A hypothesis that cannot be checked from the output is one the next
    probe pays for again.

    The CWaPE probe listed `01/01/2025` and `31/12/2025` and threw away their
    sentence, so which lead-in phrase the page uses — the whole question — could
    not be answered without spending on another call.
    """

    class _Source:
        title = "Les tarifs prosumer 2024-2025 | CWAPE"
        summary = ("Le tarif prosumer est applicable du 01/01/2025 au "
                   "31/12/2025 par gestionnaire de réseau de distribution.")
        url = "https://www.cwape.be/node/151"
        published_at = None
        retrieved_at = None
        metadata: dict = {}
        source_type = "web"

    def test_each_date_comes_back_with_the_words_around_it(self):
        from app.services.authority_probe import date_forensics

        contexts = date_forensics(self._Source())["date_contexts"]
        assert contexts, "the dates came back without their sentence again"
        joined = " ".join(contexts)
        assert "applicable du 01/01/2025" in joined
        assert "au 31/12/2025" in joined

    def test_a_source_with_no_date_reports_no_context(self):
        from app.services.authority_probe import date_forensics

        class _Mute(self._Source):
            title = "Je suis un prosumer"
            summary = "Le tarif prosumer explique la contribution au réseau."

        assert date_forensics(_Mute())["date_contexts"] == []
