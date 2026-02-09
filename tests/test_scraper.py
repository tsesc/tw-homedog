"""Tests for 591 scraper (unit tests with mocks, no real HTTP)."""

from unittest.mock import patch

import pytest

from tw_homedog.db_config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.regions import (
    BUY_SECTION_CODES,
    RENT_SECTION_CODES,
    EN_TO_ZH,
    resolve_districts,
)
from tw_homedog.scraper import (
    build_search_url,
    _parse_listing_html,
    _normalize_buy_listing,
    _extract_detail_fields,
    fetch_buy_listing_detail,
    scrape_listings,
    _scrape_single_region,
)


@pytest.fixture
def rent_config():
    return Config(
        search=SearchConfig(
            regions=[1],
            districts=["大安區", "中山區"],
            price_min=20000,
            price_max=40000,
            mode="rent",
            min_ping=20,
            max_pages=3,
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10, max_retries=2),
    )


@pytest.fixture
def buy_config():
    return Config(
        search=SearchConfig(
            regions=[1],
            districts=["南港區", "內湖區"],
            price_min=2000,
            price_max=3000,
            mode="buy",
            min_ping=20,
            max_pages=3,
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10, max_retries=2),
    )


def test_build_search_url(rent_config):
    daan_code = RENT_SECTION_CODES[1]["大安區"]
    url = build_search_url(rent_config, daan_code)
    assert "region=1" in url
    assert "section=7" in url
    assert "price=20000_40000" in url
    assert "area=20_" in url
    assert "kind=0" in url


def test_build_search_url_no_min_ping(rent_config):
    rent_config.search.min_ping = None
    url = build_search_url(rent_config, 7)
    assert "area=" not in url


def test_build_search_url_with_filters(rent_config):
    rent_config.search.max_ping = 40
    rent_config.search.room_counts = [2, 3]
    rent_config.search.bathroom_counts = [2]
    url = build_search_url(rent_config, RENT_SECTION_CODES[1]["大安區"])
    assert "area=20_40" in url
    assert "room=2,3" in url
    assert "bath=2" in url


def test_rent_section_codes_taipei():
    assert RENT_SECTION_CODES[1]["大安區"] == 7
    assert RENT_SECTION_CODES[1]["中山區"] == 1
    assert len(RENT_SECTION_CODES[1]) == 12


def test_buy_section_codes_taipei():
    assert BUY_SECTION_CODES[1]["內湖區"] == 10
    assert BUY_SECTION_CODES[1]["南港區"] == 11
    assert BUY_SECTION_CODES[1]["大安區"] == 5
    assert len(BUY_SECTION_CODES[1]) == 12


def test_en_to_zh():
    assert EN_TO_ZH["Neihu"] == "內湖區"
    assert EN_TO_ZH["Nangang"] == "南港區"
    assert len(EN_TO_ZH) == 12


def test_parse_listing_html_basic():
    html = """
    <html><head><title>大安區電梯套房</title></head>
    <body>
    <h1>大安區電梯套房</h1>
    <div>
        <strong>35,000</strong> 元/月
    </div>
    <div>25.5 坪</div>
    <div>4F/12</div>
    <div class="address">台北市大安區忠孝東路</div>
    </body></html>
    """
    result = _parse_listing_html(html, "12345678")
    assert result["id"] == "12345678"
    assert result["title"] == "大安區電梯套房"
    assert result["price"] == "35,000"
    assert result["size_ping"] == "25.5"
    assert result["district"] == "大安區"
    assert result["url"] == "https://rent.591.com.tw/12345678"


def test_parse_listing_html_missing_fields():
    html = "<html><head><title>Test</title></head><body><h1>Test</h1></body></html>"
    result = _parse_listing_html(html, "99999")
    assert result["id"] == "99999"
    assert result["title"] == "Test"
    assert result["price"] is None
    assert result["size_ping"] is None
    assert result["floor"] is None


