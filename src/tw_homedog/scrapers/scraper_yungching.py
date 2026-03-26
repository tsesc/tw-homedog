"""Yungching (永慶房屋) scraper plugin: buy mode via public REST API."""

from __future__ import annotations

import logging
import math
import time
import random

import requests

from tw_homedog.db_config import Config
from tw_homedog.dedup import build_entity_fingerprint
from tw_homedog.normalizer import extract_price, generate_content_hash
from tw_homedog.regions import REGION_CODES

logger = logging.getLogger(__name__)

source = "yungching"

BUY_API_URL = "https://buy.yungching.com.tw/api/v2/list"

# Reverse lookup: region_id → Chinese name
_REGION_ID_TO_NAME: dict[int, str] = {v: k for k, v in REGION_CODES.items()}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _build_area_params(config: Config) -> list[list[str]]:
    """Build area query params from config regions and districts.

    Returns list of area groups, one per county:
      [["台北市-內湖區", "台北市-南港區"], ["新北市-中和區"]]

    Each group should be sent as a separate API request — Yungching API
    returns 0 results when mixing areas from different counties in one request.
    """
    groups = []
    for region_id in config.search.regions:
        county = _REGION_ID_TO_NAME.get(region_id)
        if not county:
            logger.warning("Unknown region ID %d for yungching", region_id)
            continue

        county_areas = []
        if config.search.districts:
            for district in config.search.districts:
                county_areas.append(f"{county}-{district}")
        else:
            county_areas.append(f"{county}-")

        if county_areas:
            groups.append(county_areas)

    return groups


def _normalize_listing(item: dict) -> dict:
    """Convert yungching API listing to normalized format."""
    case_key = item.get("caseKey", "")
    case_sid = str(item.get("caseSId", ""))
    title = item.get("caseName")
    price_raw = item.get("price")
    try:
        price = int(price_raw) if price_raw is not None else None
    except (ValueError, TypeError):
        price = None
    address = item.get("address")

    # Extract district from address (e.g., "台北市內湖區成功路" → "內湖區")
    district = None
    if address:
        import re
        m = re.search(r"(?:市|縣)([\u4e00-\u9fff]{1,3}區)", address)
        if m:
            district = m.group(1)

    # Area info
    pin_info = item.get("pinInfo") or {}
    reg_area = pin_info.get("regArea")  # Total registered area in 坪
    main_area = pin_info.get("mainArea")

    # Floor info
    floor_info = item.get("floorInfo") or {}
    from_floor = floor_info.get("fromFloor")
    up_floor = floor_info.get("upFloor")
    floor = None
    if from_floor is not None and up_floor is not None:
        floor = f"{from_floor}F/{up_floor}F"

    # Room info
    pattern_info = item.get("patternInfo") or {}
    room_count = pattern_info.get("room")
    living_count = pattern_info.get("livingRoom")
    bath_count = pattern_info.get("bathRoom")
    room = None
    if room_count is not None:
        parts = []
        if room_count:
            parts.append(f"{int(room_count)}房")
        if living_count:
            parts.append(f"{int(living_count)}廳")
        if bath_count:
            # Handle .5 bathrooms
            bath_str = str(bath_count) if bath_count != int(bath_count) else str(int(bath_count))
            parts.append(f"{bath_str}衛")
        room = "".join(parts)

    # Community
    community_info = item.get("communityInfo") or {}
    community_name = community_info.get("communityName")

    # Tags
    tags = item.get("tag") or []

    # Build age
    build_age = item.get("buildAge")
    houseage = f"{build_age}年" if build_age is not None else None

    # Unit price (per ping)
    unit_price = None
    if price is not None and reg_area and reg_area > 0:
        unit_price = f"{price / reg_area:.1f}"

    # Type
    kind_name = item.get("caseTypeName")

    url = f"https://buy.yungching.com.tw/list/detail/{case_key}" if case_key else None

    raw_hash = generate_content_hash(title, price, address)

    normalized = {
        "source": source,
        "listing_id": case_sid,
        "title": title,
        "price": price,
        "address": address,
        "district": district,
        "size_ping": float(reg_area) if reg_area else None,
        "floor": floor,
        "url": url,
        "published_at": None,
        "raw_hash": raw_hash,
        "houseage": houseage,
        "unit_price": unit_price,
        "kind_name": kind_name,
        "room": room,
        "tags": tags,
        "community_name": community_name,
    }
    normalized["entity_fingerprint"] = build_entity_fingerprint(normalized)
    return normalized


def scrape(config: Config, progress_cb=None) -> list[dict]:
    """Scrape yungching buy listings via public API.

    No authentication required — pure GET requests.
    """
    if config.search.mode != "buy":
        logger.info("Yungching scraper only supports buy mode, skipping")
        return []

    area_groups = _build_area_params(config)
    if not area_groups:
        logger.warning("No valid areas for yungching scraper")
        return []

    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
    })

    all_listings = []

    # Iterate per county group — Yungching API returns 0 results when mixing counties
    for areas in area_groups:
        for page_num in range(1, config.search.max_pages + 1):
            params: list[tuple[str, str]] = []
            for area in areas:
                params.append(("area", area))
            params.append(("pg", str(page_num)))
            params.append(("ps", "30"))

            # Price filters (unit: 萬)
            if config.search.price_min:
                params.append(("minPrice", str(int(config.search.price_min))))
            if config.search.price_max:
                params.append(("maxPrice", str(int(config.search.price_max))))

            # Room filters
            if config.search.room_counts:
                params.append(("minRoom", str(min(config.search.room_counts))))
                params.append(("maxRoom", str(max(config.search.room_counts))))

            logger.info("Fetching yungching page %d for %s", page_num, areas[0].split("-")[0])

            try:
                resp = session.get(BUY_API_URL, params=params, timeout=config.scraper.timeout)
                if resp.status_code != 200:
                    logger.error("Yungching API returned status %d", resp.status_code)
                    break

                body = resp.json()
                if body.get("status") != "Success":
                    logger.error("Yungching API error: %s", body.get("status"))
                    break

                data = body.get("data", {})
                items = data.get("list", [])
                total = data.get("totalCount", 0)
                pa = data.get("pa", {})
                total_pages = pa.get("totalPageCount", 1)

                if not items:
                    logger.info("No more yungching listings")
                    break

                for item in items:
                    all_listings.append(_normalize_listing(item))

                if progress_cb:
                    progress_cb(
                        f"永慶 page {page_num}: +{len(items)} (累計 {len(all_listings)}, 共 {total})"
                    )

                logger.info(
                    "Yungching page %d: got %d items, total so far: %d (API total: %d)",
                    page_num, len(items), len(all_listings), total,
                )

                if page_num >= total_pages:
                    break

            except Exception as e:
                logger.error("Failed to fetch yungching listings: %s", e)
                break

            time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))

    logger.info("Total yungching listings collected: %d", len(all_listings))
    return all_listings
