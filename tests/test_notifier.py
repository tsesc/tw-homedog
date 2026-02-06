"""Tests for Telegram notifier."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tw_homedog.config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.notifier import format_listing_message, send_notifications, validate_bot_token
from tw_homedog.storage import Storage


def _listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "12345678",
        "title": "大安區電梯套房",
        "price": 35000,
        "district": "Daan",
        "size_ping": 28.0,
        "url": "https://rent.591.com.tw/12345678",
    }
    base.update(overrides)
    return base


def test_format_listing_message_rent():
    msg = format_listing_message(_listing(), mode="rent")
    assert "新房源符合條件" in msg
    assert "大安區電梯套房" in msg
    assert "Daan" in msg
    assert "NT$35,000/月" in msg
    assert "28.0 坪" in msg
    assert "https://rent.591.com.tw/12345678" in msg


def test_format_listing_message_buy():
    listing = _listing(price=2680, url="https://sale.591.com.tw/home/house/detail/2/123.html",
                       houseage="10年", unit_price="82.5", kind_name="電梯大樓", room="3房2廳2衛")
    msg = format_listing_message(listing, mode="buy")
    assert "新物件符合條件" in msg
    assert "2,680 萬" in msg
    assert "82.5 萬/坪" in msg
    assert "10年" in msg
    assert "電梯大樓" in msg
    assert "3房2廳2衛" in msg


def test_format_listing_missing_fields():
    msg = format_listing_message(_listing(price=None, size_ping=None, district=None), mode="rent")
    assert "未提供" in msg
    assert "未知" in msg


@pytest.fixture
def config():
    return Config(
        search=SearchConfig(region=1, districts=["Daan"], price_min=20000, price_max=40000, mode="rent"),
        telegram=TelegramConfig(bot_token="test:TOKEN", chat_id="123456"),
        database_path="data/test.db",
        scraper=ScraperConfig(),
    )


@patch("tw_homedog.notifier.Bot")
def test_send_notifications_success(mock_bot_cls, config, tmp_path):
    db = Storage(str(tmp_path / "test.db"))
    db.insert_listing({**_listing(), "raw_hash": "abc"})

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)
    mock_bot_cls.return_value = mock_bot

    count = send_notifications(config, db, [_listing()])
    assert count == 1
    assert db.is_notified("591", "12345678")
    db.close()


@patch("tw_homedog.notifier.Bot")
def test_send_notifications_failure_not_recorded(mock_bot_cls, config, tmp_path):
    db = Storage(str(tmp_path / "test.db"))
    db.insert_listing({**_listing(), "raw_hash": "abc"})

    mock_bot = MagicMock()
    from telegram.error import TelegramError
    mock_bot.send_message = AsyncMock(side_effect=TelegramError("test error"))
    mock_bot_cls.return_value = mock_bot

    count = send_notifications(config, db, [_listing()])
    assert count == 0
    assert not db.is_notified("591", "12345678")
    db.close()


@patch("tw_homedog.notifier.Bot")
def test_send_notifications_batch_limit(mock_bot_cls, config, tmp_path):
    db = Storage(str(tmp_path / "test.db"))

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)
    mock_bot_cls.return_value = mock_bot

    # Create 15 listings, should only send 10
    listings = [_listing(listing_id=str(i), raw_hash=f"h{i}") for i in range(15)]
    for l in listings:
        db.insert_listing(l)

    count = send_notifications(config, db, listings)
    assert count == 10
    assert mock_bot.send_message.call_count == 10
    db.close()
