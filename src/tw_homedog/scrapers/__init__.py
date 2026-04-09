"""Scraper plugin registry and dispatcher.

Dispatches scraping to registered source plugins based on config.search.sources.
Each plugin handles its own session bootstrap, API calls, and normalization.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tw_homedog.db_config import Config

from tw_homedog.scrapers import scraper_591, scraper_sinyi, scraper_yungching

logger = logging.getLogger(__name__)

# Registry: source name → module with scrape(config, progress_cb) function
SCRAPER_REGISTRY: dict[str, object] = {
    "591": scraper_591,
    "sinyi": scraper_sinyi,
    "yungching": scraper_yungching,
}


def scrape_all(config: Config, progress_cb=None) -> dict[str, list[dict]]:
    """Scrape from all enabled sources. Returns {source: [normalized listings]}.

    Each source runs independently — one failure doesn't block others.
    """
    sources = getattr(config.search, "sources", None)
    if sources is None:
        sources = ["591"]
    results: dict[str, list[dict]] = {}

    for source_name in sources:
        scraper_module = SCRAPER_REGISTRY.get(source_name)
        if scraper_module is None:
            logger.warning("Unknown source '%s', skipping", source_name)
            continue

        logger.info("Scraping source: %s", source_name)
        try:
            listings = scraper_module.scrape(config, progress_cb=progress_cb)
            results[source_name] = listings
            logger.info("Source %s: got %d listings", source_name, len(listings))
        except Exception:
            logger.exception("Source %s scrape failed", source_name)
            results[source_name] = []

    return results
