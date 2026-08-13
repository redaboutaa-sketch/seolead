"""Claim category, risk, authority and freshness — all from vertical configuration.

Phase 3 asked one question of a claim ("how bad if wrong?") and derived a single
source-quality bar from it. That is too coarse, and it conflated two independent
things: *who* must say something, and *when* they must have said it.

Phase 3.1 splits them:

    category  →  risk  ·  authority requirement  ·  freshness requirement
                        ·  corroboration requirement

A subsidy figure needs an official source AND a date. A vendor's own displayed
price needs neither — the vendor is the authority on its own price, and the page
being undated does not make the price untrue. A market-wide average needs several
independent sources, because three search results are not a survey.

Nothing here knows about solar. Categories are matched from per-vertical keyword
lists, and every requirement comes from the vertical's `authority_policy`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import (AuthorityRequirement, ClaimCategory,
                            FreshnessRequirement)
from app.services.intent import normalize_query
from app.services.source_quality import SourceQuality
from app.verticals.profile import VerticalProfile


class ClaimRisk:
    """Kept as a plain namespace so existing imports keep working."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ClaimRequirements:
    """Everything a claim must satisfy before it may be stated."""

    category: ClaimCategory
    risk: str
    authority: AuthorityRequirement
    freshness: FreshnessRequirement
    min_corroborating_sources: int
    rationale: str

    def as_dict(self) -> dict:
        return {
            "category": self.category.value, "risk": self.risk,
            "authority": self.authority.value, "freshness": self.freshness.value,
            "min_corroborating_sources": self.min_corroborating_sources,
            "rationale": self.rationale,
        }


_AUTHORITY_RANK = {
    AuthorityRequirement.ANY: 0,
    AuthorityRequirement.SPECIALIST: 3,
    AuthorityRequirement.INSTITUTIONAL: 4,
    AuthorityRequirement.OFFICIAL: 5,
}

# Cross-vertical fallback. A vertical's own `claim_categories` take precedence;
# this exists so a vertical that has not enumerated its vocabulary still gets the
# legal and fiscal categories right rather than defaulting everything to GENERAL.
_UNIVERSAL_CATEGORY_HINTS: dict[ClaimCategory, tuple[str, ...]] = {
    ClaimCategory.SUBSIDY: ("prime", "primes", "subside", "subsides", "subvention",
                            "subsidie", "premie", "subsidy", "grant",
                            "certificat vert", "certificats verts",
                            "groenestroomcertificaat"),
    ClaimCategory.TAX: ("tva", "btw", "taxe", "impot", "impots", "tax",
                        "belasting", "vat"),
    ClaimCategory.REGULATION: ("loi", "legal", "legale", "obligation",
                               "obligatoire", "reglementation", "regulation",
                               "wettelijk", "verplicht", "norme", "decret",
                               "arrete"),
    ClaimCategory.GRID_RULE: ("gestionnaire de reseau", "raccordement", "compteur",
                              "injection", "prosumer", "tarif prosumer",
                              "netbeheerder", "aansluiting"),
    ClaimCategory.ELIGIBILITY: ("eligible", "eligibilite", "conditions d'octroi",
                                "eligibility", "qualify", "in aanmerking"),
    ClaimCategory.GUARANTEED_SAVINGS: ("economie garantie", "economies garanties",
                                       "rendement garanti", "guaranteed",
                                       "gegarandeerd"),
    ClaimCategory.ROI: ("retour sur investissement", "amortissement", "rentabilite",
                        "payback", "roi", "terugverdientijd"),
    ClaimCategory.ENERGY_PRICE: ("prix de l'electricite", "tarif electricite",
                                 "kwh", "prix du kwh", "elektriciteitsprijs"),
}

