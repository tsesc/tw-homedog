"""591 scraper: supports both rent and buy modes via BFF API + Playwright."""

import logging
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from tw_homedog.config import Config, SearchConfig
from tw_homedog.regions import (
    BUY_SECTION_CODES,
    RENT_SECTION_CODES,
    resolve_districts,
)

logger = logging.getLogger(__name__)

# Rent mode
RENT_BASE_URL = "https://rent.591.com.tw"

# Buy mode
BUY_BASE_URL = "https://sale.591.com.tw"
BUY_API_URL = "https://bff-house.591.com.tw/v1/web/sale/list"
BUY_DETAIL_API_URL = "https://bff-house.591.com.tw/v1/web/sale/detail"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


# =============================================================================
# Buy mode: BFF API-based scraper
# =============================================================================

def _get_buy_session_headers(config: Config) -> tuple[requests.Session, dict]:
    """Get a session with CSRF token and cookies from 591 buy page."""
    from playwright.sync_api import sync_playwright

    api_headers = {}

    def capture_request(request):
        if 'bff-house.591.com.tw/v1/web/sale/list' in request.url:
            api_headers.update(dict(request.headers))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=random.choice(USER_AGENTS))
        page.on('request', capture_request)

        page.goto(f'{BUY_BASE_URL}/?shType=list&regionid={config.search.regions[0]}',
                  timeout=config.scraper.timeout * 1000)
        page.wait_for_load_state('networkidle', timeout=config.scraper.timeout * 1000)
        page.wait_for_timeout(2000)

        cookies = page.context.cookies()
        cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in cookies)
        browser.close()

    session = requests.Session()
    headers = {
        'User-Agent': api_headers.get('user-agent', random.choice(USER_AGENTS)),
        'x-csrf-token': api_headers.get('x-csrf-token', ''),
        'deviceid': api_headers.get('deviceid', ''),
        'device': 'pc',
        'Referer': f'{BUY_BASE_URL}/',
        'Accept': 'text/plain, */*; q=0.01',
        'Cookie': cookie_str,
    }
    return session, headers


def _normalize_buy_listing(item: dict) -> dict:
    """Convert BFF API listing item to our raw format."""
    section_name = item.get('section_name', '') or None

    return {
        "id": str(item.get("houseid", "")),
        "title": item.get("title"),
        "price": item.get("price"),  # in 萬 (10k NTD)
        "address": f"{item.get('section_name', '')} {item.get('address', '')}",
        "district": section_name,
        "size_ping": item.get("area"),
        "floor": item.get("floor"),
        "room": item.get("room"),
        "url": f"{BUY_BASE_URL}/home/house/detail/2/{item.get('houseid', '')}.html",
        "published_at": None,
        "houseage": item.get("showhouseage"),
        "unit_price": item.get("unitprice"),
        "kind_name": item.get("kind_name"),
        "shape_name": item.get("shape_name"),
        "tags": item.get("tag", []),
    }


def scrape_buy_listings(config: Config) -> list[dict]:
    """Scrape 591 buy listings via BFF API."""
    resolved = resolve_districts(config.search.regions[0], config.search.districts, mode="buy")
    district_codes = list(resolved.values())
    if not district_codes:
        logger.warning("No valid districts configured for buy mode")
        return []

    section_param = ','.join(str(c) for c in district_codes)

    logger.info("Getting session from 591 buy page...")
    session, headers = _get_buy_session_headers(config)

    all_listings = []
    first_row = 0
    page_size = 30

    for page_num in range(config.search.max_pages):
        timestamp = int(time.time() * 1000)
        params = {
            'type': 2,
            'timestamp': timestamp,
            'shType': 'list',
            'regionid': config.search.regions[0],
            'section': section_param,
        }
        if config.search.min_ping:
            params['area'] = f'{int(config.search.min_ping)}_'
        params['firstRow'] = first_row

        logger.info("Fetching buy listings page %d (firstRow=%d)", page_num + 1, first_row)

        try:
            resp = session.get(BUY_API_URL, params=params, headers=headers,
                               timeout=config.scraper.timeout)
            if resp.status_code != 200:
                logger.error("API returned status %d", resp.status_code)
                break

            body = resp.json()
            if body.get('status') != 1:
                logger.error("API error: %s", body.get('msg', ''))
                break

            data = body.get('data', {})
            total = int(data.get('total', 0))
            house_list = data.get('house_list', [])

            if not house_list:
                logger.info("No more listings")
                break

            # Filter to individual listings (skip community/newhouse entries)
            for item in house_list:
                if item.get('is_community') or item.get('is_newhouse'):
                    continue
                all_listings.append(_normalize_buy_listing(item))

            logger.info("Page %d: got %d items, total so far: %d (API total: %d)",
                        page_num + 1, len(house_list), len(all_listings), total)

            first_row += page_size

            if first_row >= total:
                break

        except Exception as e:
            logger.error("Failed to fetch buy listings: %s", e)
            break

        time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))

    logger.info("Total buy listings collected: %d", len(all_listings))
    return all_listings


