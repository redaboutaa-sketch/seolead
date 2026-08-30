"""Regional scope.

Belgium is not one regulatory unit for solar. Wallonia, Flanders and Brussels each
set their own premiums, and their grid operators run different metering rules. A
Wallonian premium generalised to "Belgium" is a false statement of law, and it is
exactly the kind of claim this pipeline exists to refuse.

So scope is a first-class property of a claim and of the evidence supporting it,
and a claim may only be supported by evidence whose scope *covers* it. National
evidence covers a regional claim; regional evidence never covers a national one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.intent import normalize_query


class Region(StrEnum):
    """ISO 3166-2 style codes. `BE` means the whole country."""

    BE = "BE"
    BE_WAL = "BE-WAL"
    BE_BRU = "BE-BRU"
    BE_VLG = "BE-VLG"
    FR = "FR"
    NL = "NL"
    UNKNOWN = "UNKNOWN"

    @property
    def parent(self) -> "Region | None":
        return {
            Region.BE_WAL: Region.BE,
            Region.BE_BRU: Region.BE,
            Region.BE_VLG: Region.BE,
        }.get(self)

    @property
    def is_subnational(self) -> bool:
        return self.parent is not None

    def covers(self, other: "Region") -> bool:
        """Whether evidence scoped to `self` can support a claim scoped to `other`.

        National evidence covers a regional claim: a federal VAT rate applies in
        Wallonia. The reverse is false — a Walloon premium says nothing about
        Flanders — and that asymmetry is the whole point of this method.
        """
        if self is Region.UNKNOWN or other is Region.UNKNOWN:
            return False
        if self is other:
            return True
        return other.parent is self


# Region vocabulary, matched against claim and page text. Data, not logic.
_REGION_TERMS: dict[Region, tuple[str, ...]] = {
    Region.BE_WAL: ("wallonie", "wallonne", "wallon", "region wallonne",
                    "wallonia", "waals gewest", "cwape", "ores", "resa"),
    Region.BE_BRU: ("bruxelles", "bruxelloise", "bruxellois", "brussels",
                    "region de bruxelles-capitale", "brussel", "brugel",
                    "sibelga", "leefmilieu brussel", "bruxelles environnement"),
    Region.BE_VLG: ("flandre", "flamande", "flamand", "vlaanderen", "vlaams",
                    "flanders", "vreg", "fluvius", "energiesparen"),
    Region.BE: ("belgique", "belgie", "belgium", "federal", "federale",
                "national", "nationale"),
}


@dataclass(frozen=True)
class RegionMatch:
    region: Region
    evidence: str

    def as_dict(self) -> dict:
        return {"region": self.region.value, "matched_on": self.evidence}


def _names(region: Region, normalized: str) -> str | None:
    """The first vocabulary term of `region` present in `normalized`, if any."""
    for term in _REGION_TERMS[region]:
        if re.search(rf"(?<!\w){re.escape(normalize_query(term))}(?!\w)",
                     normalized):
            return term
    return None


def names_region(text: str, region: Region) -> bool:
    """Whether this text names this region, whatever else it also names.

    Distinct from `detect_region`, which picks ONE scope for a whole page. Here
    the question is per-sentence and additive: a ventilated sentence — « en
    Wallonie : X ; en Flandre : Y » — names both, and both answers are yes.
    """
    if region is Region.UNKNOWN:
        return False
    return _names(region, normalize_query(text or "")) is not None


def detect_region(text: str, *, default: Region = Region.UNKNOWN) -> RegionMatch:
    """Detect the region a text is scoped to.

    One sub-national region named, and it wins over the country: a page that says
    both "Belgique" and "Wallonie" is almost always describing a Walloon rule in a
    Belgian context, and scoping it to the country would over-generalise it.

    SEVERAL sub-national regions named, and the text is national. This is the
    correction of a real defect: the previous version returned whichever region
    came first in the iteration order, which was always BE-WAL. A page comparing
    the Walloon, Brussels and Flemish schemes — precisely the Belgium-wide source
    a Belgium-wide claim needs — was stamped Walloon, and every HIGH-risk claim it
    supported was then rejected for "regional scope mismatch: BE-WAL evidence
    cannot establish a BE-wide claim". The label was an artefact of enum ordering,
    not of the text.
    """
    normalized = normalize_query(text or "")
    if not normalized:
        return RegionMatch(default, "")

    subnational = [(region, term)
                   for region in (Region.BE_WAL, Region.BE_BRU, Region.BE_VLG)
                   if (term := _names(region, normalized)) is not None]

    if len(subnational) == 1:
        region, term = subnational[0]
        return RegionMatch(region, term)

    if len(subnational) > 1:
        return RegionMatch(Region.BE,
                           ", ".join(term for _, term in subnational))

    national = _names(Region.BE, normalized)
    if national is not None:
        return RegionMatch(Region.BE, national)

    return RegionMatch(default, "")


def region_for_market(market: str) -> Region:
    try:
        return Region(market.upper())
    except ValueError:
        return Region.UNKNOWN


def scope_is_compatible(evidence_region: Region, claim_region: Region) -> bool:
    return evidence_region.covers(claim_region)


def describe_mismatch(evidence_region: Region, claim_region: Region) -> str:
    if evidence_region is Region.UNKNOWN:
        return "evidence carries no identifiable regional scope"
    if claim_region is Region.UNKNOWN:
        return "claim carries no identifiable regional scope"
    if evidence_region.is_subnational and claim_region is evidence_region.parent:
        return (f"{evidence_region.value} evidence cannot establish a "
                f"{claim_region.value}-wide claim")
    return (f"{evidence_region.value} evidence does not cover a "
            f"{claim_region.value} claim")
