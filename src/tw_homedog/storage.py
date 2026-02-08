"""SQLite storage for listings and notification tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tw_homedog.dedup import (
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_PRICE_TOLERANCE,
    DEFAULT_SIZE_TOLERANCE,
    build_entity_fingerprint,
    score_duplicate,
)


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
    entity_fingerprint TEXT,
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

CREATE TABLE IF NOT EXISTS listings_read (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    raw_hash TEXT,
    read_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, listing_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source, listing_id)
);

CREATE TABLE IF NOT EXISTS dedup_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    listing_id TEXT,
    canonical_listing_id TEXT,
    candidate_ids TEXT,
    score REAL,
    reason TEXT,
    entity_fingerprint TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dedup_audit_created_at
    ON dedup_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_dedup_audit_event_type
    ON dedup_audit(event_type);
"""


class Storage:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False avoids scheduler/thread callbacks crashing on shared DB handle.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self):
        """Add new columns/tables/indexes if they don't exist (for existing DBs)."""
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
            "entity_fingerprint": "TEXT",
            "is_enriched": "INTEGER DEFAULT 0",
        }
        for col, col_type in new_columns.items():
            if col not in existing:
                self.conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {col_type}")

        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_listings_fingerprint "
            "ON listings(source, entity_fingerprint)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS favorites ("
            "source TEXT NOT NULL, listing_id TEXT NOT NULL, "
            "added_at TEXT NOT NULL DEFAULT (datetime('now')), "
            "PRIMARY KEY (source, listing_id))"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS dedup_audit ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "event_type TEXT NOT NULL, source TEXT NOT NULL, listing_id TEXT, "
            "canonical_listing_id TEXT, candidate_ids TEXT, score REAL, reason TEXT, "
            "entity_fingerprint TEXT, metadata TEXT, "
            "created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dedup_audit_created_at "
            "ON dedup_audit(created_at)"
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dedup_audit_event_type "
            "ON dedup_audit(event_type)"
        )
        # Recompute fingerprints to keep old rows aligned with latest fingerprint rules.
        self.backfill_entity_fingerprints(recompute_existing=True)
        self.conn.commit()

    def backfill_entity_fingerprints(
        self,
        *,
        source: str | None = None,
        recompute_existing: bool = False,
        limit: int | None = None,
    ) -> int:
        """Populate/recompute entity fingerprint for historical rows."""
        conditions: list[str] = []
        params: list[Any] = []
        if source:
            conditions.append("source = ?")
            params.append(source)
        if not recompute_existing:
            conditions.append("(entity_fingerprint IS NULL OR entity_fingerprint = '')")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM listings {where_clause} ORDER BY id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        updated = 0
        for row in rows:
            listing = dict(row)
            fingerprint = build_entity_fingerprint(listing)
            if not fingerprint:
                continue
            if listing.get("entity_fingerprint") == fingerprint:
                continue
            self.conn.execute(
                "UPDATE listings SET entity_fingerprint = ? WHERE id = ?",
                (fingerprint, listing["id"]),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated

    def _normalize_listing(self, listing: dict) -> dict:
        normalized = dict(listing)
        normalized["source"] = str(normalized.get("source") or "591")
        normalized["listing_id"] = str(normalized.get("listing_id") or "")
        if not normalized.get("entity_fingerprint"):
            normalized["entity_fingerprint"] = build_entity_fingerprint(normalized)
        return normalized

    def _insert_listing_row(self, listing: dict) -> None:
        self.conn.execute(
            """INSERT INTO listings
               (source, listing_id, title, price, address, district,
                size_ping, floor, url, published_at, raw_hash, houseage,
                unit_price, kind_name, room, tags, community_name, entity_fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                listing.get("community_name"),
                listing.get("entity_fingerprint"),
            ),
        )

    def insert_listing_with_dedup(
        self,
        listing: dict,
        *,
        batch_cache: dict[str, list[dict]] | None = None,
        dedup_enabled: bool = False,
        dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
        price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
        size_tolerance: float = DEFAULT_SIZE_TOLERANCE,
    ) -> dict[str, Any]:
        """Insert listing and return dedup decision."""
        listing = self._normalize_listing(listing)
        source = listing["source"]
        listing_id = listing["listing_id"]
        fingerprint = listing.get("entity_fingerprint")
        result: dict[str, Any] = {
            "inserted": False,
            "reason": "",
            "score": None,
            "canonical_listing_id": None,
            "entity_fingerprint": fingerprint,
        }

        existing_id = self.conn.execute(
            "SELECT listing_id FROM listings WHERE source = ? AND listing_id = ?",
            (source, listing_id),
        ).fetchone()
        if existing_id:
            result["reason"] = "duplicate_listing_id"
            result["canonical_listing_id"] = existing_id["listing_id"]
            self.record_dedup_decision(
                event_type="skip",
                source=source,
                listing_id=listing_id,
                canonical_listing_id=existing_id["listing_id"],
                candidate_ids=[existing_id["listing_id"]],
                score=1.0,
                reason=result["reason"],
                entity_fingerprint=fingerprint,
            )
            return result

        if listing.get("raw_hash"):
            existing_hash = self.conn.execute(
                "SELECT listing_id, source FROM listings WHERE raw_hash = ? LIMIT 1",
                (listing["raw_hash"],),
            ).fetchone()
            if existing_hash:
                result["reason"] = "duplicate_raw_hash"
                result["canonical_listing_id"] = existing_hash["listing_id"]
                self.record_dedup_decision(
                    event_type="skip",
                    source=source,
                    listing_id=listing_id,
                    canonical_listing_id=existing_hash["listing_id"],
                    candidate_ids=[existing_hash["listing_id"]],
                    score=1.0,
                    reason=result["reason"],
                    entity_fingerprint=fingerprint,
                )
                return result

        if dedup_enabled and fingerprint:
            best_score = 0.0
            best_candidate: dict[str, Any] | None = None

            db_candidates = self.get_dedup_candidates(source, fingerprint)
            for candidate in db_candidates:
                scored = score_duplicate(
                    listing,
                    candidate,
                    price_tolerance=price_tolerance,
                    size_tolerance=size_tolerance,
                )
                if scored.score > best_score:
                    best_score = scored.score
                    best_candidate = {
                        "listing_id": candidate["listing_id"],
                        "reason": scored.reason,
                        "score": scored.score,
                    }

            if batch_cache:
                for candidate in batch_cache.get(fingerprint, []):
                    scored = score_duplicate(
                        listing,
                        candidate,
                        price_tolerance=price_tolerance,
                        size_tolerance=size_tolerance,
                    )
                    if scored.score > best_score:
                        best_score = scored.score
                        best_candidate = {
                            "listing_id": candidate.get("listing_id"),
                            "reason": f"batch:{scored.reason}",
                            "score": scored.score,
                        }

            if best_candidate and best_score >= dedup_threshold:
                result["reason"] = "duplicate_entity"
                result["score"] = round(best_score, 4)
                result["canonical_listing_id"] = best_candidate["listing_id"]
                self.record_dedup_decision(
                    event_type="skip",
                    source=source,
                    listing_id=listing_id,
                    canonical_listing_id=best_candidate["listing_id"],
                    candidate_ids=[best_candidate["listing_id"]],
                    score=best_score,
                    reason=best_candidate["reason"],
                    entity_fingerprint=fingerprint,
                )
                return result

        try:
            self._insert_listing_row(listing)
            self.conn.commit()
            if batch_cache is not None and fingerprint:
                batch_cache.setdefault(fingerprint, []).append(dict(listing))
            result["inserted"] = True
            result["reason"] = "inserted"
            return result
        except sqlite3.IntegrityError:
            result["reason"] = "duplicate_integrity"
            return result

    def insert_listing(self, listing: dict) -> bool:
        """Insert a listing if not duplicate. Returns True if inserted."""
        return bool(self.insert_listing_with_dedup(listing)["inserted"])

    def get_dedup_candidates(
        self,
        source: str,
        entity_fingerprint: str,
        *,
        exclude_listing_id: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        if not entity_fingerprint:
            return []
        params: list[Any] = [source, entity_fingerprint]
        sql = (
            "SELECT * FROM listings WHERE source = ? AND entity_fingerprint = ?"
        )
        if exclude_listing_id:
            sql += " AND listing_id != ?"
            params.append(exclude_listing_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def record_dedup_decision(
        self,
        *,
        event_type: str,
        source: str,
        listing_id: str | None,
        canonical_listing_id: str | None = None,
        candidate_ids: list[str] | None = None,
        score: float | None = None,
        reason: str | None = None,
        entity_fingerprint: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO dedup_audit
               (event_type, source, listing_id, canonical_listing_id, candidate_ids, score,
                reason, entity_fingerprint, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_type,
                source,
                listing_id,
                canonical_listing_id,
                json.dumps(candidate_ids or [], ensure_ascii=False),
                score,
                reason,
                entity_fingerprint,
                json.dumps(metadata or {}, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()

    def get_relation_counts(
        self,
        source: str,
        listing_ids: list[str],
    ) -> dict[str, dict[str, int]]:
        if not listing_ids:
            return {}

        placeholders = ",".join("?" for _ in listing_ids)
        params = [source] + listing_ids
        counts = {
            lid: {"notifications": 0, "reads": 0, "favorites": 0}
            for lid in listing_ids
        }

        notif_rows = self.conn.execute(
            f"""SELECT listing_id, COUNT(*) AS c FROM notifications_sent
                WHERE source = ? AND listing_id IN ({placeholders})
                GROUP BY listing_id""",
            params,
        ).fetchall()
        for row in notif_rows:
            counts[row["listing_id"]]["notifications"] = int(row["c"])

        read_rows = self.conn.execute(
            f"""SELECT listing_id, COUNT(*) AS c FROM listings_read
                WHERE source = ? AND listing_id IN ({placeholders})
                GROUP BY listing_id""",
            params,
        ).fetchall()
        for row in read_rows:
            counts[row["listing_id"]]["reads"] = int(row["c"])

        fav_rows = self.conn.execute(
            f"""SELECT listing_id, COUNT(*) AS c FROM favorites
                WHERE source = ? AND listing_id IN ({placeholders})
                GROUP BY listing_id""",
            params,
        ).fetchall()
        for row in fav_rows:
            counts[row["listing_id"]]["favorites"] = int(row["c"])

        return counts

    def merge_duplicate_group(
        self,
        *,
        source: str,
        canonical_listing_id: str,
        duplicate_listing_ids: list[str],
        score: float | None = None,
        reason: str = "cleanup_merge",
        entity_fingerprint: str | None = None,
    ) -> int:
        """Merge duplicate listings into canonical one inside a transaction."""
        if not duplicate_listing_ids:
            return 0

        duplicate_listing_ids = [
            str(lid)
            for lid in duplicate_listing_ids
            if str(lid) and str(lid) != str(canonical_listing_id)
        ]
        if not duplicate_listing_ids:
            return 0

        canonical = self.conn.execute(
            "SELECT raw_hash FROM listings WHERE source = ? AND listing_id = ?",
            (source, canonical_listing_id),
        ).fetchone()
        canonical_hash = canonical["raw_hash"] if canonical else None

        with self.conn:
            for dup in duplicate_listing_ids:
                self.conn.execute(
                    """INSERT OR IGNORE INTO notifications_sent (listing_id, source, channel, notified_at)
                       SELECT ?, source, channel, notified_at
                       FROM notifications_sent WHERE source = ? AND listing_id = ?""",
                    (canonical_listing_id, source, dup),
                )
                self.conn.execute(
                    """INSERT OR IGNORE INTO listings_read (source, listing_id, raw_hash, read_at)
                       SELECT source, ?, ?, read_at
                       FROM listings_read WHERE source = ? AND listing_id = ?""",
                    (canonical_listing_id, canonical_hash, source, dup),
                )
                self.conn.execute(
                    """INSERT OR IGNORE INTO favorites (source, listing_id, added_at)
                       SELECT source, ?, added_at
                       FROM favorites WHERE source = ? AND listing_id = ?""",
                    (canonical_listing_id, source, dup),
                )

                self.conn.execute(
                    "DELETE FROM notifications_sent WHERE source = ? AND listing_id = ?",
                    (source, dup),
                )
                self.conn.execute(
                    "DELETE FROM listings_read WHERE source = ? AND listing_id = ?",
                    (source, dup),
                )
                self.conn.execute(
                    "DELETE FROM favorites WHERE source = ? AND listing_id = ?",
                    (source, dup),
                )
                self.conn.execute(
                    "DELETE FROM listings WHERE source = ? AND listing_id = ?",
                    (source, dup),
                )

                self.conn.execute(
                    """INSERT INTO dedup_audit
                       (event_type, source, listing_id, canonical_listing_id, candidate_ids, score,
                        reason, entity_fingerprint, metadata, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        "merge",
                        source,
                        dup,
                        canonical_listing_id,
                        json.dumps([dup], ensure_ascii=False),
                        score,
                        reason,
                        entity_fingerprint,
                        json.dumps({}, ensure_ascii=False),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )

        return len(duplicate_listing_ids)

    def get_duplicate_fingerprint_groups(
        self,
        source: str = "591",
        min_group_size: int = 2,
    ) -> list[dict]:
        rows = self.conn.execute(
            """SELECT entity_fingerprint, COUNT(*) AS group_count
               FROM listings
               WHERE source = ? AND entity_fingerprint IS NOT NULL AND entity_fingerprint != ''
               GROUP BY entity_fingerprint
               HAVING COUNT(*) >= ?
               ORDER BY group_count DESC, entity_fingerprint ASC""",
            (source, min_group_size),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_all_listings(self, source: str = "591") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM listings WHERE source = ? ORDER BY created_at DESC, id DESC",
            (source,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_listings_by_fingerprint(self, source: str, entity_fingerprint: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM listings
               WHERE source = ? AND entity_fingerprint = ?
               ORDER BY created_at DESC, listing_id DESC""",
            (source, entity_fingerprint),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_dedup_audit_recent(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM dedup_audit ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def validate_relation_integrity(self) -> dict[str, int]:
        """Return orphan counts for relation tables that reference non-existing listings."""
        checks = {
            "notifications_sent": self.conn.execute(
                """SELECT COUNT(*) AS c
                   FROM notifications_sent n
                   LEFT JOIN listings l
                     ON l.source = n.source AND l.listing_id = n.listing_id
                   WHERE l.listing_id IS NULL"""
            ).fetchone()["c"],
            "listings_read": self.conn.execute(
                """SELECT COUNT(*) AS c
                   FROM listings_read r
                   LEFT JOIN listings l
                     ON l.source = r.source AND l.listing_id = r.listing_id
                   WHERE l.listing_id IS NULL"""
            ).fetchone()["c"],
            "favorites": self.conn.execute(
                """SELECT COUNT(*) AS c
                   FROM favorites f
                   LEFT JOIN listings l
                     ON l.source = f.source AND l.listing_id = f.listing_id
                   WHERE l.listing_id IS NULL"""
            ).fetchone()["c"],
        }
        return {k: int(v) for k, v in checks.items()}

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

    def get_unread_listings(self) -> list[dict]:
        """Get all listings that are unread (no read record or content changed)."""
        rows = self.conn.execute(
            """SELECT l.* FROM listings l
               LEFT JOIN listings_read r
                 ON l.source = r.source AND l.listing_id = r.listing_id
               WHERE r.source IS NULL OR l.raw_hash != r.raw_hash"""
        ).fetchall()
        return [dict(row) for row in rows]

    def get_listings_with_read_status(self) -> list[dict]:
        """Get all listings with is_read flag."""
        rows = self.conn.execute(
            """SELECT l.*, CASE WHEN r.listing_id IS NULL THEN 0
                                WHEN l.raw_hash = r.raw_hash THEN 1 ELSE 0 END AS is_read
               FROM listings l
               LEFT JOIN listings_read r
                 ON l.source = r.source AND l.listing_id = r.listing_id"""
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["is_read"] = bool(d.pop("is_read"))
            result.append(d)
        return result

    def mark_as_read(self, source: str, listing_id: str):
        """Mark a listing as read, recording its current raw_hash."""
        row = self.conn.execute(
            "SELECT raw_hash FROM listings WHERE source = ? AND listing_id = ?",
            (source, listing_id),
        ).fetchone()
        raw_hash = row["raw_hash"] if row else None
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO listings_read (source, listing_id, raw_hash, read_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source, listing_id)
               DO UPDATE SET raw_hash = excluded.raw_hash, read_at = excluded.read_at""",
            (source, listing_id, raw_hash, now),
        )
        self.conn.commit()

    def mark_many_as_read(self, source: str, listing_ids: list[str]):
        """Bulk mark listings as read with their current raw_hashes."""
        if not listing_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in listing_ids)
        rows = self.conn.execute(
            f"SELECT listing_id, raw_hash FROM listings WHERE source = ? AND listing_id IN ({placeholders})",
            [source] + listing_ids,
        ).fetchall()
        hash_map = {row["listing_id"]: row["raw_hash"] for row in rows}
        for lid in listing_ids:
            self.conn.execute(
                """INSERT INTO listings_read (source, listing_id, raw_hash, read_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(source, listing_id)
                   DO UPDATE SET raw_hash = excluded.raw_hash, read_at = excluded.read_at""",
                (source, lid, hash_map.get(lid), now),
            )
        self.conn.commit()

    def get_unread_count(self) -> int:
        """Get count of unread listings."""
        row = self.conn.execute(
            """SELECT COUNT(*) FROM listings l
               LEFT JOIN listings_read r
                 ON l.source = r.source AND l.listing_id = r.listing_id
               WHERE r.source IS NULL OR l.raw_hash != r.raw_hash"""
        ).fetchone()
        return row[0]

    def get_listing_by_id(self, source: str, listing_id: str) -> dict | None:
        """Get a single listing by source and listing_id."""
        row = self.conn.execute(
            "SELECT * FROM listings WHERE source = ? AND listing_id = ?",
            (source, listing_id),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------
    def add_favorite(self, source: str, listing_id: str) -> None:
        """Add a listing to favorites (idempotent)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO favorites (source, listing_id) VALUES (?, ?)",
            (source, listing_id),
        )
        self.conn.commit()

    def remove_favorite(self, source: str, listing_id: str) -> None:
        """Remove a listing from favorites."""
        self.conn.execute(
            "DELETE FROM favorites WHERE source = ? AND listing_id = ?",
            (source, listing_id),
        )
        self.conn.commit()

    def is_favorite(self, source: str, listing_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM favorites WHERE source = ? AND listing_id = ?",
            (source, listing_id),
        ).fetchone()
        return row is not None

    def get_favorites(self) -> list[dict]:
        """Return favorite listings with read status."""
        rows = self.conn.execute(
            """SELECT l.*, 1 AS is_favorite,
                      CASE WHEN r.listing_id IS NULL THEN 0
                           WHEN l.raw_hash = r.raw_hash THEN 1 ELSE 0 END AS is_read,
                      f.added_at
               FROM favorites f
               JOIN listings l ON l.source = f.source AND l.listing_id = f.listing_id
               LEFT JOIN listings_read r
                 ON l.source = r.source AND l.listing_id = r.listing_id
               ORDER BY f.added_at DESC"""
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["is_read"] = bool(d.pop("is_read"))
            d["is_favorite"] = bool(d.pop("is_favorite"))
            result.append(d)
        return result

    def clear_favorites(self):
        self.conn.execute("DELETE FROM favorites")
        self.conn.commit()

    def close(self):
        self.conn.close()