def _extract_detail_fields(data: dict) -> dict:
    """Extract enrichment fields from buy detail API response data."""
    result = {}

    # From ware object
    ware = data.get("ware") or {}
    main_area = ware.get("mainarea")
    if main_area is not None:
        try:
            result["main_area"] = float(main_area)
        except (ValueError, TypeError):
            pass
    result["community_name"] = ware.get("community_name") or None

    # From info sections
    info = data.get("info") or {}

    # info['3'] contains: CarPlace, RatioRate, Fitment, ManagePrice, Shape
    info3 = info.get("3") or []
    for item in info3:
        name = item.get("name", "")
        value = item.get("value", "")
        if name == "車位":
            result["parking_desc"] = value or None
        elif name == "公設比":
            result["public_ratio"] = value or None
        elif name == "管理費":
            result["manage_price_desc"] = value or None
        elif name == "裝潢程度":
            result["fitment"] = value or None
        elif name == "型態":
            result["shape_name"] = value or None

    # info['2'] contains: Direction
    info2 = info.get("2") or []
    for item in info2:
        name = item.get("name", "")
        value = item.get("value", "")
        if name == "朝向":
            result["direction"] = value or None

    return result


def fetch_buy_listing_detail(
    session: requests.Session, headers: dict, house_id: str, timeout: int = 30
) -> dict | None:
    """Fetch detail data for a single buy listing from BFF API."""
    timestamp = int(time.time() * 1000)
    params = {"id": house_id, "timestamp": timestamp}
    try:
        resp = session.get(BUY_DETAIL_API_URL, params=params, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Detail API returned %d for house_id=%s", resp.status_code, house_id)
            return None
        body = resp.json()
        if body.get("status") != 1:
            logger.warning(
                "Detail API error for house_id=%s: status=%s msg=%s",
                house_id, body.get("status"), body.get("msg", ""),
            )
            logger.debug("Detail API full response for house_id=%s: %s", house_id, body)
            return None
        return _extract_detail_fields(body.get("data", {}))
    except Exception as e:
        logger.error("Failed to fetch detail for house_id=%s: %s", house_id, e)
        return None


def enrich_buy_listings(
    config: Config,
    session: requests.Session,
    headers: dict,
    listing_ids: list[str],
) -> dict[str, dict]:
    """Fetch detail data for multiple buy listings. Returns {listing_id: detail_dict}."""
    results = {}
    for i, lid in enumerate(listing_ids):
        logger.info("Enriching detail %d/%d: %s", i + 1, len(listing_ids), lid)
        detail = fetch_buy_listing_detail(session, headers, lid, timeout=config.scraper.timeout)
        if detail:
            results[lid] = detail
        if i < len(listing_ids) - 1:
            time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))
    logger.info("Enriched %d/%d listings", len(results), len(listing_ids))
    return results


# =============================================================================
# Rent mode: Playwright + HTTP scraper (original)
# =============================================================================

def build_search_url(config: Config, district_code: int) -> str:
    """Build 591 rent search URL from config and district code."""
    params = [
        f"region={config.search.regions[0]}",
        f"section={district_code}",
        f"price={config.search.price_min}_{config.search.price_max}",
    ]
    if config.search.min_ping:
        params.append(f"area={int(config.search.min_ping)}_")
    params.append("kind=0")
    return f"{RENT_BASE_URL}/list?{'&'.join(params)}"


def _extract_listing_ids_from_page(page) -> list[str]:
    """Extract listing IDs from a Playwright page."""
    ids = set()
    links = page.query_selector_all("a[href*='rent.591.com.tw/']")
    for link in links:
        href = link.get_attribute("href") or ""
        match = re.search(r"/(\d{7,8})(?:\?|$|#)", href)
        if match:
            ids.add(match.group(1))

    cards = page.query_selector_all("[data-id]")
    for card in cards:
        data_id = card.get_attribute("data-id")
        if data_id and data_id.isdigit() and len(data_id) >= 7:
            ids.add(data_id)

    return list(ids)


def collect_listing_ids(config: Config) -> list[str]:
    """Use Playwright to collect listing IDs from 591 rent search pages."""
    from playwright.sync_api import sync_playwright

    all_ids = set()
    resolved = resolve_districts(config.search.regions[0], config.search.districts, mode="rent")
    district_codes = list(resolved.values())
    if not district_codes:
        logger.warning("No valid districts configured")
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=random.choice(USER_AGENTS))

        for district_code in district_codes:
            url = build_search_url(config, district_code)
            logger.info("Scraping search page: %s", url)

            try:
                page.goto(url, timeout=config.scraper.timeout * 1000)
                page.wait_for_load_state("networkidle", timeout=config.scraper.timeout * 1000)
            except Exception as e:
                logger.error("Failed to load search page: %s", e)
                continue

            last_count = 0
            no_change = 0
            for _ in range(config.search.max_pages * 5):
                current_ids = _extract_listing_ids_from_page(page)
                all_ids.update(current_ids)

                if len(all_ids) == last_count:
                    no_change += 1
                    if no_change >= 3:
                        break
                else:
                    no_change = 0
                    last_count = len(all_ids)

                next_btn = page.query_selector(
                    ".pageNext, a[rel='next'], .pagination .next:not(.disabled)"
                )
                if next_btn and next_btn.is_visible():
                    try:
                        next_btn.click()
                        time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))
                        page.wait_for_load_state("networkidle", timeout=config.scraper.timeout * 1000)
                        continue
                    except Exception:
                        pass

                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)

            logger.info("Collected %d IDs from district code %d", len(all_ids), district_code)
            time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))

        browser.close()

    logger.info("Total unique listing IDs collected: %d", len(all_ids))
    return list(all_ids)