# Category → (risk, authority, freshness, corroboration, why).
# Overridable per vertical via `authority_policy`.
_DEFAULT_POLICY: dict[ClaimCategory, tuple[str, AuthorityRequirement,
                                           FreshnessRequirement, int, str]] = {
    ClaimCategory.SUBSIDY: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "Public aid is set by an authority and changes; only that authority "
        "establishes it, and an undated figure is unusable."),
    ClaimCategory.TAX: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "Tax rates are legal facts with effective dates."),
    ClaimCategory.REGULATION: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "A legal obligation is established by the regulator, not by a vendor."),
    ClaimCategory.GRID_RULE: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "Grid connection and metering rules come from the operator or regulator."),
    ClaimCategory.ELIGIBILITY: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "Telling a reader they qualify for something is a promise about a rule."),
    ClaimCategory.GUARANTEED_SAVINGS: (
        ClaimRisk.HIGH, AuthorityRequirement.INSTITUTIONAL,
        FreshnessRequirement.REQUIRED, 2,
        "A guarantee of financial outcome is the highest-consequence claim a "
        "commercial page can make."),
    ClaimCategory.ROI: (
        ClaimRisk.HIGH, AuthorityRequirement.INSTITUTIONAL,
        FreshnessRequirement.REQUIRED, 2,
        "Payback depends on prices and support schemes that move."),
    ClaimCategory.ENERGY_PRICE: (
        ClaimRisk.HIGH, AuthorityRequirement.INSTITUTIONAL,
        FreshnessRequirement.REQUIRED, 1,
        "Energy prices are volatile; an undated figure misleads."),
    ClaimCategory.MARKET_AVERAGE: (
        ClaimRisk.MEDIUM, AuthorityRequirement.SPECIALIST,
        FreshnessRequirement.PREFERRED, 3,
        "An average across a market needs more than one seller's page; a few "
        "search results are not a survey."),
    ClaimCategory.OBSERVED_PRICE_RANGE: (
        ClaimRisk.LOW, AuthorityRequirement.SPECIALIST,
        FreshnessRequirement.PREFERRED, 1,
        "A range reported BY a named source is a statement about what that "
        "source observed, not a claim about the market. One specialist source "
        "establishes what that source reports — and the wording must attribute "
        "it rather than promote it to an average."),
    ClaimCategory.MARKET_PRICE: (
        ClaimRisk.MEDIUM, AuthorityRequirement.SPECIALIST,
        FreshnessRequirement.PREFERRED, 2,
        "An unqualified price statement reads as market-wide; it needs more "
        "than one seller's page."),
    ClaimCategory.VENDOR_PRICE: (
        ClaimRisk.LOW, AuthorityRequirement.ANY,
        FreshnessRequirement.PREFERRED, 1,
        "A vendor is the authority on its own displayed price. It establishes "
        "that price only, never a market average."),
    ClaimCategory.PRODUCT_SPEC: (
        ClaimRisk.LOW, AuthorityRequirement.SPECIALIST,
        FreshnessRequirement.NOT_REQUIRED, 1,
        "Technical characteristics are stable and specialist sources suffice."),
    ClaimCategory.GENERAL: (
        ClaimRisk.LOW, AuthorityRequirement.ANY,
        FreshnessRequirement.NOT_REQUIRED, 1,
        "Explanatory statement with no regulatory or financial consequence."),
}

# A guaranteed FINANCIAL OUTCOME, in any word order: "rendement garanti",
# "rendement est garanti", "économies garanties". Matched by proximity rather
# than by fixed phrase, because word order varies and the promise does not.
#
# Deliberately narrow: a manufacturer's product warranty ("garantie 25 ans") is
# not a financial guarantee, and forcing it to clear an INSTITUTIONAL bar would
# refuse a claim the manufacturer is entitled to make about its own product.
_GUARANTEED_OUTCOME = re.compile(
    r"(?:garanti\w*|guaranteed|gegarandeerd)\W+(?:\w+\W+){0,3}?"
    r"(?:rendement|economie\w*|epargne|benefice|retour|savings?|returns?|roi|yield)"
    r"|(?:rendement|economie\w*|epargne|benefice|retour|savings?|returns?|roi|yield)"
    r"\W+(?:\w+\W+){0,3}?(?:garanti\w*|guaranteed|gegarandeerd)",
    re.IGNORECASE)

# VAT mentioned as a PRICE QUALIFIER is not a claim about the tax rate.
# "4 000 € TVAC", "1 000 € hors TVA" and "prix HTVA" are pricing statements; only
# a claim about the rate itself is a TAX claim. Live validation showed naive
# substring matching classifying "TVAC" as TAX (because "tva" is inside it),
# which pushed ordinary price claims to HIGH risk and blocked them.
_VAT_AS_PRICE_QUALIFIER = re.compile(
    r"\b(?:tvac|htva|hors\s+tva|tva\s+comprise|tva\s+incluse|btw\s+inbegrepen|"
    r"excl\.?\s*tva|incl\.?\s*tva)\b", re.IGNORECASE)
# A genuine tax claim names a rate.
_TAX_RATE = re.compile(
    r"\b(?:taux\s+(?:de\s+)?(?:tva|btw)|tva\s+(?:de|a|à)\s*\d|"
    r"btw[- ]tarief|vat\s+rate)\b", re.IGNORECASE)

# An explicit average: "en moyenne", "le prix moyen". These genuinely assert a
# market-wide central value and keep the strict bar.
_AVERAGE_MARKERS = ("en moyenne", "prix moyen", "cout moyen", "moyenne",
                    "gemiddeld", "on average")
# A reported RANGE: "entre X et Y", "de X à Y", "X – Y". This asserts what a
# source observed, which is a different and far more defensible statement.
_RANGE_MARKERS = ("entre", "varie entre", "varie de", "compris entre",
                  "de l'ordre de", "comptez environ", "comptez a present",
                  "generalement entre", "a partir de", "jusqu'a",
                  "tussen", "van tot", "typically between", "ranges from")
_RANGE_PATTERN = re.compile(
    r"\d[\d\s.,]*\s*(?:€|eur|euros?)?\s*(?:[-–—]|a|à|et|to|tot)\s*"
    r"\d[\d\s.,]*\s*(?:€|eur|euros?|/|par)", re.IGNORECASE)
