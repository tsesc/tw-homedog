"""Integration test: full pipeline with mock 591 responses."""

import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.normalizer import normalize_591_listing
from tw_homedog.matcher import find_matching_listings
from tw_homedog.notifier import send_notifications
from tw_homedog.storage import Storage


@pytest.fixture
def config():
    return Config(
        search=SearchConfig(
            region=1,
            districts=["大安區"],
            price_min=20000,
            price_max=40000,
            mode="rent",
            min_ping=15,
            keywords_include=[],
            keywords_exclude=["頂樓"],
        ),
        telegram=TelegramConfig(bot_token="test:TOKEN", chat_id="123456"),
        database_path="",  # overridden per test
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10, max_retries=1),
    )


MOCK_RAW_LISTINGS = [
    {
        "id": "11111111",
        "title": "大安區電梯套房近捷運",
        "price": "35,000",
        "address": "台北市大安區忠孝東路",
        "district": "大安區",
        "size_ping": "28",
        "floor": "5F/12F",
        "url": "https://rent.591.com.tw/11111111",
    },
    {
        "id": "22222222",
        "title": "頂樓加蓋雅房",
        "price": "15,000",
        "address": "台北市萬華區",
        "district": "萬華區",
        "size_ping": "8",
        "floor": "6F/6F",
        "url": "https://rent.591.com.tw/22222222",
    },
    {
        "id": "33333333",
        "title": "中山區精裝公寓",
        "price": "30,000",
        "address": "台北市中山區",
        "district": "中山區",
        "size_ping": "22",
        "floor": "3F/5F",
        "url": "https://rent.591.com.tw/33333333",
    },
]


def test_full_pipeline_scrape_to_match(config, tmp_path):
    """Test: raw listings → normalize → store → match (no Telegram)."""
    db_path = str(tmp_path / "test.db")
    config.database_path = db_path
    storage = Storage(db_path)

    # Normalize and store
    for raw in MOCK_RAW_LISTINGS:
        normalized = normalize_591_listing(raw)
        storage.insert_listing(normalized)

    # Match
    matched = find_matching_listings(config, storage)

    # Only listing 11111111 should match:
    # - 22222222: excluded by keyword "頂樓" + wrong district + below min price
    # - 33333333: district 中山區 not in ["大安區"]
    assert len(matched) == 1
    assert matched[0]["listing_id"] == "11111111"
    storage.close()


@patch("tw_homedog.notifier.Bot")
def test_full_pipeline_with_notify(mock_bot_cls, config, tmp_path):
    """Test: full pipeline including Telegram mock."""
    db_path = str(tmp_path / "test.db")
    config.database_path = db_path
    storage = Storage(db_path)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)
    mock_bot_cls.return_value = mock_bot

    # Store matching listing
    normalized = normalize_591_listing(MOCK_RAW_LISTINGS[0])
    storage.insert_listing(normalized)

    # Match and notify
    matched = find_matching_listings(config, storage)
    assert len(matched) == 1

    sent = asyncio.run(send_notifications(config, storage, matched))
    assert sent == 1
    assert storage.is_notified("591", "11111111")

    # Second run: no new notifications
    matched_again = find_matching_listings(config, storage)
    assert len(matched_again) == 0

    storage.close()


def test_dedup_across_runs(config, tmp_path):
    """Test: same listings across multiple scrape runs are deduplicated."""
    db_path = str(tmp_path / "test.db")
    storage = Storage(db_path)

    # First "run"
    for raw in MOCK_RAW_LISTINGS:
        normalized = normalize_591_listing(raw)
        storage.insert_listing(normalized)

    count_after_first = len(storage.conn.execute("SELECT * FROM listings").fetchall())

    # Second "run" with same data
    for raw in MOCK_RAW_LISTINGS:
        normalized = normalize_591_listing(raw)
        storage.insert_listing(normalized)

    count_after_second = len(storage.conn.execute("SELECT * FROM listings").fetchall())
    assert count_after_first == count_after_second == 3

    storage.close()
