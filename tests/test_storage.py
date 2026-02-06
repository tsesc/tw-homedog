"""Tests for SQLite storage."""

import pytest

from tw_homedog.storage import Storage


@pytest.fixture
def db(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    yield s
    s.close()


def _make_listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "12345678",
        "title": "大安區電梯套房",
        "price": 35000,
        "address": "台北市大安區忠孝東路",
        "district": "Daan",
        "size_ping": 28.0,
        "floor": "5/12",
        "url": "https://rent.591.com.tw/12345678",
        "published_at": "2025-01-01",
        "raw_hash": "abc123",
    }
    base.update(overrides)
    return base


def test_init_creates_tables(db):
    tables = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {row["name"] for row in tables}
    assert "listings" in names
    assert "notifications_sent" in names


def test_insert_listing(db):
    assert db.insert_listing(_make_listing()) is True
    rows = db.conn.execute("SELECT * FROM listings").fetchall()
    assert len(rows) == 1
    assert rows[0]["listing_id"] == "12345678"


def test_dedup_by_source_listing_id(db):
    db.insert_listing(_make_listing())
    assert db.insert_listing(_make_listing(raw_hash="different")) is False


def test_dedup_by_content_hash(db):
    db.insert_listing(_make_listing())
    assert db.insert_listing(_make_listing(listing_id="99999999")) is False


def test_notification_tracking(db):
    db.insert_listing(_make_listing())
    assert db.is_notified("591", "12345678") is False
    db.record_notification("591", "12345678")
    assert db.is_notified("591", "12345678") is True


def test_get_unnotified_listings(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    db.record_notification("591", "111")
    unnotified = db.get_unnotified_listings()
    assert len(unnotified) == 1
    assert unnotified[0]["listing_id"] == "222"
