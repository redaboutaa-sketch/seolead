"""Search context — where and how a query is actually searched.

Belgium is not a generic global Google search, and treating it as one would return
a SERP no Belgian searcher ever sees. Worse for this pilot: Belgium is genuinely
multilingual, so `BE/fr` and `BE/nl` are different SERPs for the same product.

Nothing Belgian is hard-coded into the provider. The provider takes a
`SearchContext`; this module maps a (market, language) pair onto one, and the table
is data.

Location codes are DataForSEO's Google geo-targeting codes. Belgium is 2056,
verified against DataForSEO's locations documentation.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import SeoLeadError


class UnsupportedSearchContext(SeoLeadError):
    code = "INVALID_REQUEST"


@dataclass(frozen=True)
class SearchContext:
    """One concrete search configuration."""

    location_code: int
    location_name: str
    language_code: str
    language_name: str
    device: str = "desktop"
    os: str = "windows"
    se_domain: str = "google.com"

    def as_dict(self) -> dict:
        return {
            "location_code": self.location_code,
            "location_name": self.location_name,
            "language_code": self.language_code,
            "language_name": self.language_name,
            "device": self.device,
            "se_domain": self.se_domain,
        }


# (market, language) → context. Adding France or German-speaking Belgium is a row.
_CONTEXTS: dict[tuple[str, str], SearchContext] = {
    ("BE", "fr"): SearchContext(2056, "Belgium", "fr", "French",
                                se_domain="google.be"),
    ("BE", "nl"): SearchContext(2056, "Belgium", "nl", "Dutch",
                                se_domain="google.be"),
    ("BE", "de"): SearchContext(2056, "Belgium", "de", "German",
                                se_domain="google.be"),
    ("FR", "fr"): SearchContext(2250, "France", "fr", "French",
                                se_domain="google.fr"),
    ("NL", "nl"): SearchContext(2528, "Netherlands", "nl", "Dutch",
                                se_domain="google.nl"),
}


def get_search_context(market: str, language: str, *,
                       device: str = "desktop") -> SearchContext:
    key = (market.upper(), language.lower())
    context = _CONTEXTS.get(key)
    if context is None:
        raise UnsupportedSearchContext(
            f"no search context configured for market={market!r} "
            f"language={language!r}; configured: "
            f"{', '.join(f'{m}/{l}' for m, l in sorted(_CONTEXTS))}"
        )
    if device == context.device:
        return context
    # Mobile is a different SERP, not a variant of the same one.
    return SearchContext(
        location_code=context.location_code, location_name=context.location_name,
        language_code=context.language_code, language_name=context.language_name,
        device=device, os="android" if device == "mobile" else "windows",
        se_domain=context.se_domain,
    )


def supported_contexts() -> list[str]:
    return [f"{m}/{l}" for m, l in sorted(_CONTEXTS)]
