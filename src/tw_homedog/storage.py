"""SQLite storage for listings and notification tracking."""

import json
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
    tags TEXT,
    parking_desc TEXT,
    public_ratio TEXT,
    manage_price_desc TEXT,
    fitment TEXT,
    shape_name TEXT,
    community_name TEXT,
    main_area REAL,
    direction TEXT,
    is_enriched INTEGER DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        self._migrate()

    def _migrate(self):
        """Add new columns if they don't exist (for existing DBs)."""
        existing = {
            row[1]
            for row in self.conn.execute("PRAGMA table_info(listings)").fetchall()
        }
        new_columns = {
            "parking_desc": "TEXT",
            "public_ratio": "TEXT",
            "manage_price_desc": "TEXT",
            "fitment": "TEXT",
            "shape_name": "TEXT",
            "community_name": "TEXT",
            "main_area": "REAL",
            "direction": "TEXT",
            "is_enriched": "INTEGER DEFAULT 0",
        }
        for col, col_type in new_columns.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {col_type}")

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
                    houseage, unit_price, kind_name, room, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    json.dumps(listing.get("tags") or [], ensure_ascii=False),
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

    def update_listing_detail(self, source: str, listing_id: str, detail: dict):
        """Update a listing with detail enrichment data."""
        self.conn.execute(
            """UPDATE listings SET
                parking_desc = ?, public_ratio = ?, manage_price_desc = ?,
                fitment = ?, shape_name = ?, community_name = ?,
                main_area = ?, direction = ?, is_enriched = 1
               WHERE source = ? AND listing_id = ?""",
            (
                detail.get("parking_desc"),
                detail.get("public_ratio"),
                detail.get("manage_price_desc"),
                detail.get("fitment"),
                detail.get("shape_name"),
                detail.get("community_name"),
                detail.get("main_area"),
                detail.get("direction"),
                source,
                listing_id,
            ),
        )
        self.conn.commit()

    def get_unenriched_listing_ids(self, listing_ids: list[str], source: str = "591") -> list[str]:
        """Return listing_ids that haven't been enriched yet."""
        if not listing_ids:
            return []
        placeholders = ",".join("?" for _ in listing_ids)
        rows = self.conn.execute(
            f"""SELECT listing_id FROM listings
                WHERE source = ? AND listing_id IN ({placeholders})
                AND is_enriched = 0""",
            [source] + listing_ids,
        ).fetchall()
        return [row["listing_id"] for row in rows]

    def get_listing_count(self) -> int:
        """Get total number of listings in DB."""
        row = self.conn.execute("SELECT COUNT(*) FROM listings").fetchone()
        return row[0]

    def get_unnotified_count(self, channel: str = "telegram") -> int:
        """Get count of unnotified listings."""
        row = self.conn.execute(
            """SELECT COUNT(*) FROM listings l
               LEFT JOIN notifications_sent n
                 ON l.source = n.source AND l.listing_id = n.listing_id AND n.channel = ?
               WHERE n.id IS NULL""",
            (channel,),
        ).fetchone()
        return row[0]

    def close(self):
        self.conn.close()
