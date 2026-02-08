from tw_homedog.dedup_cleanup import run_cleanup
from tw_homedog.storage import Storage


def _listing(lid: str, **overrides):
    base = {
        "source": "591",
        "listing_id": lid,
        "title": "南港陽光水岸三房",
        "price": 2980,
        "address": "台北市南港區向陽路258巷10號5樓",
        "district": "南港區",
        "size_ping": 36.5,
        "floor": "5/12",
        "url": f"https://sale.591.com.tw/home/house/detail/2/{lid}.html",
        "published_at": "2025-01-01T00:00:00+00:00",
        "raw_hash": f"hash-{lid}",
        "room": "3房2廳2衛",
        "community_name": "陽光水岸",
    }
    base.update(overrides)
    return base


def test_cleanup_dry_run_and_apply(tmp_path):
    db = Storage(str(tmp_path / "cleanup.db"))
    try:
        db.insert_listing(_listing("a1"))
        db.insert_listing(
            _listing("a2", title="不同文案", address="臺北市南港區向陽路258巷10號", price=2990)
        )
        db.insert_listing(
            _listing(
                "a3",
                title="青年守則日系風格4房+車",
                room="4房2廳2衛",
                address="汐止區 建成路56巷",
                district="汐止區",
                size_ping=58.82,
                floor="20F/23F",
                price=2480,
            )
        )
        db.insert_listing(
            _listing(
                "a4",
                title="汐止國泰醫院旁3房+車位",
                room="3房2廳2衛",
                address="汐止區 建成路56巷",
                district="汐止區",
                size_ping=58.82,
                floor="20F/23F",
                price=2480,
            )
        )
        db.insert_listing(_listing("b1", address="台北市南港區研究院路二段70巷1號", raw_hash="hash-b1"))

        # Simulate legacy database that has no entity fingerprints.
        db.conn.execute("UPDATE listings SET entity_fingerprint = NULL")
        db.conn.commit()

        dry = run_cleanup(db, dry_run=True, batch_size=50)
        assert dry["dry_run"] is True
        assert dry["groups"] >= 1
        before = db.get_listing_count()

        applied = run_cleanup(db, dry_run=False, batch_size=50)
        assert applied["dry_run"] is False
        assert applied["merged_records"] >= 1
        assert db.get_listing_count() == before - applied["merged_records"]
        assert applied["validation"] == {
            "notifications_sent": 0,
            "listings_read": 0,
            "favorites": 0,
        }
    finally:
        db.close()
