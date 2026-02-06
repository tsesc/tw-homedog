"""Tests for 591 scraper (unit tests with mocks, no real HTTP)."""

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.scraper import (
    build_search_url,
    _parse_listing_html,
    _normalize_buy_listing,
    RENT_DISTRICT_CODES,
    BUY_DISTRICT_CODES,
    ZH_TO_EN_DISTRICT,
)


@pytest.fixture
def rent_config():
    return Config(
        search=SearchConfig(
            region=1,
            districts=["Daan", "Zhongshan"],
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
            region=1,
            districts=["Nangang", "Neihu"],
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
    url = build_search_url(rent_config, RENT_DISTRICT_CODES["Daan"])
    assert "region=1" in url
    assert "section=7" in url
    assert "price=20000_40000" in url
    assert "area=20_" in url
    assert "kind=0" in url


def test_build_search_url_no_min_ping(rent_config):
    rent_config.search.min_ping = None
    url = build_search_url(rent_config, 7)
    assert "area=" not in url


def test_rent_district_codes():
    assert RENT_DISTRICT_CODES["Daan"] == 7
    assert RENT_DISTRICT_CODES["Zhongshan"] == 1
    assert len(RENT_DISTRICT_CODES) == 12


def test_buy_district_codes():
    assert BUY_DISTRICT_CODES["Neihu"] == 10
    assert BUY_DISTRICT_CODES["Nangang"] == 11
    assert BUY_DISTRICT_CODES["Daan"] == 5
    assert len(BUY_DISTRICT_CODES) == 12


def test_zh_to_en_district():
    assert ZH_TO_EN_DISTRICT["內湖區"] == "Neihu"
    assert ZH_TO_EN_DISTRICT["南港區"] == "Nangang"
    assert len(ZH_TO_EN_DISTRICT) == 12


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
    assert result["district"] == "Daan"
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
    assert result["district"] == "Nangang"
    assert result["size_ping"] == "32.5"
    assert result["houseage"] == "10年"
    assert result["unit_price"] == "82.5"
    assert result["kind_name"] == "電梯大樓"
    assert result["room"] == "3房2廳2衛"
    assert "sale.591.com.tw" in result["url"]
