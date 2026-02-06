"""Tests for match engine."""

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.matcher import match_price, match_district, match_size, match_keywords, find_matching_listings
from tw_homedog.storage import Storage


@pytest.fixture
def config():
    return Config(
        search=SearchConfig(
            region=1,
            districts=["Daan", "Zhongshan"],
            price_min=20000,
            price_max=40000,
            min_ping=20,
            keywords_include=["電梯"],
            keywords_exclude=["頂樓"],
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(),
    )


def _listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "123",
        "title": "大安區電梯套房",
        "price": 35000,
        "district": "Daan",
        "size_ping": 28.0,
    }
    base.update(overrides)
    return base


# Price filter tests
def test_price_within_range(config):
    assert match_price(_listing(price=35000), config) is True

def test_price_below_min(config):
    assert match_price(_listing(price=15000), config) is False

def test_price_above_max(config):
    assert match_price(_listing(price=50000), config) is False

def test_price_none_passes(config):
    assert match_price(_listing(price=None), config) is True

def test_price_open_ended_max(config):
    config.search.price_max = None
    assert match_price(_listing(price=999999), config) is True


# District filter tests
def test_district_match(config):
    assert match_district(_listing(district="Daan"), config) is True

def test_district_no_match(config):
    assert match_district(_listing(district="Wanhua"), config) is False

def test_district_none_passes(config):
    assert match_district(_listing(district=None), config) is True


# Size filter tests
def test_size_above_min(config):
    assert match_size(_listing(size_ping=28.0), config) is True

def test_size_below_min(config):
    assert match_size(_listing(size_ping=15.0), config) is False

def test_size_none_passes(config):
    assert match_size(_listing(size_ping=None), config) is True

def test_size_no_min_config(config):
    config.search.min_ping = None
    assert match_size(_listing(size_ping=5.0), config) is True


# Keyword filter tests
def test_keyword_include_match(config):
    assert match_keywords(_listing(title="大安區電梯套房"), config) is True

def test_keyword_include_no_match(config):
    assert match_keywords(_listing(title="大安區套房"), config) is False

def test_keyword_exclude_match(config):
    assert match_keywords(_listing(title="電梯頂樓套房"), config) is False

def test_keyword_no_config(config):
    config.search.keywords_include = []
    config.search.keywords_exclude = []
    assert match_keywords(_listing(title="anything"), config) is True


# Composite matcher test
def test_find_matching_listings(config, tmp_path):
    db = Storage(str(tmp_path / "test.db"))
    # Insert matching listing
    db.insert_listing({
        "source": "591", "listing_id": "111", "title": "大安區電梯套房",
        "price": 35000, "district": "Daan", "size_ping": 28.0,
        "raw_hash": "aaa",
    })
    # Insert non-matching listing (wrong district)
    db.insert_listing({
        "source": "591", "listing_id": "222", "title": "電梯套房",
        "price": 35000, "district": "Wanhua", "size_ping": 28.0,
        "raw_hash": "bbb",
    })
    # Insert already-notified listing
    db.insert_listing({
        "source": "591", "listing_id": "333", "title": "大安區電梯套房",
        "price": 35000, "district": "Daan", "size_ping": 28.0,
        "raw_hash": "ccc",
    })
    db.record_notification("591", "333")

    matched = find_matching_listings(config, db)
    assert len(matched) == 1
    assert matched[0]["listing_id"] == "111"
    db.close()
