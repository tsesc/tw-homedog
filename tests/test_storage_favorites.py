import sqlite3
from pathlib import Path

from tw_homedog.storage import Storage


def _make_storage(tmp_path: Path) -> Storage:
    db = tmp_path / "test.db"
    return Storage(str(db))


def _insert_listing(storage: Storage, listing_id: str, raw_hash: str = "h"):
    storage.insert_listing({
        "source": "591",
        "listing_id": listing_id,
        "title": "t",
        "price": 100,
        "address": "addr",
        "district": "X",
        "size_ping": 10.5,
        "floor": "1F",
        "url": "https://example.com",
        "published_at": "2026-02-08",
        "raw_hash": raw_hash,
        "houseage": None,
        "unit_price": None,
        "kind_name": None,
        "room": None,
        "tags": [],
        "community_name": None,
    })


def test_favorite_add_get_and_read_flag(tmp_path):
    storage = _make_storage(tmp_path)
    _insert_listing(storage, "1", raw_hash="hash1")

    storage.add_favorite("591", "1")
    favs = storage.get_favorites()
    assert len(favs) == 1
    assert favs[0]["listing_id"] == "1"
    assert favs[0]["is_favorite"] is True
    assert favs[0]["is_read"] is False

    storage.mark_as_read("591", "1")
    favs = storage.get_favorites()
    assert favs[0]["is_read"] is True


def test_clear_favorites(tmp_path):
    storage = _make_storage(tmp_path)
    _insert_listing(storage, "1")
    _insert_listing(storage, "2", raw_hash="h2")
    storage.add_favorite("591", "1")
    storage.add_favorite("591", "2")

    storage.clear_favorites()
    assert storage.get_favorites() == []
