"""Price context extraction.

"€6 000" is nearly useless. "€6 000 for a 5 kWc installation, VAT included,
installation included" is actionable, and the difference is entirely context that
the source already stated and the system was throwing away.

Phase 3.4's inventory showed why it matters: the live evidence carried prices on at
least four incompatible bases — per Wc, per kWc, per m², and total system — and a
writer handed the bare figures could compare or average things that are not
comparable.

Nothing is inferred. A basis that the text does not state stays `None`, and a claim
whose basis is unknown is flagged rather than assumed to be a total.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class PriceBasis(StrEnum):
    """What the amount is per."""

    TOTAL = "TOTAL"              # for the whole installation
    PER_WP = "PER_WP"            # per watt-peak
    PER_KWP = "PER_KWP"          # per kWc / kWp
    PER_M2 = "PER_M2"
    PER_PANEL = "PER_PANEL"
    PER_KWH = "PER_KWH"
    PER_YEAR = "PER_YEAR"
    UNKNOWN = "UNKNOWN"

    @property
    def is_comparable_group(self) -> str:
        """Prices may only be ranged or compared within one basis."""
        return self.value


class VatStatus(StrEnum):
    INCLUDED = "INCLUDED"        # TVAC, TTC, incl. BTW
    EXCLUDED = "EXCLUDED"        # HTVA, hors TVA, excl.
    UNKNOWN = "UNKNOWN"


# Un nombre tel qu'un texte l'écrit : chiffres, séparateurs de milliers
# (espace, espace insécable, point) et séparateur décimal (virgule).
_NUM = r"\d[\d\s\u00a0\u202f.,]*\d|\d"

_AMOUNT = re.compile(rf"({_NUM})\s*(?:€|eur\b|euros?\b)", re.IGNORECASE)
_AMOUNT_PREFIX = re.compile(rf"(?:€|\$|£)\s*({_NUM})")
# « entre 6.000 et 10.000 € » : la devise ne suit que la borne haute, et
# `_AMOUNT` ne voyait donc que 10.000. Une fourchette réduite à sa borne haute
# est une valeur fausse affichée comme une mesure — le même défaut que
# « 5 ans » tiré de « 5 à 7 ans » (lot C), de l'autre côté du mur : la règle
# existait pour les affirmations du corps, jamais pour les montants extraits.
_RANGE_BOUNDS = re.compile(
    rf"(?:entre|de)\s+({_NUM})\s*(?:€|eur\b|euros?\b)?"
    rf"\s*(?:et|à|a|–|—|-)\s*({_NUM})\s*(?:€|eur\b|euros?\b)",
    re.IGNORECASE)

_BASIS_PATTERNS: tuple[tuple[PriceBasis, re.Pattern[str]], ...] = (
    (PriceBasis.PER_KWP, re.compile(r"(?:/|par\s+)\s*kw(?:c|p)\b", re.I)),
    (PriceBasis.PER_WP, re.compile(r"(?:/|par\s+)\s*(?:w(?:c|p)\b|watt[-\s]?cr[eê]te)", re.I)),
    (PriceBasis.PER_M2, re.compile(r"(?:/|par\s+)\s*m[²2]\b", re.I)),
    (PriceBasis.PER_KWH, re.compile(r"(?:/|par\s+)\s*kwh\b", re.I)),
    (PriceBasis.PER_YEAR, re.compile(r"(?:/|par\s+)\s*an\b", re.I)),
    (PriceBasis.PER_PANEL, re.compile(r"(?:par\s+)?panneau\s+(?:seul|solaire)?\s*"
                                      r"(?:revient|co[uû]te)|le\s+panneau\s+seul", re.I)),
)

_VAT_INCLUDED = re.compile(r"\b(?:tvac|ttc|tva\s+comprise|tva\s+incluse|"
                           r"btw\s+inbegrepen|incl\.?\s*tva)\b", re.I)
_VAT_EXCLUDED = re.compile(r"\b(?:htva|hors\s+tva|hors\s+taxes?|excl\.?\s*tva|"
                           r"exclusief\s+btw)\b", re.I)

_SYSTEM_SIZE = re.compile(r"(\d[\d.,]*)\s*(?:[-–à]\s*(\d[\d.,]*)\s*)?kw(?:c|p)\b",
                          re.IGNORECASE)
_BATTERY_IN = re.compile(r"\bavec\s+batterie|batterie\s+(?:comprise|incluse)|"
                         r"met\s+batterij\b", re.I)
_BATTERY_OUT = re.compile(r"\bsans\s+batterie|batterie\s+(?:non\s+comprise|"
                          r"en\s+option)\b", re.I)
_INSTALL_IN = re.compile(r"\bpose\s+comprise|installation\s+comprise|"
                         r"placement\s+compris|tout\s+compris|cl[eé]\s+en\s+main\b",
                         re.I)
_INSTALL_OUT = re.compile(r"\bhors\s+pose|hors\s+installation|"
                          r"panneau\s+seul|mat[eé]riel\s+seul\b", re.I)


def _amount(raw: str) -> float | None:
    """Lire un nombre comme un texte français l'écrit — ou refuser.

    L'ancienne lecture retirait tout ce qui n'était pas un chiffre : « 1,2 € »
    devenait 12, et la page prix affichait « 1 € – 12 € par watt-crête » pour
    une source qui disait 1 à 1,2 €/Wc. Un facteur dix sur une page
    commerciale, publié pendant quatre semaines.

    Les règles, dans l'ordre où l'ambiguïté se lève :
      • l'espace, sous toutes ses formes, ne sépare que des milliers ;
      • virgule ET point : le dernier des deux porte les décimales ;
      • virgule seule : décimale (« 1,2 » → 1.2) — sauf devant exactement
        trois chiffres, où « 1,500 » vaut 1,5 en français et 1500 en anglais.
        Là on REFUSE : un chiffre faux sur une page de prix coûte plus cher
        qu'un chiffre absent ;
      • point seul : milliers devant exactement trois chiffres (« 6.000 »),
        décimale sinon (« 1.2 »).
    """
    text = re.sub(r"[\s\u00a0\u202f]", "", raw or "")
    if not text or not text[0].isdigit():
        return None

    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        if len(text.rsplit(",", 1)[1]) == 3:
            return None
        text = text.replace(",", ".")
    elif has_dot:
        if len(text.rsplit(".", 1)[1]) == 3:
            text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return None


def plain(value: float) -> int | float:
    """Un montant tel qu'il se transporte en JSON : entier quand il l'est."""
    return int(value) if float(value).is_integer() else round(float(value), 2)


@dataclass(frozen=True)
class PriceContext:
    """Everything the source actually said about a price. Nothing inferred."""

    amounts: tuple[float, ...]
    currency: str | None
    basis: PriceBasis
    vat: VatStatus
    system_size_kwp: tuple[float, ...]
    battery_included: bool | None
    installation_included: bool | None
    is_range: bool

    @property
    def is_usable(self) -> bool:
        """Enough context for a reader to act on.

        A bare amount with an unknown basis is not: €6 000 could be a total, a
        per-kWc rate or a per-m² figure, and the three differ by an order of
        magnitude.
        """
        return bool(self.amounts) and self.basis is not PriceBasis.UNKNOWN

    def comparable_key(self) -> tuple:
        """Two prices may only be ranged together when this key matches."""
        return (self.basis.value, self.vat.value, self.currency or "EUR",
                self.battery_included, self.installation_included)

    def as_dict(self) -> dict:
        return {
            "amounts": [plain(a) for a in self.amounts],
            "currency": self.currency,
            "basis": self.basis.value, "vat_status": self.vat.value,
            "system_size_kwp": list(self.system_size_kwp),
            "battery_included": self.battery_included,
            "installation_included": self.installation_included,
            "is_range": self.is_range, "usable": self.is_usable,
        }


def extract_price_context(text: str) -> PriceContext | None:
    """Extract a price and its stated context, or None if there is no price."""
    text = text or ""
    amounts = [_amount(m.group(1)) for m in _AMOUNT.finditer(text)]
    amounts += [_amount(m.group(1)) for m in _AMOUNT_PREFIX.finditer(text)]
    # Les deux bornes d'une fourchette, même quand la devise ne suit que la
    # seconde. Ajoutées aux montants déjà vus : l'ensemble dédoublonne.
    for match in _RANGE_BOUNDS.finditer(text):
        amounts += [_amount(match.group(1)), _amount(match.group(2))]
    amounts = [a for a in amounts if a is not None]
    if not amounts:
        return None

    basis = PriceBasis.UNKNOWN
    for candidate, pattern in _BASIS_PATTERNS:
        if pattern.search(text):
            basis = candidate
            break
    else:
        # A total is only assumed when the text names an installation, never as a
        # fallback for "we could not tell".
        if re.search(r"\binstallation\b|\bbudget\b|\bau total\b|\binvestissement\b",
                     text, re.IGNORECASE):
            basis = PriceBasis.TOTAL

    vat = VatStatus.UNKNOWN
    if _VAT_INCLUDED.search(text):
        vat = VatStatus.INCLUDED
    elif _VAT_EXCLUDED.search(text):
        vat = VatStatus.EXCLUDED

    sizes: list[float] = []
    for match in _SYSTEM_SIZE.finditer(text):
        for group in match.groups():
            if not group:
                continue
            try:
                sizes.append(float(group.replace(",", ".")))
            except ValueError:
                continue

    battery = True if _BATTERY_IN.search(text) else (
        False if _BATTERY_OUT.search(text) else None)
    installation = True if _INSTALL_IN.search(text) else (
        False if _INSTALL_OUT.search(text) else None)

    return PriceContext(
        amounts=tuple(sorted(set(amounts))),
        currency="EUR" if re.search(r"€|eur", text, re.IGNORECASE) else None,
        basis=basis, vat=vat, system_size_kwp=tuple(sorted(set(sizes))),
        battery_included=battery, installation_included=installation,
        is_range=len(set(amounts)) > 1,
    )


def describe(context: PriceContext) -> str:
    """Human-readable qualification, for the brief and the writer."""
    parts: list[str] = []
    if context.is_range and len(context.amounts) >= 2:
        parts.append(f"{plain(context.amounts[0])}–{plain(context.amounts[-1])} "
                     f"{context.currency or ''}".strip())
    elif context.amounts:
        parts.append(f"{plain(context.amounts[0])} "
                     f"{context.currency or ''}".strip())

    basis_label = {
        PriceBasis.TOTAL: "for the whole installation",
        PriceBasis.PER_WP: "per watt-peak",
        PriceBasis.PER_KWP: "per kWc",
        PriceBasis.PER_M2: "per m²",
        PriceBasis.PER_PANEL: "per panel",
        PriceBasis.PER_KWH: "per kWh",
        PriceBasis.PER_YEAR: "per year",
        PriceBasis.UNKNOWN: "basis not stated",
    }[context.basis]
    parts.append(basis_label)

    if context.system_size_kwp:
        sizes = "–".join(str(s).rstrip("0").rstrip(".")
                         for s in context.system_size_kwp)
        parts.append(f"{sizes} kWc")
    parts.append({VatStatus.INCLUDED: "VAT included",
                  VatStatus.EXCLUDED: "VAT excluded",
                  VatStatus.UNKNOWN: "VAT status unknown"}[context.vat])
    if context.installation_included is True:
        parts.append("installation included")
    elif context.installation_included is False:
        parts.append("installation excluded")
    if context.battery_included is True:
        parts.append("battery included")
    elif context.battery_included is False:
        parts.append("battery excluded")
    return ", ".join(parts)


def observed_range(contexts: list[PriceContext], *, minimum: int = 2
                   ) -> dict | None:
    """Build an observed range from comparable price observations.

    Refuses rather than normalises. Observations on different bases, VAT
    treatments or inclusions are not comparable, and averaging them would
    manufacture a number no source stated.

    The result is explicitly an *observed sample*, never a market average.
    """
    usable = [c for c in contexts if c.is_usable]
    if len(usable) < minimum:
        return None

    groups: dict[tuple, list[PriceContext]] = {}
    for context in usable:
        groups.setdefault(context.comparable_key(), []).append(context)

    key, members = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(members) < minimum:
        return None

    amounts = sorted(a for member in members for a in member.amounts)
    basis, vat, currency, battery, installation = key
    return {
        "low": plain(amounts[0]), "high": plain(amounts[-1]),
        "currency": currency,
        "basis": basis, "vat_status": vat,
        "battery_included": battery, "installation_included": installation,
        "observation_count": len(members),
        "wording": ("observed across the retrieved sample — not a market "
                    "average"),
    }
