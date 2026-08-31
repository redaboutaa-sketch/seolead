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
    # Whether this market sets the answer REGIONALLY. Configuration, not code:
    # a Belgian premium is regional, a French one is not, and nothing here knows
    # which. When true, the claim is written in regional scope and a country-wide
    # phrasing is only admissible from a genuinely national source — or from a
    # sentence that carries the breakdown itself.
    regionally_determined: bool = False

    def as_dict(self) -> dict:
        return {
            "category": self.category.value, "risk": self.risk,
            "authority": self.authority.value, "freshness": self.freshness.value,
            "min_corroborating_sources": self.min_corroborating_sources,
            "rationale": self.rationale,
            "regionally_determined": self.regionally_determined,
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
    # `kwh` alone used to sit in this list, among three phrases that all name a
    # PRICE. It is a unit, not a price: every statement of a QUANTITY of energy
    # ("la production était de 16,8 kWh/jour", "un ménage consomme 3 500 kWh par
    # an") became an electricity-tariff claim — HIGH risk, institutional source
    # required, dated. Those are the ordinary, useful sentences an article about
    # solar output is made of, and the requirement they inherited was
    # unmeetable. A kWh becomes a price claim only when the text says so.
    ClaimCategory.ENERGY_PRICE: ("prix de l'electricite", "tarif electricite",
                                 "prix du kwh", "prix au kwh", "cout du kwh",
                                 "tarif du kwh", "elektriciteitsprijs",
                                 "prijs per kwh"),
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
    ClaimCategory.FINANCING_PROMISE: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "A promise about our own commercial offer — free, no upfront payment, "
        "self-financing, application fees, instalments covered by savings. "
        "Research can never establish it, because the source of an offer is the "
        "company making it: the OFFICIAL bar keeps it unassertable from "
        "retrieved pages, and the only legitimate path into a page is the "
        "validated first-party offer registry."),
    ClaimCategory.CONTRACT_PROMISE: (
        ClaimRisk.HIGH, AuthorityRequirement.OFFICIAL,
        FreshnessRequirement.REQUIRED, 1,
        "A promise about the terms of the provider's contract — a tariff "
        "called fixed or guaranteed over a duration, a buyout trajectory, an "
        "automatic ownership transfer. Same construction as "
        "FINANCING_PROMISE: no researched source can establish it, so the "
        "OFFICIAL bar keeps it unassertable from retrieval; the only path in "
        "is the offer registry with contract evidence and a legal verdict on "
        "the exact wording."),
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
    r"\W+(?:\w+\W+){0,3}?(?:garanti\w*|guaranteed|gegarandeerd)"
    # « Vous économisez forcément par rapport au marché » — the guarantee said
    # without the word. Measured GENERAL/LOW on 2026-08-31; the certainty
    # adverb next to a savings verb IS the guarantee.
    r"|econom\w+\W+(?:\w+\W+){0,2}?"
    r"(?:forcement|necessairement|assurement|a\s+coup\s+sur|quoi\s+qu)"
    r"|(?:forcement|necessairement|assurement)\W+(?:\w+\W+){0,2}?econom\w+",
    re.IGNORECASE)

