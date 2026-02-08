"""Tests for match engine."""

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.matcher import (
    match_price,
    match_district,
    match_size,
    match_keywords,
    match_room,
    match_bathroom,
    match_build_year,
    find_matching_listings,
)
from tw_homedog.storage import Storage


@pytest.fixture
def config():
    return Config(
        search=SearchConfig(
            regions=[1],
            districts=["大安區", "中山區"],
            price_min=20000,
            price_max=40000,
            min_ping=20,
            max_ping=None,
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
        "district": "大安區",
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
    assert match_district(_listing(district="大安區"), config) is True

def test_district_no_match(config):
    assert match_district(_listing(district="萬華區"), config) is False

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


def test_size_max(config):
    config.search.max_ping = 30
    assert match_size(_listing(size_ping=28.0), config) is True
    assert match_size(_listing(size_ping=35.0), config) is False


# Room / bathroom filters
def test_room_filter(config):
    config.search.room_counts = [3]
    assert match_room(_listing(room="3房2廳2衛"), config) is True
    assert match_room(_listing(room="2房1廳1衛"), config) is False
    assert match_room(_listing(room=None), config) is True  # unknown allowed


def test_bath_filter(config):
    config.search.bathroom_counts = [2]
    assert match_bathroom(_listing(room="3房2廳2衛"), config) is True
    assert match_bathroom(_listing(room="3房2廳1衛"), config) is False


# Build year filter
def test_build_year_from_explicit(config):
    config.search.year_built_min = 2000
    config.search.year_built_max = 2015
    assert match_build_year(_listing(build_year=2010), config) is True
    assert match_build_year(_listing(build_year=1995), config) is False


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


def test_keyword_searches_room_field(config):
    config.search.keywords_include = ["3房"]
    config.search.keywords_exclude = []
    # Title doesn't have "3房" but room field does
    assert match_keywords(_listing(title="南港套房", room="3房2廳2衛"), config) is True
    assert match_keywords(_listing(title="南港套房", room="2房1廳1衛"), config) is False


def test_keyword_searches_tags_json(config):
    import json
    config.search.keywords_include = ["含車位"]
    config.search.keywords_exclude = []
    assert match_keywords(_listing(title="南港套房", tags=json.dumps(["含車位", "有陽台"])), config) is True
    assert match_keywords(_listing(title="南港套房", tags=json.dumps(["有陽台"])), config) is False


def test_keyword_exclude_in_tags(config):
    import json
    config.search.keywords_include = []
    config.search.keywords_exclude = ["頂加"]
    assert match_keywords(_listing(title="好房", tags=json.dumps(["頂加"])), config) is False


def test_keyword_searches_parking_desc(config):
    config.search.keywords_include = ["平面"]
    config.search.keywords_exclude = []
    assert match_keywords(_listing(title="南港套房", parking_desc="10.53坪，平面式"), config) is True
    assert match_keywords(_listing(title="南港套房", parking_desc="機械式"), config) is False


def test_keyword_searches_shape_name(config):
    config.search.keywords_include = ["電梯大樓"]
    config.search.keywords_exclude = []
    assert match_keywords(_listing(title="南港套房", shape_name="電梯大樓"), config) is True
    assert match_keywords(_listing(title="南港套房", shape_name="公寓"), config) is False


def test_keyword_searches_community_name(config):
    config.search.keywords_include = ["VICTOR"]
    config.search.keywords_exclude = []
    assert match_keywords(_listing(title="南港套房", community_name="VICTOR嘉醴"), config) is True


# Composite matcher test
def test_find_matching_listings(config, tmp_path):
    db = Storage(str(tmp_path / "test.db"))
    # Insert matching listing
    db.insert_listing({
        "source": "591", "listing_id": "111", "title": "大安區電梯套房",
        "price": 35000, "district": "大安區", "size_ping": 28.0,
        "raw_hash": "aaa",
    })
    # Insert non-matching listing (wrong district)
    db.insert_listing({
        "source": "591", "listing_id": "222", "title": "電梯套房",
        "price": 35000, "district": "萬華區", "size_ping": 28.0,
        "raw_hash": "bbb",
    })
    # Insert already-notified listing
    db.insert_listing({
        "source": "591", "listing_id": "333", "title": "大安區電梯套房",
        "price": 35000, "district": "大安區", "size_ping": 28.0,
        "raw_hash": "ccc",
    })
    db.record_notification("591", "333")

    matched = find_matching_listings(config, db)
    assert len(matched) == 1
    assert matched[0]["listing_id"] == "111"
    db.close()
