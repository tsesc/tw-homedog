"""Match engine: filter listings by configured criteria."""

import json
import logging
import re
from datetime import datetime

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
    """Check if listing meets size range requirements."""
    size = listing.get("size_ping")
    # Missing data should not reject
    if size is None:
        return True
    if config.search.min_ping is not None and size < config.search.min_ping:
        return False
    if config.search.max_ping is not None and size > config.search.max_ping:
        return False
    return True


def _parse_counts(text: str | None, marker: str) -> int | None:
    """Extract integer count (房/衛) from strings like '3房2廳2衛'. Returns None if not found."""
    if not text:
        return None
    try:
        match = next((m for m in re.finditer(r"(\d+)" + marker, text) if m), None)
    except re.error:
        return None
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def match_room(listing: dict, config: Config) -> bool:
    """Check room count against configured set. Unknown counts do not reject."""
    if not config.search.room_counts:
        return True
    count = _parse_counts(listing.get("room"), "房")
    if count is None:
        count = _parse_counts(listing.get("shape_name"), "房")
    if count is None:
        return True
    return count in config.search.room_counts


def match_bathroom(listing: dict, config: Config) -> bool:
    """Check bathroom count against configured set. Unknown counts do not reject."""
    if not config.search.bathroom_counts:
        return True
    count = _parse_counts(listing.get("room"), "衛")
    if count is None:
        count = _parse_counts(listing.get("shape_name"), "衛")
    if count is None:
        return True
    return count in config.search.bathroom_counts


def match_build_year(listing: dict, config: Config) -> bool:
    """Check build year range. Missing data does not reject."""
    year_min = config.search.year_built_min
    year_max = config.search.year_built_max
    if year_min is None and year_max is None:
        return True

    build_year = listing.get("build_year")

    # If explicit build_year not present, derive from houseage like "15年"
    if build_year is None:
        houseage = listing.get("houseage")
        if isinstance(houseage, str):
            match = re.search(r"(\\d+)", houseage)
            if match:
                try:
                    age = int(match.group(1))
                    current_year = datetime.now().year
                    build_year = current_year - age
                except ValueError:
                    build_year = None

    if build_year is None:
        return True

    if year_min is not None and build_year < year_min:
        return False
    if year_max is not None and build_year > year_max:
        return False
    return True


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
        if not match_room(listing, config):
            continue
        if not match_bathroom(listing, config):
            continue
        if not match_build_year(listing, config):
            continue
        if not match_keywords(listing, config):
            continue
        matched.append(listing)

    logger.info("Matched %d/%d unnotified listings", len(matched), len(unnotified))
    return matched