# ── Financing promises ───────────────────────────────────────────────────────
# Measured 2026-08-31 (audit §2): « Panneaux solaires gratuits : vous ne payez
# rien », « sans apport », « s'autofinance » all classified GENERAL / LOW / ANY.
# `_GUARANTEED_OUTCOME` only knows « garanti* », and the highest-consequence
# commercial promise this vertical can make sailed under every bar.
#
# The vocabulary, and its deliberate edges:
#   - « gratuitement » alone is NOT caught: « produire gratuitement de
#     l'électricité » is a real SUPPORTED ledger claim about post-payback
#     production, not an offer. It is caught only next to installé/posé/fourni.
#   - « 0 € » must not match « 0,05 €/kWh » — a tariff is not a giveaway.
#   - « sans aide ni subside » is a statement about public support, not about
#     our offer, and stays untouched.
# Every edge above is pinned by a regression corpus of real ledger texts.
# The typographic apostrophe survives `normalize_query`, so every pattern that
# crosses one accepts both spellings — « s’autofinance » escaped the first
# version of this regex for exactly that reason.
_APO = r"[’']"
_FINANCING_PROMISE = re.compile(
    rf"\bsans\s+(?:apport|avance|epargne|mise\s+de\s+fonds"
    rf"|rien\s+(?:avancer|payer|debourser)"
    rf"|(?:investissement|economies?|capital)\s+(?:initial|de\s+depart|prealable)"
    rf"|sortir\s+d{_APO}\s*argent"
    rf"|debourser)"
    rf"|\baucun\w*\s+(?:apport|epargne|avance|investissement|economie\w*"
    rf"|mise\s+de\s+fonds|capital)"
    rf"|\bpas\s+besoin\s+d{_APO}\s*(?:economie\w*|epargne|apport|argent|capital)"
    rf"|\b(?:0|zero)\s*(?:€|eur(?:os?)?\b)(?![\d.,]\d)"
    rf"|\bzero\s+(?:investissement|apport|avance|epargne|frais)"
    rf"|\bne\s+(?:vous\s+)?coute\w*\s+rien"
    rf"|\bgratuit(?:e|s|es)?\b"
    rf"|\b(?:installe|pose|fourni|place)\w*\s+gratuitement\b"
    rf"|\bgratuitement\s+(?:installe|pose|fourni|place)\w*"
    rf"|\bs{_APO}\s*autofinance\w*\b|\bautofinanc\w+\b"
    rf"|\bse\s+(?:rembours|financ|pai|pay)\w+\s+tout\w*\s+seul\w*"
    rf"|\bmensualite\w*\b\W+(?:\w+\W+){{0,10}}?econom\w+"
    rf"|\beconom\w+\W+(?:\w+\W+){{0,10}}?mensualite\w*"
    rf"|\b(?:couvr|compens)\w+\W+(?:\w+\W+){{0,4}}?mensualite\w*"
    rf"|\b(?:rembours|financ|pay|pai)\w+\s+par\s+"
    rf"(?:les?\s+|la\s+|votre\s+|vos\s+)?(?:econom\w+|factur\w+)"
    rf"|\b(?:factur|econom)\w+\W+(?:\w+\W+){{0,2}}?(?:financ|rembours)\w+"
    rf"\W+(?:\w+\W+){{0,3}}?(?:installation|panneaux|projet|systeme)"
    rf"|\bfrais\s+de\s+dossier\b"
    # SG Solution hardening (2026-08-31). « Aucun crédit bancaire n'est
    # nécessaire » measured GENERAL/LOW; « Vous payez seulement 150 € »
    # measured MARKET_PRICE/MEDIUM. Both are promises about how the reader
    # pays — the first family this category exists for.
    rf"|\b(?:aucun|sans|pas\s+de)\s+credit(?:\s+bancaire)?\b"
    rf"|\bsans\s+passer\s+par\s+(?:la|une|votre)\s+banque"
    rf"|\bvous\s+(?:ne\s+)?payez\s+(?:que|seulement)\b"
    rf"|\bne\s+(?:vous\s+)?coute\w*\s+que\b",
    re.IGNORECASE)

# ── Contract promises (SG Solution model, 2026-08-31) ────────────────────────
# The terms of the provider's contract, promised as certainties: a tariff
# called fixed or guaranteed over a duration, a bill that "can never rise
# again", a buyout price trajectory, an automatic ownership transfer. Measured
# before this block existed: « Le tarif est garanti à 0,27 €/kWh pendant
# 25 ans » → MARKET_PRICE/MEDIUM; « Votre facture ne pourra plus augmenter »
# and « Après 25 ans, l'installation devient gratuitement votre propriété » →
# GENERAL/LOW. All of them are first-party contract assertions that no
# researched source can establish — only the offer registry, with contract
# evidence (`offer.evidence.contract_reference`) and a legal verdict on the
# exact wording.
#
# Deliberate edge: a product warranty (« garantie 25 ans sur les panneaux »,
# « garantie constructeur ») is the manufacturer's claim about its product,
# not a promise about OUR contract's terms — the tariff/price/bill nouns are
# what make the difference, and the regression corpus pins that a warranty
# stays out of here.
_CONTRACT_PROMISE = re.compile(
    rf"\b(?:tarif|prix|montant|mensualite)\w*\W+(?:\w+\W+){{0,4}}?"
    rf"(?:garanti\w*|fixe\w*|bloque\w*|verrouille\w*)"
    rf"|\b(?:garanti\w*|fixe\w*|bloque\w*)\W+(?:\w+\W+){{0,4}}?"
    rf"(?:tarif|prix|€|eur\b|euros?\b|kwh)"
    rf"|\b(?:facture|prix|tarif)\w*\W+(?:\w+\W+){{0,3}}?"
    rf"(?:ne\s+pourra\w*\s+plus|n{_APO}\s*augmentera\w*\s+(?:plus|jamais)"
    rf"|ne\s+(?:peut|pourront|pourra)\s+(?:plus|pas)\s+augmenter)"
    rf"|\bprotege\w*\s+(?:de|contre)\s+(?:toutes?\s+)?(?:les\s+)?hausses?"
    rf"|\ba\s+l{_APO}\s*abri\s+des\s+hausses?"
    rf"|\bprix\s+de\s+rachat\b|\boption\s+de\s+rachat\b"
    rf"|\brachat\w*\W+(?:\w+\W+){{0,4}}?(?:baisse|diminue|reduit)\w*"
    rf"|\bracheter\s+(?:l{_APO}\s*|votre\s+|son\s+)?installation"
    rf"|\bdev(?:ient|enez|iendrez)\s+(?:gratuitement\s+|automatiquement\s+)?"
    rf"(?:votre\s+|sa\s+)?propri(?:ete|etaire)"
    rf"|\bpropri(?:ete|etaire)\W+(?:\w+\W+){{0,4}}?"
    rf"(?:au\s+terme|apres\s+\d+\s+ans|automatiquement|gratuitement)"
    rf"|\btransfert\s+(?:automatique\s+)?de\s+propriete",
    re.IGNORECASE)

