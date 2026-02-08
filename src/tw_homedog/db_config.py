"""Database-backed configuration management."""

import json
import logging
import sqlite3
from pathlib import Path

import yaml

from tw_homedog.config import Config, ScraperConfig, SearchConfig, TelegramConfig
from tw_homedog.map_preview import MapConfig
from tw_homedog.regions import EN_TO_ZH

logger = logging.getLogger(__name__)

REQUIRED_KEYS = [
    # Accept either search.region or search.regions for backward compatibility
    "search.districts",
    "search.price_min",
    "search.price_max",
    "telegram.bot_token",
    "telegram.chat_id",
]

DEFAULTS = {
    "search.mode": "buy",
    "search.min_ping": None,
    "search.max_ping": None,
    "search.room_counts": [],
    "search.bathroom_counts": [],
    "search.year_built_min": None,
    "search.year_built_max": None,
    "search.keywords_include": [],
    "search.keywords_exclude": [],
    "search.max_pages": 3,
    "database.path": "data/homedog.db",
    "scraper.delay_min": 2,
    "scraper.delay_max": 5,
    "scraper.timeout": 30,
    "scraper.max_retries": 3,
    "scheduler.interval_minutes": 120,
    "maps.enabled": False,
    "maps.base_url": "https://maps.googleapis.com/maps/api/staticmap",
    "maps.size": "640x400",
    "maps.zoom": None,
    "maps.scale": 2,
    "maps.language": "zh-TW",
    "maps.region": "tw",
    "maps.timeout": 6,
    "maps.cache_ttl_seconds": 86400,
    "maps.cache_dir": "data/map_cache",
    "maps.style": None,
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
        # Also check for region/regions (backward compat)
        extended_keys = REQUIRED_KEYS + ["search.region", "search.regions"]
        row = self.conn.execute(
            "SELECT COUNT(*) FROM bot_config WHERE key IN ({})".format(
                ",".join("?" for _ in extended_keys)
            ),
            extended_keys,
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

        # Support both region (single) and regions (list) for backward compatibility
        regions_raw = _get("search.regions")
        region_raw = _get("search.region")

        if regions_raw is None and region_raw is None:
            raise ValueError("Config must specify either 'search.region' or 'search.regions'")

        if regions_raw is not None:
            # New format: regions as list
            if not isinstance(regions_raw, list):
                regions = [regions_raw]
            else:
                regions = regions_raw
        else:
            # Old format: single region (backward compat)
            regions = [region_raw]

        # Convert English district names to Chinese for backward compatibility
        raw_districts = _get("search.districts", [])
        districts = [EN_TO_ZH.get(d, d) for d in raw_districts]

        def _validate_filters():
            errors: list[str] = []

            def _check_counts(name: str, counts):
                if counts is None:
                    return
                if not isinstance(counts, list):
                    errors.append(f"{name} must be a list")
                    return
                for c in counts:
                    if not isinstance(c, int):
                        errors.append(f"{name} values must be integers")
                        break
                    if c < 1 or c > 5:
                        errors.append(f"{name} values must be between 1 and 5")
                        break

            room_counts = _get("search.room_counts", [])
            bath_counts = _get("search.bathroom_counts", [])
            size_min = _get("search.min_ping")
            size_max = _get("search.max_ping")
            year_min = _get("search.year_built_min")
            year_max = _get("search.year_built_max")

            _check_counts("search.room_counts", room_counts)
            _check_counts("search.bathroom_counts", bath_counts)

            if size_min is not None and size_max is not None and size_min > size_max:
                errors.append("search.min_ping must be <= search.max_ping")
            if year_min is not None and year_max is not None and year_min > year_max:
                errors.append("search.year_built_min must be <= search.year_built_max")

            if errors:
                raise ValueError("Invalid config:\n" + "\n".join(f"  - {e}" for e in errors))

        _validate_filters()

        return Config(
            search=SearchConfig(
                regions=regions,
                districts=districts,
                price_min=_get("search.price_min"),
                price_max=_get("search.price_max"),
                mode=_get("search.mode", "buy"),
                min_ping=_get("search.min_ping"),
                max_ping=_get("search.max_ping"),
                room_counts=_get("search.room_counts", []),
                bathroom_counts=_get("search.bathroom_counts", []),
                year_built_min=_get("search.year_built_min"),
                year_built_max=_get("search.year_built_max"),
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
            maps=MapConfig(
                enabled=_get("maps.enabled", False),
                api_key=_get("maps.api_key"),
                base_url=_get("maps.base_url", DEFAULTS["maps.base_url"]),
                size=_get("maps.size", DEFAULTS["maps.size"]),
                zoom=_get("maps.zoom", DEFAULTS["maps.zoom"]),
                scale=_get("maps.scale", DEFAULTS["maps.scale"]),
                language=_get("maps.language", DEFAULTS["maps.language"]),
                region=_get("maps.region", DEFAULTS["maps.region"]),
                timeout=_get("maps.timeout", DEFAULTS["maps.timeout"]),
                cache_ttl_seconds=_get("maps.cache_ttl_seconds", DEFAULTS["maps.cache_ttl_seconds"]),
                cache_dir=_get("maps.cache_dir", DEFAULTS["maps.cache_dir"]),
                style=_get("maps.style", DEFAULTS["maps.style"]),
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
        if "room_counts" in search:
            items["search.room_counts"] = search["room_counts"]
        if "bathroom_counts" in search:
            items["search.bathroom_counts"] = search["bathroom_counts"]
        if "min" in price:
            items["search.price_min"] = price["min"]
        if "max" in price:
            items["search.price_max"] = price["max"]
        if "mode" in search:
            items["search.mode"] = search["mode"]
        if "min_ping" in size:
            items["search.min_ping"] = size["min_ping"]
        if "max_ping" in size:
            items["search.max_ping"] = size["max_ping"]
        if "year_built" in search:
            year_built = search.get("year_built", {})
            if "min" in year_built:
                items["search.year_built_min"] = year_built["min"]
            if "max" in year_built:
                items["search.year_built_max"] = year_built["max"]
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
