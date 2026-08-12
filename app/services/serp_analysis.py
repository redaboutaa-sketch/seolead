"""Deterministic first-pass analysis of the organic results.

What this does: reads the *shape* of the result page — how many results are
commercial vs informational, whether calculators or comparison pages dominate,
whether Belgian domains hold the page, which questions Google surfaces. That is
what tells us what the searcher is actually being served, and where the gap is.

What this deliberately does not do: reproduce competitor copy, or hand the writer a
specific page to imitate. Titles and snippets are used as *signals* and are never
passed to the writer as material. The brief receives derived observations and the
questions, not competitor text.
"""
from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from app.schemas.serp import SerpSnapshot
from app.services.intent import normalize_query
from app.verticals.profile import VerticalProfile

# Page-shape signals, matched against titles. Multilingual for the BE pilot.
_CALCULATOR_HINTS = ("calculateur", "calculatrice", "simulateur", "simulator",
                     "calculator", "estimation", "estimateur", "bereken")
_COMPARISON_HINTS = ("comparatif", "comparaison", "comparer", "vergelijk",
                     "comparison", "versus", " vs ", "meilleur", "beste", "top ")
_GUIDE_HINTS = ("guide", "comment", "hoe ", "how to", "tout savoir", "conseils",
                "expliqué", "uitleg")
_PRICE_HINTS = ("prix", "prijs", "coût", "kosten", "tarif", "cost", "price",
                "combien", "hoeveel", "devis", "offerte")
_LISTING_HINTS = ("installateur", "installateurs", "entreprise", "devis gratuit")

_BE_TLDS = (".be",)


def _host(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    return host[4:] if host.startswith("www.") else (host or None)


def _matches(text: str, hints: tuple[str, ...]) -> bool:
    normalized = normalize_query(text)
    return any(normalize_query(h).strip() in normalized for h in hints)


def analyse_serp(snapshot: SerpSnapshot, profile: VerticalProfile) -> dict:
    """Derive structural observations. No competitor text leaves this function."""
    organic = snapshot.organic
    total = len(organic)

    if total == 0:
        return {
            "organic_count": 0,
            "observations": ["The SERP returned no organic results to analyse."],
            "competitor_pages": [],
            "questions": [],
            "related_searches": [],
            "serp_features": sorted(snapshot.feature_types),
            "content_gap": [],
        }

    calculators = comparisons = guides = price_pages = listings = 0
    local_pages = 0
    domains: Counter[str] = Counter()

    competitor_pages = []
    for result in organic:
        title = result.title or ""
        host = _host(result.url)
        if host:
            domains[host] += 1
        if any(host.endswith(t) for t in _BE_TLDS) if host else False:
            local_pages += 1

        is_calculator = _matches(title, _CALCULATOR_HINTS)
        is_comparison = _matches(title, _COMPARISON_HINTS)
        is_guide = _matches(title, _GUIDE_HINTS)
        is_price = _matches(title, _PRICE_HINTS)
        is_listing = _matches(title, _LISTING_HINTS)

        calculators += is_calculator
        comparisons += is_comparison
        guides += is_guide
        price_pages += is_price
        listings += is_listing

        # Structure only. `title` is kept for operator inspection of the SERP; it
        # is NOT forwarded to the writer.
        competitor_pages.append({
            "rank": result.rank_group or result.rank_absolute,
            "domain": host,
            "url": result.url,
            "title": title,
            "shape": {
                "calculator": is_calculator, "comparison": is_comparison,
                "guide": is_guide, "price_focused": is_price, "listing": is_listing,
            },
        })

    commercial_signals = price_pages + listings + comparisons
    informational_signals = guides
    dominant = "commercial" if commercial_signals > informational_signals else (
        "informational" if informational_signals > commercial_signals else "mixed")

    observations: list[str] = [
        f"{total} organic results analysed; {len(domains)} distinct domains.",
        f"Dominant page framing: {dominant} "
        f"({commercial_signals} commercial vs {informational_signals} informational signals).",
    ]
    if calculators:
        observations.append(
            f"{calculators} of {total} results present a calculator or simulator — "
            f"searchers expect an interactive estimate.")
    if comparisons:
        observations.append(
            f"{comparisons} of {total} results are comparison pages.")
    if price_pages:
        observations.append(
            f"{price_pages} of {total} results lead with price framing.")
    if local_pages:
        observations.append(
            f"{local_pages} of {total} results sit on .be domains — the SERP is "
            f"locally held.")
    else:
        observations.append(
            "No .be domain appears in the organic results, which is unusual for a "
            "Belgian query and may indicate a local content gap.")

    repeated = [d for d, n in domains.most_common(3) if n > 1]
    if repeated:
        observations.append(
            f"Domains appearing more than once: {', '.join(repeated)}.")

    if snapshot.feature_types:
        observations.append(
            f"SERP features present: {', '.join(sorted(snapshot.feature_types))}.")

    # Content gap: page shapes the SERP is NOT serving.
    gap: list[str] = []
    if not calculators:
        gap.append("No calculator or simulator appears in the top results.")
    if not comparisons:
        gap.append("No comparison page appears in the top results.")
    if not local_pages:
        gap.append("No Belgian-domain result appears in the top results.")
    if guides == 0:
        gap.append("No explanatory guide appears in the top results.")

    return {
        "organic_count": total,
        "distinct_domains": len(domains),
        "top_domains": [{"domain": d, "count": n} for d, n in domains.most_common(5)],
        "shape_counts": {
            "calculator": calculators, "comparison": comparisons, "guide": guides,
            "price_focused": price_pages, "listing": listings,
            "belgian_domain": local_pages,
        },
        "dominant_framing": dominant,
        "observations": observations,
        "competitor_pages": competitor_pages,
        "questions": [q.text for q in snapshot.paa],
        "related_searches": [q.text for q in snapshot.related],
        "serp_features": sorted(snapshot.feature_types),
        "content_gap": gap,
    }