# ── Acceptance promises (SG Solution model, 2026-08-31) ──────────────────────
# « Tout le monde est accepté », « Votre banque vous refuse ? SG Solution vous
# accepte », « Même si vous n'êtes pas finançable, vous êtes accepté » — all
# measured GENERAL/LOW. An acceptance promise is an eligibility claim at its
# most consequential: the operator prequalifies, the provider DECIDES, and a
# page has no standing to promise anyone's decision. Routed to ELIGIBILITY
# (HIGH / OFFICIAL / dated), and the unconditional form blocks at QA.
_ACCEPTANCE_PROMISE = re.compile(
    rf"\btout\s+le\s+monde\s+est\s+(?:accepte|eligible)\w*"
    rf"|\btous\s+(?:les\s+dossiers\s+sont\s+)?acceptes\b"
    rf"|\bvous\s+(?:etes|serez)\s+accepte\w*"
    rf"|\brefus\w*\W+(?:\w+\W+){{0,6}}?accept\w+"
    rf"|\baccept\w+\W+(?:\w+\W+){{0,6}}?refus\w*"
    # « SG Solution vous accepte. » stands alone once the sentence splitter
    # separates it from « Votre banque vous refuse ? » — the promise must be
    # caught per sentence, not per pairing.
    rf"|\bvous\s+accept(?:e|ons|era|erons|eront)\b"
    rf"|\b(?:pas|non)\s+financable\w*\W+(?:\w+\W+){{0,6}}?accepte\w*"
    rf"|\baucun\w*\s+(?:verification|controle|condition)\w*\s+"
    rf"(?:financier\w*|de\s+solvabilite|n{_APO}\s*est\s+(?:necessaire|requis))"
    rf"|\bsans\s+(?:aucune\s+)?(?:verification|condition)\s+"
    rf"(?:financiere|de\s+solvabilite|de\s+revenus)",
    re.IGNORECASE)


def is_contract_promise(text: str) -> bool:
    """Whether this text promises terms of the provider's contract."""
    return bool(_CONTRACT_PROMISE.search(normalize_query(text or "")))


def is_unconditional_contract_promise(text: str) -> bool:
    """The blocking form: a contract-terms promise with no condition anywhere.

    « Selon le contrat proposé, le tarif peut être fixé pour la durée » names
    its conditions and passes; « Le tarif est garanti pendant 25 ans » does
    not. The wording that MAY ultimately be published for these terms belongs
    to the legal verdict matrix, never to a generated sentence.
    """
    normalized = normalize_query(text or "")
    return bool(_CONTRACT_PROMISE.search(normalized)) and \
        not _CONDITIONAL_MARKERS.search(normalized)


def is_unconditional_outcome_promise(text: str) -> bool:
    """A guaranteed financial outcome with no condition — for the QA layer.

    The claim ledger already refuses GUARANTEED_SAVINGS without institutional
    corroboration in the BODY; this predicate exists because the QA guard also
    reads title and meta description, where no ledger looks. « Vous économisez
    forcément par rapport au marché » in a meta description is the guarantee
    at its most visible.
    """
    normalized = normalize_query(text or "")
    return bool(_GUARANTEED_OUTCOME.search(normalized)) and \
        not _CONDITIONAL_MARKERS.search(normalized)


def is_acceptance_promise(text: str) -> bool:
    """Whether this text promises acceptance or unconditional eligibility."""
    return bool(_ACCEPTANCE_PROMISE.search(normalize_query(text or "")))


def is_unconditional_acceptance_promise(text: str) -> bool:
    """The blocking form: acceptance promised with no condition, no analysis.

    The honest sentence exists and passes: « Selon l'analyse de votre dossier,
    votre demande peut être acceptée. » Final eligibility is the provider's
    decision after analysis; a page that promises it is wrong before it is
    checked, whatever the registry says.
    """
    normalized = normalize_query(text or "")
    return bool(_ACCEPTANCE_PROMISE.search(normalized)) and \
        not _CONDITIONAL_MARKERS.search(normalized)

