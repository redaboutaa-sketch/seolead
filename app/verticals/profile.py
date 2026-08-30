"""Vertical profiles, loaded from YAML.

This module is the reason the pipeline has no `if solar:` anywhere. Everything a
vertical needs in order to behave differently — its languages, its conversion
goals, the claims it may not make, the content types it prefers — is data. Adding
AI_TRAINING_FR means adding a file here and a row in `vertical`, and changing no
Python.

`restricted_claims` is the load-bearing field. For solar it names subsidies,
tariffs and ROI; the QA layer treats any of those appearing as an asserted figure
without dated evidence as a blocking issue.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.core.enums import ContentType, PHASE2_CONTENT_TYPES
from app.core.errors import InvalidVertical

PROFILE_DIR = Path(__file__).resolve().parents[2] / "config" / "verticals"


class CTAOption(BaseModel):
    code: str
    label: str
    intents: list[str] = Field(default_factory=list)


class VerticalProfile(BaseModel):
    code: str
    name: str
    market: str
    languages: list[str]
    default_language: str
    target_audience: str
    business_objective: str
    conversion_goals: list[str] = Field(default_factory=list)
    cta_options: list[CTAOption] = Field(default_factory=list)
    preferred_content_types: list[ContentType] = Field(default_factory=list)
    # Topics that may not be asserted without dated, sourced evidence.
    restricted_claims: list[str] = Field(default_factory=list)
    # Substrings that, if they appear in a draft, are always a blocking issue.
    forbidden_phrases: list[str] = Field(default_factory=list)
    commercial_terms: list[str] = Field(default_factory=list)
    comparison_terms: list[str] = Field(default_factory=list)
    # Sub-market localities only — regions and cities. A query naming one of these
    # genuinely wants locally-specific content.
    local_terms: list[str] = Field(default_factory=list)
    # The market's own names ("Belgique", "België"). Deliberately NOT local terms:
    # nearly every query in a national vertical carries the country name, and
    # treating that as local intent would classify the entire vertical as LOCAL and
    # route every page to the wrong content type and the wrong CTA.
    market_terms: list[str] = Field(default_factory=list)

    # ── Provider policy (Phase 3) ────────────────────────────────────────────
    # Whether community/discussion research is worth paying for in this vertical.
    # Phase 2 measured that Last30Days indexes technical communities: valuable
    # when the audience IS that community, actively harmful for consumer
    # commercial queries, where it supplied a racing-game post as the only
    # "evidence". Off by default.
    community_research_enabled: bool = False
    # Keyword metrics cost money per call and are not needed on every job.
    keyword_metrics_enabled: bool = True
    # Domains whose claims this vertical treats as authoritative regardless of the
    # generic classifier — regulators and grid operators for the market.
    authoritative_domains: list[str] = Field(default_factory=list)

    # ── Claim policy (Phase 3.1) ─────────────────────────────────────────────
    # category → vocabulary that identifies it. Matched before the cross-vertical
    # fallback, so a vertical can name its own regulatory language.
    claim_categories: dict[str, list[str]] = Field(default_factory=dict)
    # category → {authority, freshness, risk, min_corroborating_sources,
    # rationale}. Overrides the cross-vertical defaults in `claim_policy`.
    authority_policy: dict[str, dict] = Field(default_factory=dict)
    # Categories whose answer is set REGIONALLY in this market. In Belgium the
    # premium, the prosumer tariff, the green certificates and therefore the
    # payback all differ by region; in a unitary market the same list would be
    # empty. Nothing in the code knows that — it is configuration, like every
    # other statement about a market.
    regionally_determined_claims: list[str] = Field(default_factory=list)
    # Where to look when a HIGH-risk claim is unresolved. A placeholder here is
    # deliberate: it can be populated without touching orchestration code.
    official_source_policy: dict = Field(default_factory=dict)

    # ── Price answering (Phase 3.4) ──────────────────────────────────────────
    # How many comparable observations before a range may be stated, and whether
    # this vertical's core query is a price question at all. Configuration, so no
    # Solar-specific rule reaches the orchestrator.
    price_policy: dict = Field(default_factory=dict)

    # ── Matching vocabulary (Phase 3.3) ──────────────────────────────────────
    # Terms that are CONTEXT rather than TOPIC in this vertical. `solaire` is
    # generic for Solar Belgium and highly discriminative for a roofing vertical,
    # so this is per-vertical rather than a global list.
    generic_terms: list[str] = Field(default_factory=list)
    # Multi-word domain concepts that act as a claim's semantic head:
    # "tarif prosumer", "retour sur investissement". A passage must contain the
    # claim's head before it can be treated as bearing on the same proposition.
    concept_phrases: list[str] = Field(default_factory=list)

    def official_domains(self) -> list[str]:
        """Domains a targeted authoritative search may be restricted to.

        Accepts both configuration shapes: the Phase 3.1 flat list of strings and
        the Phase 3.2 entries carrying authority metadata. Supporting both means a
        vertical that has not been migrated keeps its authorities rather than
        silently losing them.
        """
        names: list[str] = []
        for entry in (self.official_source_policy or {}).get("domains") or []:
            if isinstance(entry, str):
                names.append(entry.strip().lower())
            elif isinstance(entry, dict) and entry.get("domain"):
                names.append(str(entry["domain"]).strip().lower())
        names.extend(d.strip().lower() for d in self.authoritative_domains)
        return list(dict.fromkeys(n for n in names if n))

    def selectable_content_types(self) -> list[ContentType]:
        """Only Phase 2 types are selectable, whatever the profile lists.

        A profile naming SIMULATOR must not cause the selector to emit one before
        the QA rules and conversion components for simulators exist.
        """
        preferred = [t for t in self.preferred_content_types if t in PHASE2_CONTENT_TYPES]
        return preferred or [ContentType.ARTICLE]


@lru_cache(maxsize=32)
def load_profile(code: str) -> VerticalProfile:
    path = PROFILE_DIR / f"{code.lower()}.yaml"
    if not path.is_file():
        raise InvalidVertical(f"no vertical profile for code {code!r}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = VerticalProfile.model_validate(data)
    if profile.code != code:
        raise InvalidVertical(
            f"profile file {path.name} declares code {profile.code!r}, expected {code!r}"
        )
    return profile


def available_profiles() -> list[str]:
    if not PROFILE_DIR.is_dir():
        return []
    return sorted(p.stem.upper() for p in PROFILE_DIR.glob("*.yaml"))
