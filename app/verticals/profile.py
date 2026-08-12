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