def _get_session() -> requests.Session:
    """Create HTTP session with random User-Agent."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


def fetch_listing_detail(config: Config, listing_id: str, session: requests.Session | None = None) -> dict | None:
    """Fetch and parse a single rent listing detail page."""
    if session is None:
        session = _get_session()

    url = f"{RENT_BASE_URL}/{listing_id}"

    for attempt in range(config.scraper.max_retries):
        try:
            response = session.get(url, timeout=config.scraper.timeout)
            if response.status_code == 200:
                return _parse_listing_html(response.text, listing_id)
            elif response.status_code == 404:
                logger.warning("Listing %s not found (404)", listing_id)
                return None
            else:
                logger.warning("Attempt %d: status %d for listing %s", attempt + 1, response.status_code, listing_id)
        except requests.RequestException as e:
            logger.warning("Attempt %d: error for listing %s: %s", attempt + 1, listing_id, e)

        if attempt < config.scraper.max_retries - 1:
            time.sleep(2 ** (attempt + 1))

    logger.error("Failed to fetch listing %s after %d retries", listing_id, config.scraper.max_retries)
    return None


def _parse_listing_html(html: str, listing_id: str) -> dict:
    """Parse rent listing detail HTML into raw data dict."""
    soup = BeautifulSoup(html, "html.parser")

    title = None
    title_tag = soup.find("h1") or soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    price = None
    price_match = re.search(r">(\d{1,3}(?:,\d{3})*)</?\w*>\s*元/月", html)
    if price_match:
        price = price_match.group(1)
    else:
        price_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*元", html)
        if price_match:
            price = price_match.group(1)

    size_ping = None
    size_match = re.search(r"([\d.]+)\s*坪", html)
    if size_match:
        size_ping = size_match.group(1)

    floor = None
    floor_match = re.search(r"(\d+)\s*[F樓]\s*/\s*(\d+)", html)
    if floor_match:
        floor = f"{floor_match.group(1)}F/{floor_match.group(2)}F"

    address = None
    addr_tag = soup.find(class_=re.compile(r"addr|address|location", re.I))
    if addr_tag:
        address = addr_tag.get_text(strip=True)

    district = None
    # Match Chinese district names from the region's section codes
    region_sections = BUY_SECTION_CODES.get(1, {})  # Default to Taipei
    rent_sections = RENT_SECTION_CODES.get(1, {})
    all_district_names = set(region_sections.keys()) | set(rent_sections.keys())
    for text_block in [address or "", title or ""]:
        for zh_name in all_district_names:
            zh_short = zh_name[:-1]  # Remove 區
            if zh_short in text_block:
                district = zh_name
                break
        if district:
            break

    return {
        "id": listing_id,
        "title": title,
        "price": price,
        "address": address,
        "district": district,
        "size_ping": size_ping,
        "floor": floor,
        "url": f"{RENT_BASE_URL}/{listing_id}",
        "published_at": None,
    }


def scrape_rent_listings(config: Config) -> list[dict]:
    """Full rent scrape pipeline: collect IDs → fetch details."""
    listing_ids = collect_listing_ids(config)
    if not listing_ids:
        logger.info("No listing IDs found")
        return []

    session = _get_session()
    results = []

    for i, lid in enumerate(listing_ids):
        logger.info("Fetching detail %d/%d: %s", i + 1, len(listing_ids), lid)
        detail = fetch_listing_detail(config, lid, session)
        if detail:
            results.append(detail)
        time.sleep(random.uniform(config.scraper.delay_min, config.scraper.delay_max))

    logger.info("Scraped %d listings out of %d IDs", len(results), len(listing_ids))
    return results


# =============================================================================
# Unified entry point
# =============================================================================

def scrape_listings(config: Config) -> list[dict]:
    """Scrape listings based on config mode (rent or buy).

    Loops through all configured regions and combines results.
    """
    all_listings = []
    mode = config.search.mode

    for region_id in config.search.regions:
        # Create a temporary config with single region for backward compat with helpers
        temp_config = Config(
            search=SearchConfig(
                regions=[region_id],
                districts=config.search.districts,
                price_min=config.search.price_min,
                price_max=config.search.price_max,
                mode=config.search.mode,
                min_ping=config.search.min_ping,
                keywords_include=config.search.keywords_include,
                keywords_exclude=config.search.keywords_exclude,
                max_pages=config.search.max_pages,
            ),
            telegram=config.telegram,
            database_path=config.database_path,
            scraper=config.scraper,
        )

        if mode == 'buy':
            listings = scrape_buy_listings(temp_config)
        else:
            listings = scrape_rent_listings(temp_config)

        all_listings.extend(listings)

    return all_listings
