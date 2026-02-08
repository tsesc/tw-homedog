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


def test_update_listing_detail(db):
    db.insert_listing(_make_listing())
    detail = {
        "parking_desc": "10.53坪，平面式",
        "public_ratio": "51%",
        "manage_price_desc": "7900元/月",
        "fitment": "高檔裝潢",
        "shape_name": "電梯大樓",
        "community_name": "VICTOR嘉醴",
        "main_area": 18.5,
        "direction": "坐南朝北",
    }
    db.update_listing_detail("591", "12345678", detail)
    row = db.conn.execute("SELECT * FROM listings WHERE listing_id = '12345678'").fetchone()
    assert row["parking_desc"] == "10.53坪，平面式"
    assert row["public_ratio"] == "51%"
    assert row["manage_price_desc"] == "7900元/月"
    assert row["fitment"] == "高檔裝潢"
    assert row["shape_name"] == "電梯大樓"
    assert row["community_name"] == "VICTOR嘉醴"
    assert row["main_area"] == 18.5
    assert row["direction"] == "坐南朝北"
    assert row["is_enriched"] == 1


def test_is_enriched_default(db):
    db.insert_listing(_make_listing())
    row = db.conn.execute("SELECT is_enriched FROM listings WHERE listing_id = '12345678'").fetchone()
    assert row["is_enriched"] == 0


def test_get_unenriched_listing_ids(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    db.update_listing_detail("591", "111", {"parking_desc": "test"})
    unenriched = db.get_unenriched_listing_ids(["111", "222"])
    assert unenriched == ["222"]


def test_get_unenriched_listing_ids_empty(db):
    assert db.get_unenriched_listing_ids([]) == []


# --- listings_read tests ---

def test_init_creates_listings_read_table(db):
    tables = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {row["name"] for row in tables}
    assert "listings_read" in names


def test_mark_as_read(db):
    db.insert_listing(_make_listing())
    db.mark_as_read("591", "12345678")
    row = db.conn.execute(
        "SELECT * FROM listings_read WHERE source = '591' AND listing_id = '12345678'"
    ).fetchone()
    assert row is not None
    assert row["raw_hash"] == "abc123"


def test_mark_as_read_updates_on_reread(db):
    db.insert_listing(_make_listing())
    db.mark_as_read("591", "12345678")
    # Simulate content update
    db.conn.execute(
        "UPDATE listings SET raw_hash = 'new_hash' WHERE listing_id = '12345678'"
    )
    db.conn.commit()
    db.mark_as_read("591", "12345678")
    row = db.conn.execute(
        "SELECT raw_hash FROM listings_read WHERE source = '591' AND listing_id = '12345678'"
    ).fetchone()
    assert row["raw_hash"] == "new_hash"


def test_get_unread_listings_all_unread(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    unread = db.get_unread_listings()
    assert len(unread) == 2


def test_get_unread_listings_excludes_read(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    db.mark_as_read("591", "111")
    unread = db.get_unread_listings()
    assert len(unread) == 1
    assert unread[0]["listing_id"] == "222"


def test_get_unread_listings_content_change_resurfaces(db):
    db.insert_listing(_make_listing())
    db.mark_as_read("591", "12345678")
    # Simulate content update — raw_hash changes
    db.conn.execute(
        "UPDATE listings SET raw_hash = 'updated_hash' WHERE listing_id = '12345678'"
    )
    db.conn.commit()
    unread = db.get_unread_listings()
    assert len(unread) == 1
    assert unread[0]["listing_id"] == "12345678"


def test_get_unread_count(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    db.mark_as_read("591", "111")
    assert db.get_unread_count() == 1


def test_mark_many_as_read(db):
    db.insert_listing(_make_listing(listing_id="111"))
    db.insert_listing(_make_listing(listing_id="222", raw_hash="def456"))
    db.insert_listing(_make_listing(listing_id="333", raw_hash="ghi789"))
    db.mark_many_as_read("591", ["111", "222"])
    unread = db.get_unread_listings()
    assert len(unread) == 1
    assert unread[0]["listing_id"] == "333"


def test_mark_many_as_read_empty(db):
    db.mark_many_as_read("591", [])  # Should not raise


def test_get_listing_by_id(db):
    db.insert_listing(_make_listing())
    listing = db.get_listing_by_id("591", "12345678")
    assert listing is not None
    assert listing["title"] == "大安區電梯套房"


def test_get_listing_by_id_not_found(db):
    assert db.get_listing_by_id("591", "nonexistent") is None
