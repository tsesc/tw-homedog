"""Tests for yungching scraper (unit tests with mocks, no real HTTP)."""

from unittest.mock import patch, MagicMock

import pytest

from tw_homedog.db_config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.scrapers.scraper_yungching import (
    _build_area_params,
    _normalize_listing,
    scrape,
    source,
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
    assert source == "yungching"


def test_build_area_params_with_districts(buy_config):
    groups = _build_area_params(buy_config)
    assert groups == [["台北市-內湖區", "台北市-南港區"]]


def test_build_area_params_no_districts(buy_config):
    buy_config.search.districts = []
    groups = _build_area_params(buy_config)
    assert groups == [["台北市-"]]


def test_build_area_params_multi_region(buy_config):
    buy_config.search.regions = [1, 3]
    buy_config.search.districts = ["內湖區"]
    groups = _build_area_params(buy_config)
    # Each region is a separate group (separate API request)
    assert groups == [["台北市-內湖區"], ["新北市-內湖區"]]


def test_build_area_params_unknown_region(buy_config):
    buy_config.search.regions = [999]
    groups = _build_area_params(buy_config)
    assert groups == []


SAMPLE_LISTING = {
    "caseSId": 6514850,
    "caseKey": "bdd7794a-a3cb-45fd-a3ff-336bec4c9c6b",
    "caseName": "內湖電梯三房車位",
    "address": "台北市內湖區成功路三段",
    "price": 2680.0,
    "caseTypeName": "住宅大樓",
    "buildAge": 15.2,
    "pinInfo": {
        "regArea": 42.5,
        "mainArea": 25.3,
        "landArea": 8.5,
    },
    "floorInfo": {
        "fromFloor": 5,
        "toFloor": 5,
        "upFloor": 12,
    },
    "patternInfo": {
        "room": 3.0,
        "livingRoom": 2.0,
        "bathRoom": 2.0,
    },
    "communityInfo": {
        "communityId": 12345,
        "communityName": "成功大廈",
    },
    "tag": ["近捷運", "有車位"],
}


def test_normalize_listing_full():
    result = _normalize_listing(SAMPLE_LISTING)
    assert result["source"] == "yungching"
    assert result["listing_id"] == "6514850"
    assert result["title"] == "內湖電梯三房車位"
    assert result["price"] == 2680
    assert result["address"] == "台北市內湖區成功路三段"
    assert result["district"] == "內湖區"
    assert result["size_ping"] == 42.5
    assert result["floor"] == "5F/12F"
    assert result["room"] == "3房2廳2衛"
    assert result["community_name"] == "成功大廈"
    assert result["tags"] == ["近捷運", "有車位"]
    assert result["houseage"] == "15.2年"
    assert result["kind_name"] == "住宅大樓"
    assert "buy.yungching.com.tw" in result["url"]
    assert result["raw_hash"]  # non-empty
    assert result["entity_fingerprint"]  # non-empty


def test_normalize_listing_minimal():
    item = {
        "caseSId": 999,
        "caseKey": "abc-123",
        "caseName": "測試物件",
        "address": None,
        "price": None,
    }
    result = _normalize_listing(item)
    assert result["source"] == "yungching"
    assert result["listing_id"] == "999"
    assert result["title"] == "測試物件"
    assert result["price"] is None
    assert result["district"] is None
    assert result["size_ping"] is None
    assert result["floor"] is None
    assert result["room"] is None


def test_normalize_listing_half_bathroom():
    item = {
        "caseSId": 100,
        "caseKey": "x",
        "caseName": "test",
        "address": "台北市大安區",
        "price": 1000.0,
        "patternInfo": {"room": 2.0, "livingRoom": 1.0, "bathRoom": 1.5},
    }
    result = _normalize_listing(item)
    assert result["room"] == "2房1廳1.5衛"


def test_scrape_rent_mode_skipped(buy_config):
    buy_config.search.mode = "rent"
    result = scrape(buy_config)
    assert result == []


def _make_api_response(items, total=100, page=1, total_pages=4):
    return {
        "status": "Success",
        "data": {
            "list": items,
            "totalCount": total,
            "pa": {
                "currentPage": page,
                "totalPageCount": total_pages,
                "totalItemCount": total,
            },
        },
    }


def test_scrape_happy_path(buy_config):
    """Scrape returns normalized listings from API."""
    items = [SAMPLE_LISTING]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _make_api_response(items, total=1, total_pages=1)

    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.return_value = mock_resp

        result = scrape(buy_config)

    assert len(result) == 1
    assert result[0]["source"] == "yungching"
    assert result[0]["listing_id"] == "6514850"


def test_scrape_pagination(buy_config):
    """Scrape paginates through multiple pages."""
    page1_resp = MagicMock()
    page1_resp.status_code = 200
    page1_resp.json.return_value = _make_api_response(
        [SAMPLE_LISTING], total=60, page=1, total_pages=2
    )

    page2_listing = dict(SAMPLE_LISTING, caseSId=9999, caseName="第二頁物件")
    page2_resp = MagicMock()
    page2_resp.status_code = 200
    page2_resp.json.return_value = _make_api_response(
        [page2_listing], total=60, page=2, total_pages=2
    )

    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.side_effect = [page1_resp, page2_resp]

        result = scrape(buy_config)

    assert len(result) == 2
    assert result[1]["listing_id"] == "9999"


def test_scrape_api_error(buy_config):
    """Scrape handles API error gracefully."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.return_value = mock_resp

        result = scrape(buy_config)

    assert result == []


def test_scrape_network_error(buy_config):
    """Scrape handles network exceptions."""
    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.side_effect = Exception("Connection timeout")

        result = scrape(buy_config)

    assert result == []


def test_scrape_empty_response(buy_config):
    """Scrape handles empty list response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _make_api_response([], total=0, total_pages=0)

    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.return_value = mock_resp

        result = scrape(buy_config)

    assert result == []


def test_scrape_progress_callback(buy_config):
    """Progress callback is called with status messages."""
    messages = []
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _make_api_response(
        [SAMPLE_LISTING], total=1, total_pages=1
    )

    with patch("tw_homedog.scrapers.scraper_yungching.requests.Session") as MockSession:
        session = MockSession.return_value
        session.get.return_value = mock_resp

        scrape(buy_config, progress_cb=lambda m: messages.append(m))

    assert len(messages) == 1
    assert "永慶" in messages[0]