_MARKET_MARKERS = _AVERAGE_MARKERS + _RANGE_MARKERS
# First-person / vendor-page language: "nos tarifs", "notre offre", "chez nous".
_VENDOR_MARKERS = ("nos tarifs", "nos prix", "notre offre", "notre prix",
                   "chez nous", "our price", "our pricing", "onze prijs")


def _matches_term(term: str, normalized_claim: str) -> bool:
    """Whole-word match.

    Naive substring matching made "TVAC" match "tva" and "prime" match
    "primeur". Short category keywords are exactly the ones where a substring hit
    is most likely to be wrong, so every term is anchored to word boundaries.
    """
    normalized_term = normalize_query(term)
    if not normalized_term:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
                     normalized_claim) is not None


def classify_category(claim: str, profile: VerticalProfile) -> ClaimCategory:
    """Match a claim to a category, vertical vocabulary first."""
    normalized = normalize_query(claim)

    # A guaranteed financial outcome outranks every other match: it is the
    # highest-consequence promise a commercial page can make, and it is often
    # phrased alongside pricing that would otherwise capture the claim.
    if _GUARANTEED_OUTCOME.search(normalized):
        return ClaimCategory.GUARANTEED_SAVINGS

    vat_is_price_qualifier = bool(_VAT_AS_PRICE_QUALIFIER.search(claim)) and \
        not _TAX_RATE.search(claim)

    for category_name, terms in (profile.claim_categories or {}).items():
        try:
            category = ClaimCategory(category_name.upper())
        except ValueError:
            continue
        if category is ClaimCategory.TAX and vat_is_price_qualifier:
            continue
        if any(_matches_term(term, normalized) for term in terms):
            return category

    for category, hints in _UNIVERSAL_CATEGORY_HINTS.items():
        if category is ClaimCategory.TAX and vat_is_price_qualifier:
            continue
        if any(_matches_term(hint, normalized) for hint in hints):
            return category

    # Price claims split by scope: a market average and a vendor's own price are
    # different assertions needing different evidence.
    has_money = any(token in normalized for token in ("eur", "euro", "€", "prix",
                                                      "cout", "tarif", "prijs"))
    if has_money or _has_currency(claim):
        if any(marker in normalized for marker in _VENDOR_MARKERS):
            return ClaimCategory.VENDOR_PRICE
        # An explicit average outranks a range: "le prix moyen varie entre X et Y"
        # is still an average claim and keeps the strict bar.
        if any(marker in normalized for marker in _AVERAGE_MARKERS):
            return ClaimCategory.MARKET_AVERAGE
        if (_RANGE_PATTERN.search(claim)
                or any(marker in normalized for marker in _RANGE_MARKERS)):
            return ClaimCategory.OBSERVED_PRICE_RANGE
        # An unqualified price claim in an editorial context reads as market-wide.
        return ClaimCategory.MARKET_PRICE

    return ClaimCategory.GENERAL


def _has_currency(claim: str) -> bool:
    return any(symbol in claim for symbol in ("€", "$", "£"))


def requirements_for(claim: str, profile: VerticalProfile) -> ClaimRequirements:
    """Full requirement set for one atomic claim."""
    category = classify_category(claim, profile)
    risk, authority, freshness, corroboration, rationale = _DEFAULT_POLICY[category]

    override = (profile.authority_policy or {}).get(category.value)
    if isinstance(override, dict):
        if "authority" in override:
            try:
                authority = AuthorityRequirement(str(override["authority"]).upper())
            except ValueError:
                pass
        if "freshness" in override:
            try:
                freshness = FreshnessRequirement(str(override["freshness"]).upper())
            except ValueError:
                pass
        if "risk" in override:
            risk = str(override["risk"]).upper()
        if "min_corroborating_sources" in override:
            try:
                corroboration = max(1, int(override["min_corroborating_sources"]))
            except (TypeError, ValueError):
                pass
        if override.get("rationale"):
            rationale = str(override["rationale"])

    return ClaimRequirements(category=category, risk=risk, authority=authority,
                             freshness=freshness,
                             min_corroborating_sources=corroboration,
                             rationale=rationale)


def authority_is_sufficient(requirement: AuthorityRequirement,
                            quality: SourceQuality) -> bool:
    return quality.rank >= _AUTHORITY_RANK[requirement]


def acceptable_qualities(requirement: AuthorityRequirement) -> list[SourceQuality]:
    return [q for q in SourceQuality
            if q.rank >= _AUTHORITY_RANK[requirement] and q is not SourceQuality.UNKNOWN]


def summarize(requirements: list[ClaimRequirements]) -> dict:
    risks: dict[str, int] = {}
    categories: dict[str, int] = {}
    for requirement in requirements:
        risks[requirement.risk] = risks.get(requirement.risk, 0) + 1
        categories[requirement.category.value] = \
            categories.get(requirement.category.value, 0) + 1
    return {"counts": risks, "high_risk_count": risks.get(ClaimRisk.HIGH, 0),
            "categories": categories}
