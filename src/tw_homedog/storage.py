"""SQLite storage for listings and notification tracking."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    title TEXT,
    price INTEGER,
    address TEXT,
    district TEXT,
    size_ping REAL,
    floor TEXT,
    url TEXT,
    published_at TEXT,
    raw_hash TEXT,
    houseage TEXT,
    unit_price TEXT,
    kind_name TEXT,
    room TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_listings_hash ON listings(raw_hash);

CREATE TABLE IF NOT EXISTS notifications_sent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    source TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'telegram',
    notified_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, listing_id, channel)
);
"""


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)

    def insert_listing(self, listing: dict) -> bool:
        """Insert a listing if not duplicate. Returns True if inserted."""
        # Check content hash duplicate
        if listing.get("raw_hash"):
            existing = self.conn.execute(
                "SELECT 1 FROM listings WHERE raw_hash = ?",
                (listing["raw_hash"],),
            ).fetchone()
            if existing:
                return False

        try:
            self.conn.execute(
                """INSERT INTO listings
                   (source, listing_id, title, price, address, district,
                    size_ping, floor, url, published_at, raw_hash,
                    houseage, unit_price, kind_name, room)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    listing["source"],
                    listing["listing_id"],
                    listing.get("title"),
                    listing.get("price"),
                    listing.get("address"),
                    listing.get("district"),
                    listing.get("size_ping"),
                    listing.get("floor"),
                    listing.get("url"),
                    listing.get("published_at"),
                    listing.get("raw_hash"),
                    listing.get("houseage"),
                    listing.get("unit_price"),
                    listing.get("kind_name"),
                    listing.get("room"),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def is_notified(self, source: str, listing_id: str, channel: str = "telegram") -> bool:
        """Check if a listing has already been notified."""
        row = self.conn.execute(
            "SELECT 1 FROM notifications_sent WHERE source = ? AND listing_id = ? AND channel = ?",
            (source, listing_id, channel),
        ).fetchone()
        return row is not None

    def record_notification(self, source: str, listing_id: str, channel: str = "telegram"):
        """Record that a notification was sent."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO notifications_sent (listing_id, source, channel, notified_at)
               VALUES (?, ?, ?, ?)""",
            (listing_id, source, channel, now),
        )
        self.conn.commit()

    def get_unnotified_listings(self, channel: str = "telegram") -> list[dict]:
        """Get all listings that haven't been notified yet."""
        rows = self.conn.execute(
            """SELECT l.* FROM listings l
               LEFT JOIN notifications_sent n
                 ON l.source = n.source AND l.listing_id = n.listing_id AND n.channel = ?
               WHERE n.id IS NULL""",
            (channel,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        self.conn.close()
