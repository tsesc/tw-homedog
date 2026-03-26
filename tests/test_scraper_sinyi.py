"""Tests for sinyi scraper (unit tests with mocks, no real HTTP)."""

from unittest.mock import patch, MagicMock

import pytest

from tw_homedog.db_config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.scrapers.scraper_sinyi import (
    _build_request_payload,
    _get_district_zips,
    _normalize_listing,
    scrape,
    source,
    CITY_TO_RETRANGE,
    TAIPEI_DISTRICT_ZIPS,
)


@pytest.fixture
def buy_config():
    return Config(
        search=SearchConfig(
            regions=[1],
            districts=["內湖區", "南港區"],
            price_min=2000,
            price_max=3000,
            mode="buy",
            min_ping=20,
            max_pages=2,
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10),
    )


def test_source_name():
    assert source == "sinyi"


def test_get_district_zips():
    zips = _get_district_zips(["內湖區", "南港區"])
    assert zips == {"114", "115"}


def test_get_district_zips_empty():
    assert _get_district_zips([]) == set()


def test_get_district_zips_unknown():
    assert _get_district_zips(["不存在區"]) == set()


def test_build_request_payload_basic(buy_config):
    payload = _build_request_payload(buy_config, page=1)
    assert payload["page"] == 1
    assert payload["pageCnt"] == 50
    f = payload["filter"]
    assert f["retRange"] == ["1"]  # Taipei
    assert f["price"]["priceRange"] == ["2000-3000"]
    assert f["ping"]["pingRange"] == ["20-999"]


def test_build_request_payload_no_price(buy_config):
    buy_config.search.price_min = 0
    buy_config.search.price_max = 0
    payload = _build_request_payload(buy_config)
    assert "price" not in payload["filter"]


def test_build_request_payload_unknown_region(buy_config):
    buy_config.search.regions = [999]
    payload = _build_request_payload(buy_config)
    assert payload["filter"]["retRange"] == ["1"]  # Falls back to Taipei


SAMPLE_LISTING = {
    "houseNo": "5204CR",
    "name": "文山區電梯兩房",
    "totalPrice": 2488,
    "address": "台北市文山區辛亥路四段",
    "zipCode": "116",
    "areaBuilding": 26.53,
    "floor": "8",
    "totalfloor": "18",
    "layout": "2房2廳1衛",
    "commName": "敦南捷境",
    "age": "8.8年",
    "houselandtype": ["L"],
    "tags": ["7", "6", "4"],
    "shareURL": "https://sinyi.in/o/5204CR/0/3",
}


def test_normalize_listing_full():
    result = _normalize_listing(SAMPLE_LISTING)
    assert result["source"] == "sinyi"
    assert result["listing_id"] == "5204CR"
    assert result["title"] == "文山區電梯兩房"
    assert result["price"] == 2488
    assert result["address"] == "台北市文山區辛亥路四段"
    assert result["district"] == "文山區"
    assert result["size_ping"] == 26.53
    assert result["floor"] == "8F/18F"
    assert result["room"] == "2房2廳1衛"
    assert result["community_name"] == "敦南捷境"
    assert result["houseage"] == "8.8年"
    assert result["kind_name"] == "電梯大樓"
    assert result["url"] == "https://sinyi.in/o/5204CR/0/3"
    assert result["raw_hash"]
    assert result["entity_fingerprint"]


def test_normalize_listing_minimal():
    item = {
        "houseNo": "TEST1",
        "name": "測試",
        "totalPrice": None,
        "address": None,
    }
    result = _normalize_listing(item)
    assert result["source"] == "sinyi"
    assert result["listing_id"] == "TEST1"
    assert result["price"] is None
    assert result["district"] is None
    assert result["size_ping"] is None


def test_normalize_listing_type_mapping():
    for code, expected in [("L", "電梯大樓"), ("W", "華廈"), ("A", "公寓"), ("T", "透天"), ("S", "套房")]:
        item = {"houseNo": "X", "houselandtype": [code]}
        result = _normalize_listing(item)
        assert result["kind_name"] == expected


def test_scrape_rent_mode_skipped(buy_config):
    buy_config.search.mode = "rent"
    result = scrape(buy_config)
    assert result == []


def test_scrape_happy_path(buy_config):
    """Scrape with mocked Playwright context."""
    api_response = {
        "retResult": True,
        "retCode": "200",
        "content": {
            "totalCnt": 1,
            "object": [SAMPLE_LISTING],
        },
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json.return_value = api_response

    mock_request = MagicMock()
    mock_request.post.return_value = mock_resp

    mock_page = MagicMock()
    mock_page.evaluate.return_value = {"sat": "730282", "sid": "20260325000000000"}
    mock_page.url = "https://www.sinyi.com.tw/buy/list"

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_context.cookies.return_value = []
    mock_context.request = mock_request

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("playwright.sync_api.sync_playwright") as mock_sp:
        mock_sp.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sp.return_value.__exit__ = MagicMock(return_value=False)

        result = scrape(buy_config)

    # 5204CR has zipCode=116 (文山區), not in our districts (內湖/南港)
    # So it should be filtered out by client-side district filter
    assert len(result) == 0


def test_scrape_no_district_filter(buy_config):
    """Without districts, all listings pass."""
    buy_config.search.districts = []

    api_response = {
        "retResult": True,
        "retCode": "200",
        "content": {
            "totalCnt": 1,
            "object": [SAMPLE_LISTING],
        },
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json.return_value = api_response

    mock_request = MagicMock()
    mock_request.post.return_value = mock_resp

    mock_page = MagicMock()
    mock_page.evaluate.return_value = {"sat": "730282", "sid": "20260325000000000"}

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_context.cookies.return_value = []
    mock_context.request = mock_request

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    with patch("playwright.sync_api.sync_playwright") as mock_sp:
        mock_sp.return_value.__enter__ = MagicMock(return_value=mock_pw)
        mock_sp.return_value.__exit__ = MagicMock(return_value=False)

        result = scrape(buy_config)

    assert len(result) == 1
    assert result[0]["listing_id"] == "5204CR"


def test_region_mapping():
    assert CITY_TO_RETRANGE["台北市"] == "1"
    assert CITY_TO_RETRANGE["新北市"] == "2"
    assert CITY_TO_RETRANGE["台中市"] == "8"
    assert CITY_TO_RETRANGE["台南市"] == "12"
    assert CITY_TO_RETRANGE["高雄市"] == "14"


def test_taipei_district_zips():
    assert TAIPEI_DISTRICT_ZIPS["內湖區"] == "114"
    assert TAIPEI_DISTRICT_ZIPS["南港區"] == "115"
    assert len(TAIPEI_DISTRICT_ZIPS) == 12
