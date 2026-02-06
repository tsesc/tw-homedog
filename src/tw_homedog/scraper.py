"""591 scraper: supports both rent and buy modes via BFF API + Playwright."""

import logging
import random
import re
import time

import requests
from bs4 import BeautifulSoup

from tw_homedog.config import Config

logger = logging.getLogger(__name__)

# Rent mode
RENT_BASE_URL = "https://rent.591.com.tw"
RENT_DISTRICT_CODES = {
    "Daan": 7, "Zhongzheng": 8, "Xinyi": 3, "Songshan": 4,
    "Zhongshan": 1, "Neihu": 5, "Nangang": 6, "Shilin": 10,
    "Beitou": 11, "Wanhua": 9, "Wenshan": 2, "Datong": 12,
}

# Buy mode
BUY_BASE_URL = "https://sale.591.com.tw"
BUY_API_URL = "https://bff-house.591.com.tw/v1/web/sale/list"
BUY_DISTRICT_CODES = {
    "Zhongzheng": 1, "Datong": 2, "Zhongshan": 3, "Songshan": 4,
    "Daan": 5, "Wanhua": 6, "Xinyi": 7, "Shilin": 8,
    "Beitou": 9, "Neihu": 10, "Nangang": 11, "Wenshan": 12,
}

# Chinese district name to English name mapping
ZH_TO_EN_DISTRICT = {
    "中正區": "Zhongzheng", "大同區": "Datong", "中山區": "Zhongshan",
    "松山區": "Songshan", "大安區": "Daan", "萬華區": "Wanhua",
    "信義區": "Xinyi", "士林區": "Shilin", "北投區": "Beitou",
    "內湖區": "Neihu", "南港區": "Nangang", "文山區": "Wenshan",
}

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

        page.goto(f'{BUY_BASE_URL}/?shType=list&regionid={config.search.region}',
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
    section_name = item.get('section_name', '')
    district = ZH_TO_EN_DISTRICT.get(section_name)

    return {
        "id": str(item.get("houseid", "")),
        "title": item.get("title"),
        "price": item.get("price"),  # in 萬 (10k NTD)
        "address": f"{item.get('section_name', '')} {item.get('address', '')}",
        "district": district,
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
    district_codes = [
        BUY_DISTRICT_CODES[d] for d in config.search.districts if d in BUY_DISTRICT_CODES
    ]
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
            'regionid': config.search.region,
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


# =============================================================================
# Rent mode: Playwright + HTTP scraper (original)
# =============================================================================

def build_search_url(config: Config, district_code: int) -> str:
    """Build 591 rent search URL from config and district code."""
    params = [
        f"region={config.search.region}",
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
    district_codes = [
        RENT_DISTRICT_CODES[d] for d in config.search.districts if d in RENT_DISTRICT_CODES
    ]
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
    for text_block in [address or "", title or ""]:
        for zh_name, en_name in ZH_TO_EN_DISTRICT.items():
            zh_short = zh_name[:-1]  # Remove 區
            if zh_short in text_block:
                district = en_name
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
    """Scrape listings based on config mode (rent or buy)."""
    mode = config.search.mode
    if mode == 'buy':
        return scrape_buy_listings(config)
    else:
        return scrape_rent_listings(config)
