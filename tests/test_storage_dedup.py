import pytest

from tw_homedog.storage import Storage


@pytest.fixture
def db(tmp_path):
    s = Storage(str(tmp_path / "test_dedup.db"))
    yield s
    s.close()


def _listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "30001",
        "title": "南港陽光水岸三房",
        "price": 2980,
        "address": "台北市南港區向陽路258巷10號5樓",
        "district": "南港區",
        "size_ping": 36.5,
        "floor": "5/12",
        "url": "https://sale.591.com.tw/home/house/detail/2/30001.html",
        "published_at": "2025-01-01T00:00:00+00:00",
        "raw_hash": "hash-30001",
        "room": "3房2廳2衛",
        "community_name": "陽光水岸",
    }
    base.update(overrides)
    return base


def test_insert_listing_with_dedup_skips_duplicate_entity(db):
    first = db.insert_listing_with_dedup(_listing(), dedup_enabled=True)
    second = db.insert_listing_with_dedup(
        _listing(
            listing_id="30002",
            title="南港陽光水岸｜電梯大兩房車",
            address="臺北市南港區向陽路258巷10號",
            size_ping=36.49,
            price=2988,
            raw_hash="hash-30002",
        ),
        dedup_enabled=True,
    )

    assert first["inserted"] is True
    assert second["inserted"] is False
    assert second["reason"] == "duplicate_entity"

    rows = db.conn.execute("SELECT COUNT(*) AS c FROM listings").fetchone()
    assert rows["c"] == 1
    audit = db.conn.execute(
        "SELECT event_type, reason FROM dedup_audit ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert audit["event_type"] == "skip"


def test_insert_listing_with_batch_cache_skips_same_run_duplicates(db):
    batch_cache: dict[str, list[dict]] = {}
    a = db.insert_listing_with_dedup(
        _listing(), batch_cache=batch_cache, dedup_enabled=True
    )
    b = db.insert_listing_with_dedup(
        _listing(
            listing_id="30003",
            raw_hash="hash-30003",
            address="臺北市南港區向陽路258巷10號",
        ),
        batch_cache=batch_cache,
        dedup_enabled=True,
    )
    assert a["inserted"] is True
    assert b["inserted"] is False
    assert b["reason"] == "duplicate_entity"


def test_merge_duplicate_group_transfers_relations(db):
    db.insert_listing(_listing(listing_id="canon", raw_hash="hash-canon"))
    db.insert_listing(_listing(listing_id="dup", raw_hash="hash-dup", title="另一房仲文案"))

    db.record_notification("591", "dup", channel="telegram")
    db.mark_as_read("591", "dup")
    db.add_favorite("591", "dup")

    merged = db.merge_duplicate_group(
        source="591",
        canonical_listing_id="canon",
        duplicate_listing_ids=["dup"],
        score=0.93,
        reason="test-merge",
    )

    assert merged == 1
    assert db.get_listing_by_id("591", "dup") is None
    assert db.is_notified("591", "canon") is True
    assert db.is_favorite("591", "canon") is True

    read_row = db.conn.execute(
        "SELECT 1 FROM listings_read WHERE source='591' AND listing_id='canon'"
    ).fetchone()
    assert read_row is not None
    assert db.validate_relation_integrity() == {
        "notifications_sent": 0,
        "listings_read": 0,
        "favorites": 0,
    }


def test_backfill_entity_fingerprints_for_legacy_rows(db):
    db.insert_listing(_listing(listing_id="legacy-1", raw_hash="legacy-h1"))
    db.conn.execute(
        "UPDATE listings SET entity_fingerprint = NULL WHERE listing_id = 'legacy-1'"
    )
    db.conn.commit()

    updated = db.backfill_entity_fingerprints(source="591", recompute_existing=False)
    assert updated == 1

    row = db.conn.execute(
        "SELECT entity_fingerprint FROM listings WHERE source='591' AND listing_id='legacy-1'"
    ).fetchone()
    assert row["entity_fingerprint"] is not None