def test_normalize_buy_listing():
    item = {
        "houseid": 12345678,
        "title": "南港區三房電梯大樓",
        "price": "2,680",
        "section_name": "南港區",
        "address": "研究院路",
        "area": "32.5",
        "floor": "5/12",
        "room": "3房2廳2衛",
        "showhouseage": "10年",
        "unitprice": "82.5",
        "kind_name": "電梯大樓",
        "shape_name": "3房2廳2衛",
        "tag": ["近捷運", "有車位"],
    }
    result = _normalize_buy_listing(item)
    assert result["id"] == "12345678"
    assert result["title"] == "南港區三房電梯大樓"
    assert result["price"] == "2,680"
    assert result["district"] == "南港區"
    assert result["size_ping"] == "32.5"
    assert result["houseage"] == "10年"
    assert result["unit_price"] == "82.5"
    assert result["kind_name"] == "電梯大樓"
    assert result["room"] == "3房2廳2衛"
    assert "sale.591.com.tw" in result["url"]


def test_extract_detail_fields_full():
    data = {
        "ware": {
            "mainarea": "18.5",
            "community_name": "VICTOR嘉醴",
            "position_lat": "25.033964",
            "position_lng": "121.543872",
        },
        "info": {
            "3": [
                {"name": "車位", "value": "10.53坪，平面式，已含售金內"},
                {"name": "公設比", "value": "51%"},
                {"name": "管理費", "value": "7900元/月"},
                {"name": "裝潢程度", "value": "高檔裝潢"},
                {"name": "型態", "value": "電梯大樓"},
            ],
            "2": [
                {"name": "朝向", "value": "坐南朝北"},
            ],
        },
    }
    result = _extract_detail_fields(data)
    assert result["main_area"] == 18.5
    assert result["community_name"] == "VICTOR嘉醴"
    assert result["parking_desc"] == "10.53坪，平面式，已含售金內"
    assert result["public_ratio"] == "51%"
    assert result["manage_price_desc"] == "7900元/月"
    assert result["fitment"] == "高檔裝潢"
    assert result["shape_name"] == "電梯大樓"
    assert result["direction"] == "坐南朝北"
    assert result["lat"] == pytest.approx(25.033964)
    assert result["lng"] == pytest.approx(121.543872)


def test_extract_detail_fields_empty():
    result = _extract_detail_fields({})
    assert result.get("main_area") is None
    assert result.get("community_name") is None
    assert result.get("parking_desc") is None
    assert result.get("lat") is None
    assert result.get("lng") is None


def test_extract_detail_fields_partial():
    data = {
        "ware": {"mainarea": "22.3"},
        "info": {
            "3": [
                {"name": "車位", "value": ""},
                {"name": "公設比", "value": "35%"},
            ],
        },
    }
    result = _extract_detail_fields(data)
    assert result["main_area"] == 22.3
    assert result.get("parking_desc") is None  # empty string -> None
    assert result["public_ratio"] == "35%"
    assert result.get("fitment") is None


def test_extract_detail_fields_with_coordinates():
    data = {
        "ware": {
            "mainarea": "18.5",
            "position_lat": "25.033964",
            "position_lng": "121.543872",
        },
        "info": {},
    }
    result = _extract_detail_fields(data)
    assert result["lat"] == pytest.approx(25.033964)
    assert result["lng"] == pytest.approx(121.543872)


def test_extract_detail_fields_lat_lng_fallback_keys():
    data = {
        "ware": {
            "lat": "25.1",
            "lng": "121.5",
        },
        "info": {},
    }
    result = _extract_detail_fields(data)
    assert result["lat"] == pytest.approx(25.1)
    assert result["lng"] == pytest.approx(121.5)


def test_extract_detail_fields_location_object_fallback():
    """When ware has no coords, fall back to location object."""
    data = {
        "ware": {"mainarea": "35.7"},
        "info": {},
        "location": {"lat": "25.0383780", "lng": "121.6237651"},
    }
    result = _extract_detail_fields(data)
    assert result["lat"] == pytest.approx(25.038378)
    assert result["lng"] == pytest.approx(121.6237651)


# --- scrape_listings parallel ---

def _multi_region_config(regions):
    return Config(
        search=SearchConfig(
            regions=regions,
            districts=["南港區"],
            price_min=2000,
            price_max=3000,
            mode="buy",
            min_ping=20,
            max_pages=1,
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10, max_retries=2, max_workers=4),
    )


