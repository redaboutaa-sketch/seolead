"""Search-intent classification and content-type selection.

Deterministic and vertical-driven. The vocabulary comes from the vertical profile,
so classifying a French solar query and an English generic one runs the same code
over different data — which is what the multi-vertical test asserts.

An LLM would classify intent more subtly, but intent decides content type, which
decides the whole downstream shape. A deterministic rule an operator can read and
correct is worth more here than a marginally better guess they cannot audit.
"""
from __future__ import annotations

import re
import unicodedata

from app.core.enums import ContentType, SearchIntent
from app.verticals.profile import VerticalProfile


def normalize_query(query: str) -> str:
    """Casefold, strip accents, collapse whitespace.

    Accent-stripping matters for the French pilot: an operator typing "rentabilite"
    and "rentabilité" means the same seed, and treating them as two would double
    the research spend for one intent.
    """
    decomposed = unicodedata.normalize("NFKD", query.casefold())
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents).strip()


def _contains_any(haystack: str, needles: list[str]) -> bool:
    return any(normalize_query(n) in haystack for n in needles if n)


def classify_intent(query: str, profile: VerticalProfile) -> SearchIntent:
    """Classify intent from the vertical's own vocabulary.

    Market names are stripped first. "prix panneaux solaires Belgique" is a
    national commercial query, and letting the country name imply local intent
    would make almost every query in a national vertical LOCAL — which would send
    them all to the wrong content type and the wrong call to action.
    """
    normalized = normalize_query(query)
    for term in profile.market_terms:
        normalized = normalized.replace(normalize_query(term), " ")
    normalized = " ".join(normalized.split())

    if _contains_any(normalized, profile.comparison_terms):
        return SearchIntent.COMMERCIAL
    if _contains_any(normalized, profile.commercial_terms):
        # A price query naming an actual region or city is local commercial intent.
        # It is recorded as LOCAL, but LOCAL_PAGE stays unselectable in Phase 2.
        if _contains_any(normalized, profile.local_terms):
            return SearchIntent.LOCAL
        return SearchIntent.COMMERCIAL
    if re.search(r"\b(comment|pourquoi|qu'est|quest|what|why|how|hoe|waarom)\b", normalized):
        return SearchIntent.INFORMATIONAL
    if _contains_any(normalized, profile.local_terms):
        return SearchIntent.LOCAL
    return SearchIntent.INFORMATIONAL


def select_content_type(
    query: str, intent: SearchIntent, profile: VerticalProfile
) -> ContentType:
    """Pick a content type from intent, restricted to what Phase 2 supports.

    The mission's rule is that intent decides the type and that not everything is
    an ARTICLE. A comparison query becomes a COMPARISON, a commercial query a
    LANDING_PAGE, an explanatory one a GUIDE — and ARTICLE is the residual, not the
    default.
    """
    allowed = set(profile.selectable_content_types())
    normalized = normalize_query(query)

    def first_allowed(*candidates: ContentType) -> ContentType | None:
        for candidate in candidates:
            if candidate in allowed:
                return candidate
        return None

    chosen: ContentType | None = None

    if _contains_any(normalized, profile.comparison_terms):
        chosen = first_allowed(ContentType.COMPARISON, ContentType.GUIDE)
    elif intent in (SearchIntent.COMMERCIAL, SearchIntent.TRANSACTIONAL):
        chosen = first_allowed(ContentType.LANDING_PAGE, ContentType.GUIDE)
    elif intent is SearchIntent.LOCAL:
        # LOCAL_PAGE is intentionally unreachable in Phase 2: a local page needs
        # locally-specific verified facts, and nothing yet enforces that.
        chosen = first_allowed(ContentType.LANDING_PAGE, ContentType.GUIDE)
    elif intent is SearchIntent.INFORMATIONAL:
        chosen = first_allowed(ContentType.GUIDE, ContentType.ARTICLE)

    return chosen or next(iter(profile.selectable_content_types()))


def slugify(text: str, *, max_length: int = 80) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_query(text)).strip("-")
    if len(slug) <= max_length:
        return slug or "untitled"
    # Cut on a word boundary so the slug stays readable.
    return slug[:max_length].rsplit("-", 1)[0] or slug[:max_length]
