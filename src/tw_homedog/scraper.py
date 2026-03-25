"""Backward-compatible thin wrapper around scrapers/ plugin system.

All scraping logic has moved to tw_homedog.scrapers.scraper_591.
This module re-exports commonly used functions for backward compatibility.
"""

from __future__ import annotations

# Re-export from scraper_591 for backward compatibility
from tw_homedog.scrapers.scraper_591 import (  # noqa: F401
    _extract_detail_fields,
    _get_buy_session_headers,
    _normalize_buy_listing,
    _parse_listing_html,
    _scrape_single_region,
    build_search_url,
    enrich_buy_listings,
    fetch_buy_listing_detail,
    scrape_buy_listings,
    scrape_rent_listings,
)
from tw_homedog.scrapers import scrape_all


def scrape_listings(config, progress_cb=None) -> list[dict]:
    """Scrape listings from all enabled sources and return flat list.

    This is the backward-compatible entry point. It delegates to the
    scraper plugin dispatcher and flattens the results.
    """
    results = scrape_all(config, progress_cb=progress_cb)
    flat = []
    for listings in results.values():
        flat.extend(listings)
    return flat
