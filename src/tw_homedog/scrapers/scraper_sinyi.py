"""Sinyi (信義房屋) scraper plugin: buy mode via Playwright-bootstrapped API."""

from __future__ import annotations

import logging
import random
import time

from tw_homedog.db_config import Config
from tw_homedog.dedup import build_entity_fingerprint
from tw_homedog.normalizer import generate_content_hash

logger = logging.getLogger(__name__)

source = "sinyi"

API_URL = "https://sinyiwebapi.sinyi.com.tw/filterObject.php"
BASE_URL = "https://www.sinyi.com.tw"

# Map region IDs to sinyi retRange city codes
REGION_TO_RETRANGE = {
    1: "1",   # 台北市
    3: "2",   # 新北市
    6: "5",   # 桃園市
    11: "8",  # 台中市
    21: "12", # 台南市
    23: "14", # 高雄市
}

# District name → zip code for client-side filtering
TAIPEI_DISTRICT_ZIPS = {
    "中正區": "100", "大同區": "103", "中山區": "104", "松山區": "105",
    "大安區": "106", "萬華區": "108", "信義區": "110", "士林區": "111",
    "北投區": "112", "內湖區": "114", "南港區": "115", "文山區": "116",
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _get_district_zips(districts: list[str]) -> set[str]:
    """Convert district names to zip codes for client-side filtering."""
    zips = set()
    for d in districts:
        z = TAIPEI_DISTRICT_ZIPS.get(d)
        if z:
            zips.add(z)
    return zips


def _normalize_listing(item: dict) -> dict:
    """Convert sinyi API listing to normalized format."""
    house_no = item.get("houseNo", "")
    title = item.get("name")
    total_price = item.get("totalPrice")
    price = int(total_price) if total_price is not None else None
    address = item.get("address")

    # District from zipCode
    zip_code = item.get("zipCode", "")
    district = None
    for name, zc in TAIPEI_DISTRICT_ZIPS.items():
        if zc == zip_code:
            district = name
            break

    # Area
    area_building = item.get("areaBuilding")
    size_ping = float(area_building) if area_building is not None else None

    # Floor
    floor_num = item.get("floor")
    total_floor = item.get("totalfloor")
    floor = None
    if floor_num and total_floor:
        floor = f"{floor_num}F/{total_floor}F"

    # Room layout
    room = item.get("layout")

    # Community
    community_name = item.get("commName")

    # Tags (sinyi uses numeric tag codes, not strings)
    tags = item.get("tags") or []

    # Age
    houseage = item.get("age")

    # Unit price
    unit_price = None
    if price is not None and size_ping and size_ping > 0:
        unit_price = f"{price / size_ping:.1f}"

    # Kind
    kind_name = None
    house_types = item.get("houselandtype") or []
    type_map = {"L": "電梯大樓", "W": "華廈", "A": "公寓", "T": "透天", "S": "套房"}
    if house_types:
        kind_name = type_map.get(house_types[0])

    url = item.get("shareURL") or f"{BASE_URL}/buy/{house_no}"

    raw_hash = generate_content_hash(title, price, address)

    normalized = {
        "source": source,
        "listing_id": house_no,
        "title": title,
        "price": price,
        "address": address,
        "district": district,
        "size_ping": size_ping,
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


def _build_request_payload(config: Config, page: int = 1) -> dict:
    """Build the POST payload for sinyi filterObject API."""
    ret_range = []
    for region_id in config.search.regions:
        code = REGION_TO_RETRANGE.get(region_id)
        if code:
            ret_range.append(code)

    if not ret_range:
        ret_range = ["1"]  # Default to Taipei

    filter_obj: dict = {
        "exludeSameTrade": False,
        "objectStatus": 0,
        "retType": 1,
        "retRange": ret_range,
        "mapType": 1,
        "objectType": [],
    }

    # Price filter (unit: 萬)
    if config.search.price_min or config.search.price_max:
        price_min = int(config.search.price_min) if config.search.price_min else 0
        price_max = int(config.search.price_max) if config.search.price_max else 99999
        filter_obj["price"] = {
            "priceType": 2,
            "priceRange": [f"{price_min}-{price_max}"],
        }

    # Area filter (unit: 坪)
    if config.search.min_ping or config.search.max_ping:
        ping_min = int(config.search.min_ping) if config.search.min_ping else 0
        ping_max = int(config.search.max_ping) if config.search.max_ping else 999
        filter_obj["ping"] = {
            "pingType": 1,
            "pingRange": [f"{ping_min}-{ping_max}"],
        }

    return {
        "machineNo": "",
        "ipAddress": "",
        "osType": 4,
        "model": "web",
        "deviceVersion": "Mac OS X 10.15.7",
        "appVersion": "120.0.0.0",
        "deviceType": 3,
        "apType": 3,
        "browser": 1,
        "memberId": "",
        "domain": "www.sinyi.com.tw",
        "utmSource": "", "utmMedium": "", "utmCampaign": "",
        "utmCode": "", "requestor": 1, "utmContent": "", "utmTerm": "",
        "sinyiGroup": 1,
        "filter": filter_obj,
        "page": page,
        "pageCnt": 50,
        "sort": "0",
        "isReturnTotal": True,
    }


def scrape(config: Config, progress_cb=None) -> list[dict]:
    """Scrape sinyi buy listings via Playwright-bootstrapped API.

    Uses Playwright's context.request to make API calls because
    plain requests gets rejected with error 410.
    """
    if config.search.mode != "buy":
        logger.info("Sinyi scraper only supports buy mode, skipping")
        return []

    from playwright.sync_api import sync_playwright

    # Determine which districts to filter client-side
    district_zips = _get_district_zips(config.search.districts) if config.search.districts else set()

    all_listings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
        )
        page = context.new_page()

        # Bootstrap session by visiting the site
        # Sinyi's Next.js SPA is heavy — use 60s minimum for Docker environments
        bootstrap_timeout = max(config.scraper.timeout * 1000, 60000)
        logger.info("Bootstrapping sinyi session (timeout=%dms)...", bootstrap_timeout)
        try:
            page.goto(f"{BASE_URL}/buy/list", timeout=bootstrap_timeout)
            page.wait_for_load_state("networkidle", timeout=bootstrap_timeout)
            page.wait_for_timeout(3000)
        except Exception as e:
            logger.error("Failed to bootstrap sinyi session: %s", e)
            browser.close()
            return []

        # Intercept to get sat and sid from initial API calls
        sat = None
        sid = None

        cookies = context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        # Try to get sat/sid from page's existing API calls by making a test call
        # The sat and sid are set during page load via appSetup.php and getSession.php
        # We capture them from the page's JavaScript context
        try:
            session_info = page.evaluate("""() => {
                // Try to find sat/sid from window or global state
                const w = window;
                return {
                    sat: w.__NEXT_DATA__?.props?.pageProps?.sat || '',
                    sid: w.__NEXT_DATA__?.props?.pageProps?.sid || '',
                };
            }""")
            sat = session_info.get("sat") or None
            sid = session_info.get("sid") or None
        except Exception:
            pass

        if not sat or not sid:
            # Fallback: capture from network requests
            captured = {}

            def capture_response(response):
                url = response.url
                if "appSetup.php" in url:
                    try:
                        body = response.json()
                        captured["sat"] = str(body.get("content", {}).get("accessCode", ""))
                    except Exception:
                        pass
                elif "getSession.php" in url:
                    try:
                        body = response.json()
                        captured["sid"] = str(body.get("content", {}).get("sid", ""))
                    except Exception:
                        pass

            page.on("response", capture_response)
            page.reload(timeout=bootstrap_timeout)
            page.wait_for_load_state("networkidle", timeout=bootstrap_timeout)
            page.wait_for_timeout(3000)

            sat = captured.get("sat")
            sid = captured.get("sid")

        if not sat or not sid:
            logger.error("Failed to obtain sinyi session tokens (sat/sid)")
            browser.close()
            return []

        logger.info("Sinyi session bootstrapped (sat=%s, sid=%s...)", sat, sid[:8] if sid else "?")

        # Use Playwright's context.request for API calls
        headers = {
            "sat": str(sat),
            "sid": str(sid),
            "code": "0",
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "referer": f"{BASE_URL}/",
        }

        for page_num in range(1, config.search.max_pages + 1):
            payload = _build_request_payload(config, page=page_num)
            logger.info("Fetching sinyi page %d", page_num)

            try:
                resp = context.request.post(API_URL, headers=headers, data=payload)
                if resp.status != 200:
                    logger.error("Sinyi API returned status %d", resp.status)
                    break

                body = resp.json()
                if not body.get("retResult"):
                    logger.error("Sinyi API error: %s", body.get("retMsg", ""))
                    break

                content = body.get("content", {})
                objects = content.get("object", [])
                total = content.get("totalCnt", 0)

                if not objects:
                    logger.info("No more sinyi listings")
                    break

                # Client-side district filter
                for item in objects:
                    if district_zips:
                        item_zip = item.get("zipCode", "")
                        if item_zip not in district_zips:
                            continue
                    all_listings.append(_normalize_listing(item))

                if progress_cb:
                    progress_cb(
                        f"信義 page {page_num}: +{len(objects)} (累計 {len(all_listings)}, 共 {total})"
                    )

                logger.info(
                    "Sinyi page %d: got %d items (after filter: %d), API total: %d",
                    page_num, len(objects), len(all_listings), total,
                )

                # Check if we've fetched all pages
                fetched_total = page_num * 50
                if fetched_total >= total:
                    break

            except Exception as e:
                logger.error("Failed to fetch sinyi listings: %s", e)
                break

            time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))

        browser.close()

    logger.info("Total sinyi listings collected: %d", len(all_listings))
    return all_listings
