"""The first-party offer, as the rest of the system consumes it.

Two consumers, one shape:

- the QA gate needs to know which figures a draft may present as OUR offer —
  and the answer while nothing is validated is « none », which is the guard
  working, not the guard missing data;
- a future agent surface (`get_solar_offers`, `get_financing_options`) needs
  the same facts from the same place, which is why this lives in the business
  layer and not inside a React component.

Deliberately a thin projection of `SiteConfig.offer`: the registry's rules —
who may add a value, what publishable requires — live on the config model,
where the validators are. This module only answers « what may be said, today ».
"""
from __future__ import annotations

from app.site.config import InvalidSite, OfferConfig, available_sites, load_site


def offer_view(offer: OfferConfig) -> dict:
    """The offer as the QA gate consumes it. Plain data, no config import needed
    on the consuming side."""
    return {
        "version": offer.version,
        "status": offer.status,
        "publishable": offer.publishable,
        "pending_legal_review": offer.pending_legal_review,
        "registered_numbers": offer.registered_numbers(),
    }


def offer_for_vertical(vertical_code: str) -> dict | None:
    """The offer registry of the site carrying this vertical, if one exists.

    The pipeline knows verticals, not sites; this is the bridge. None when no
    site declares the vertical — and the QA guard treats None exactly like an
    empty registry: fail-closed.
    """
    wanted = (vertical_code or "").upper()
    for site_id in available_sites():
        try:
            config = load_site(site_id)
        except InvalidSite:
            continue
        if (config.vertical or "").upper() == wanted:
            return offer_view(config.offer)
    return None
