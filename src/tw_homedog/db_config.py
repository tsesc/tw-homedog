"""Database-backed configuration management and config dataclasses."""

import json
import logging
import sqlite3
from dataclasses import dataclass, field

from tw_homedog.map_preview import MapConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Config dataclasses
# =============================================================================


@dataclass
class SearchConfig:
    regions: list[int]
    districts: list[str]
    price_min: int | float
    price_max: int | float
    mode: str = "buy"  # "buy" or "rent"
    min_ping: float | None = None
    max_ping: float | None = None
    room_counts: list[int] = field(default_factory=list)
    bathroom_counts: list[int] = field(default_factory=list)
    year_built_min: int | None = None
    year_built_max: int | None = None
    keywords_include: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)
    max_pages: int = 3


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass
class ScraperConfig:
    delay_min: int = 2
    delay_max: int = 5
    timeout: int = 30
    max_retries: int = 3
    max_workers: int = 4


@dataclass
class DedupConfig:
    enabled: bool = True
    threshold: float = 0.82
    price_tolerance: float = 0.05
    size_tolerance: float = 0.08
    cleanup_batch_size: int = 200


@dataclass
class Config:
    search: SearchConfig
    telegram: TelegramConfig
    database_path: str
    scraper: ScraperConfig
    maps: MapConfig = field(
        default_factory=lambda: MapConfig(
            enabled=False,
            api_key=None,
        )
    )
    dedup: DedupConfig = field(default_factory=DedupConfig)


# =============================================================================
# DB-backed config store
# =============================================================================

REQUIRED_KEYS = [
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
    "scraper.max_workers": 4,
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
    "maps.monthly_limit": 10000,
    "dedup.enabled": True,
    "dedup.threshold": 0.82,
    "dedup.price_tolerance": 0.05,
    "dedup.size_tolerance": 0.08,
    "dedup.cleanup_batch_size": 200,
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
            if not isinstance(regions_raw, list):
                regions = [regions_raw]
            else:
                regions = regions_raw
        else:
            regions = [region_raw]

        districts = _get("search.districts", [])

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
                max_workers=_get("scraper.max_workers", 4),
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
                monthly_limit=_get("maps.monthly_limit", DEFAULTS["maps.monthly_limit"]),
            ),
            dedup=DedupConfig(
                enabled=_get("dedup.enabled", DEFAULTS["dedup.enabled"]),
                threshold=_get("dedup.threshold", DEFAULTS["dedup.threshold"]),
                price_tolerance=_get(
                    "dedup.price_tolerance", DEFAULTS["dedup.price_tolerance"]
                ),
                size_tolerance=_get("dedup.size_tolerance", DEFAULTS["dedup.size_tolerance"]),
                cleanup_batch_size=_get(
                    "dedup.cleanup_batch_size", DEFAULTS["dedup.cleanup_batch_size"]
                ),
            ),
        )
