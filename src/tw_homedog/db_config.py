"""Database-backed configuration management."""

import json
import logging
import sqlite3
from pathlib import Path

import yaml

from tw_homedog.config import Config, ScraperConfig, SearchConfig, TelegramConfig
from tw_homedog.regions import EN_TO_ZH

logger = logging.getLogger(__name__)

REQUIRED_KEYS = [
    "search.region",
    "search.districts",
    "search.price_min",
    "search.price_max",
    "telegram.bot_token",
    "telegram.chat_id",
]

DEFAULTS = {
    "search.mode": "buy",
    "search.min_ping": None,
    "search.keywords_include": [],
    "search.keywords_exclude": [],
    "search.max_pages": 3,
    "database.path": "data/homedog.db",
    "scraper.delay_min": 2,
    "scraper.delay_max": 5,
    "scraper.timeout": 30,
    "scraper.max_retries": 3,
    "scheduler.interval_minutes": 30,
}


class DbConfig:
    """Read/write configuration stored in SQLite bot_config table."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, key: str, default=None):
        """Get a config value by key. Returns deserialized JSON value."""
        row = self.conn.execute(
            "SELECT value FROM bot_config WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return json.loads(row[0] if isinstance(row, tuple) else row["value"])

    def set(self, key: str, value) -> None:
        """Set a config value. Value is JSON-serialized."""
        self.conn.execute(
            "INSERT INTO bot_config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def set_many(self, items: dict) -> None:
        """Set multiple config values atomically."""
        for key, value in items.items():
            self.conn.execute(
                "INSERT INTO bot_config (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        self.conn.commit()

    def delete(self, key: str) -> bool:
        """Delete a config key. Returns True if key existed."""
        cursor = self.conn.execute("DELETE FROM bot_config WHERE key = ?", (key,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all(self) -> dict:
        """Get all config key-value pairs."""
        rows = self.conn.execute("SELECT key, value FROM bot_config").fetchall()
        return {
            (r[0] if isinstance(r, tuple) else r["key"]): json.loads(
                r[1] if isinstance(r, tuple) else r["value"]
            )
            for r in rows
        }

    def has_config(self) -> bool:
        """Check if any required config keys exist (i.e. setup has been done)."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM bot_config WHERE key IN ({})".format(
                ",".join("?" for _ in REQUIRED_KEYS)
            ),
            REQUIRED_KEYS,
        ).fetchone()
        count = row[0] if isinstance(row, tuple) else row[0]
        return count > 0

    def build_config(self) -> Config:
        """Build a Config dataclass from DB values. Raises ValueError if required fields missing."""
        all_vals = self.get_all()

        def _get(key: str, default=None):
            if key in all_vals:
                return all_vals[key]
            if key in DEFAULTS:
                return DEFAULTS[key]
            return default

        missing = [k for k in REQUIRED_KEYS if k not in all_vals]
        if missing:
            raise ValueError(
                "Missing required config keys:\n" + "\n".join(f"  - {k}" for k in missing)
            )

        # Convert English district names to Chinese for backward compatibility
        raw_districts = _get("search.districts", [])
        districts = [EN_TO_ZH.get(d, d) for d in raw_districts]

        return Config(
            search=SearchConfig(
                region=_get("search.region"),
                districts=districts,
                price_min=_get("search.price_min"),
                price_max=_get("search.price_max"),
                mode=_get("search.mode", "buy"),
                min_ping=_get("search.min_ping"),
                keywords_include=_get("search.keywords_include", []),
                keywords_exclude=_get("search.keywords_exclude", []),
                max_pages=_get("search.max_pages", 3),
            ),
            telegram=TelegramConfig(
                bot_token=str(_get("telegram.bot_token")),
                chat_id=str(_get("telegram.chat_id")),
            ),
            database_path=_get("database.path", "data/homedog.db"),
            scraper=ScraperConfig(
                delay_min=_get("scraper.delay_min", 2),
                delay_max=_get("scraper.delay_max", 5),
                timeout=_get("scraper.timeout", 30),
                max_retries=_get("scraper.max_retries", 3),
            ),
        )

    def migrate_from_yaml(self, path: str | Path) -> int:
        """Import config from a YAML file into bot_config table. Returns number of keys imported."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"Invalid config format: expected mapping, got {type(raw).__name__}")

        items = {}
        search = raw.get("search", {})
        telegram = raw.get("telegram", {})
        scraper = raw.get("scraper", {})
        price = search.get("price", {})
        size = search.get("size", {})
        keywords = search.get("keywords", {})

        if "region" in search:
            items["search.region"] = search["region"]
        if "districts" in search:
            items["search.districts"] = search["districts"]
        if "min" in price:
            items["search.price_min"] = price["min"]
        if "max" in price:
            items["search.price_max"] = price["max"]
        if "mode" in search:
            items["search.mode"] = search["mode"]
        if "min_ping" in size:
            items["search.min_ping"] = size["min_ping"]
        if "include" in keywords:
            items["search.keywords_include"] = keywords["include"]
        if "exclude" in keywords:
            items["search.keywords_exclude"] = keywords["exclude"]
        if "max_pages" in search:
            items["search.max_pages"] = search["max_pages"]

        if "bot_token" in telegram:
            items["telegram.bot_token"] = str(telegram["bot_token"])
        if "chat_id" in telegram:
            items["telegram.chat_id"] = str(telegram["chat_id"])

        db_path = raw.get("database", {}).get("path")
        if db_path:
            items["database.path"] = db_path

        for key in ("delay_min", "delay_max", "timeout", "max_retries"):
            if key in scraper:
                items[f"scraper.{key}"] = scraper[key]

        self.set_many(items)
        logger.info("Migrated %d config keys from %s", len(items), path)
        return len(items)
