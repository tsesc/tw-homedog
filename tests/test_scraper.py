"""Tests for 591 scraper (unit tests with mocks, no real HTTP)."""

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
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


def test_extract_detail_fields_empty():
    result = _extract_detail_fields({})
    assert result.get("main_area") is None
    assert result.get("community_name") is None
    assert result.get("parking_desc") is None


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