def test_scrape_listings_multi_region_combined(monkeypatch):
    """Multiple regions returns combined results."""
    config = _multi_region_config([1, 3])

    def fake_scrape(cfg, progress_cb=None):
        rid = cfg.search.regions[0]
        return [{"listing_id": f"{rid}-1"}, {"listing_id": f"{rid}-2"}]

    with patch("tw_homedog.scraper.scrape_buy_listings", side_effect=fake_scrape):
        result = scrape_listings(config)

    assert len(result) == 4
    ids = {r["listing_id"] for r in result}
    assert ids == {"1-1", "1-2", "3-1", "3-2"}


def test_scrape_listings_single_region_direct():
    """Single region skips thread pool, direct call."""
    config = _multi_region_config([1])

    def fake_scrape(cfg, progress_cb=None):
        return [{"listing_id": "1-1"}]

    with patch("tw_homedog.scraper.scrape_buy_listings", side_effect=fake_scrape):
        result = scrape_listings(config)

    assert len(result) == 1
    assert result[0]["listing_id"] == "1-1"


def test_scrape_listings_one_region_failure():
    """One region failure returns other regions' results."""
    config = _multi_region_config([1, 3])

    def fake_scrape(cfg, progress_cb=None):
        rid = cfg.search.regions[0]
        if rid == 3:
            raise RuntimeError("network error")
        return [{"listing_id": f"{rid}-1"}]

    with patch("tw_homedog.scraper.scrape_buy_listings", side_effect=fake_scrape):
        result = scrape_listings(config)

    assert len(result) == 1
    assert result[0]["listing_id"] == "1-1"


def test_scrape_listings_progress_callback_thread_safe():
    """Progress callback invoked from parallel threads without error."""
    config = _multi_region_config([1, 3])
    messages = []

    def fake_scrape(cfg, progress_cb=None):
        rid = cfg.search.regions[0]
        if progress_cb:
            progress_cb(f"region {rid}")
        return [{"listing_id": f"{rid}-1"}]

    with patch("tw_homedog.scraper.scrape_buy_listings", side_effect=fake_scrape):
        result = scrape_listings(config, progress_cb=lambda m: messages.append(m))

    assert len(result) == 2
    assert len(messages) == 2
    assert set(messages) == {"region 1", "region 3"}


# --- fetch_buy_listing_detail status=0 top-level data ---

def test_fetch_buy_listing_detail_status0_toplevel():
    """status=0 response with ware/info/location at top level should succeed."""
    import requests as _requests

    mock_body = {
        "status": 0,
        "ware": {
            "mainarea": "18.5",
            "community_name": "測試社區",
            "position_lat": "",
            "position_lng": "",
        },
        "info": {
            "3": [
                {"name": "車位", "value": ""},
                {"name": "公設比", "value": "35%"},
            ],
        },
        "location": {"lat": "25.033964", "lng": "121.543872"},
    }

    class FakeResp:
        status_code = 200
        def json(self):
            return mock_body

    class FakeSession:
        def get(self, *a, **kw):
            return FakeResp()

    result = fetch_buy_listing_detail(FakeSession(), {}, "12345")
    assert result is not None
    assert result["main_area"] == 18.5
    assert result["community_name"] == "測試社區"
    assert result["public_ratio"] == "35%"
    assert result["lat"] == pytest.approx(25.033964)
    assert result["lng"] == pytest.approx(121.543872)


def test_fetch_buy_listing_detail_data_is_string():
    """When body['data'] is a string, fall back to top-level ware."""
    mock_body = {
        "status": 0,
        "data": "some string value",
        "ware": {
            "mainarea": "22.0",
            "community_name": "字串測試",
        },
        "info": {},
        "location": {"lat": "25.1", "lng": "121.5"},
    }

    class FakeResp:
        status_code = 200
        def json(self):
            return mock_body

    class FakeSession:
        def get(self, *a, **kw):
            return FakeResp()

    result = fetch_buy_listing_detail(FakeSession(), {}, "99999")
    assert result is not None
    assert result["main_area"] == 22.0
    assert result["lat"] == pytest.approx(25.1)
