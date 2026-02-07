"""Match engine: filter listings by configured criteria."""

import json
import logging

from tw_homedog.config import Config
from tw_homedog.storage import Storage

logger = logging.getLogger(__name__)


def match_price(listing: dict, config: Config) -> bool:
    """Check if listing price is within configured range."""
    price = listing.get("price")
    if price is None:
        return True  # No price data, don't filter out
    if config.search.price_min is not None and price < config.search.price_min:
        return False
    if config.search.price_max is not None and price > config.search.price_max:
        return False
    return True


def match_district(listing: dict, config: Config) -> bool:
    """Check if listing district is in configured list."""
    district = listing.get("district")
    if not district or not config.search.districts:
        return True  # No district data or no filter
    return district in config.search.districts


def match_size(listing: dict, config: Config) -> bool:
    """Check if listing meets minimum size requirement."""
    if config.search.min_ping is None:
        return True
    size = listing.get("size_ping")
    if size is None:
        return True  # No size data, don't filter out
    return size >= config.search.min_ping


def _build_searchable_text(listing: dict) -> str:
    """Combine all searchable fields into one string for keyword matching."""
    parts = [
        listing.get("title") or "",
        listing.get("room") or "",
        listing.get("kind_name") or "",
        listing.get("address") or "",
        listing.get("parking_desc") or "",
        listing.get("shape_name") or "",
        listing.get("community_name") or "",
    ]
    # tags stored as JSON string in DB
    tags_raw = listing.get("tags")
    if tags_raw:
        if isinstance(tags_raw, str):
            try:
                tags_list = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags_list = []
        else:
            tags_list = tags_raw
        parts.extend(tags_list)
    return " ".join(parts)


def match_keywords(listing: dict, config: Config) -> bool:
    """Check keyword include/exclude filters against all listing text fields."""
    text = _build_searchable_text(listing)

    # All include keywords must be present
    for kw in config.search.keywords_include:
        if kw not in text:
            return False

    # Any exclude keyword means rejection
    for kw in config.search.keywords_exclude:
        if kw in text:
            return False

    return True


def find_matching_listings(config: Config, storage: Storage) -> list[dict]:
    """Find all unnotified listings that match configured criteria."""
    unnotified = storage.get_unnotified_listings()
    matched = []

    for listing in unnotified:
        if not match_price(listing, config):
            continue
        if not match_district(listing, config):
            continue
        if not match_size(listing, config):
            continue
        if not match_keywords(listing, config):
            continue
        matched.append(listing)

    logger.info("Matched %d/%d unnotified listings", len(matched), len(unnotified))
    return matched