# What separates a controlled, conditional formulation from a promise. « Selon
# le financement, …, les économies PEUVENT contribuer à compenser tout ou
# partie de la mensualité » is a sentence this vertical is allowed to need;
# « l'installation s'autofinance » is not. The subject is not banned — the
# unconditional form of it is.
_CONDITIONAL_MARKERS = re.compile(
    r"\bselon\b|\ben\s+fonction\s+de\b|\bsous\s+conditions?\b"
    r"|\bpeut\b|\bpeuvent\b|\bpourrai(?:t|ent)\b|\bpotentiellement\b"
    # « même si » is not a condition — it is a concession that STRENGTHENS the
    # promise (« Même si vous n'êtes pas finançable, vous êtes accepté » rode
    # the bare `si` exemption straight past the acceptance guard, measured
    # 2026-08-31). The lookbehind keeps the real conditional « si » working.
    r"|\bdans\s+certains\s+cas\b|(?<!meme )\bsi\s|\bau\s+cas\s+par\s+cas\b"
    r"|\btout\s+ou\s+partie\b|\beligib\w+\b",
    re.IGNORECASE)


def is_financing_promise(text: str) -> bool:
    """Whether this text talks in financing-offer terms at all."""
    return bool(_FINANCING_PROMISE.search(normalize_query(text or "")))


def is_unconditional_financing_promise(text: str) -> bool:
    """The blocking form: an offer promise with no conditional anywhere near it.

    Used by SEO QA to refuse a generated sentence outright. Classification does
    not make this distinction — conditional or not, a financing claim is
    FINANCING_PROMISE and HIGH — because a conditional promise still needs the
    offer registry behind it; this predicate only decides which failure the
    operator is shown.
    """
    normalized = normalize_query(text or "")
    return bool(_FINANCING_PROMISE.search(normalized)) and \
        not _CONDITIONAL_MARKERS.search(normalized)


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

# Money vocabulary, anchored at word boundaries for exactly the reason spelled
# out on `_matches_term` — and violated three lines below it until now. The
# fallback used substring matching, so "eur" matched *chaleur*, *onduleur*,
# *meilleur*, *heures*, *capteur* and *valeur*. Ordinary sentences about how a
# panel behaves ("les panneaux n'aiment pas les fortes chaleurs") became
# market-price claims requiring three corroborating sources, and then failed for
# want of pricing evidence that could never exist for them. The stems that do
# take suffixes keep them; only the accidental collisions are gone. The euro
# SYMBOL is deliberately absent: it is not a word, and `_has_currency` already
# catches it in "7 000€" where a word boundary never could.
_MONEY_WORD = re.compile(
    r"(?<!\w)(?:euros?|prix|tarif(?:s|aires?)?|"
    r"cout(?:s|e|ent|er|era|eront|eux|euses?)?|prijs|prijzen|kosten?)(?!\w)")


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

    # Financing-offer vocabulary outranks the per-vertical vocabulary for the
    # same reason: « frais de dossier de 150 € » would otherwise fall to
    # ELIGIBILITY or a price category, and « installation gratuite » to GENERAL.
    # First-match order is what mislabelled a payback claim GRID_RULE on
    # 2026-08-31; the categories that decide the strictest bars are checked
    # before any dictionary is consulted.
    if _FINANCING_PROMISE.search(normalized):
        return ClaimCategory.FINANCING_PROMISE

    # Contract-terms promises next, for the same reason: « Le tarif est
    # garanti à 0,27 €/kWh pendant 25 ans » otherwise falls through to
    # MARKET_PRICE at MEDIUM, which is two bars too low for a first-party
    # contract assertion.
    if _CONTRACT_PROMISE.search(normalized):
        return ClaimCategory.CONTRACT_PROMISE

    # An acceptance promise is an eligibility claim at its most consequential
    # — and the eligibility DICTIONARY only knows the word « éligible », so
    # « tout le monde est accepté » sailed to GENERAL before this check.
    if _ACCEPTANCE_PROMISE.search(normalized):
        return ClaimCategory.ELIGIBILITY

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
    if _MONEY_WORD.search(normalized) or _has_currency(claim):
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
                             rationale=rationale,
                             regionally_determined=is_regionally_determined(
                                 category, profile))


def is_regionally_determined(category: ClaimCategory,
                             profile: VerticalProfile | None) -> bool:
    """Whether this market sets this category's answer region by region."""
    declared = getattr(profile, "regionally_determined_claims", None) or []
    return category.value in {str(c).upper() for c in declared}


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
