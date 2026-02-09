"""Configuration loader and validator."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from tw_homedog.map_preview import MapConfig

REQUIRED_FIELDS = {
    # Accept either region (int/str) or regions (list) for backward compatibility
    # Will be validated separately in load_config
    "search.districts": list,
    "search.price.min": (int, float),
    "search.price.max": (int, float),
    "telegram.bot_token": str,
    "telegram.chat_id": (str, int),
}

DEFAULTS = {
    "search.size.min_ping": None,
    "search.size.max_ping": None,
    "search.room_counts": [],
    "search.bathroom_counts": [],
    "search.year_built.min": None,
    "search.year_built.max": None,
    "search.keywords.include": [],
    "search.keywords.exclude": [],
    "search.max_pages": 3,
    "database.path": "data/homedog.db",
    "scraper.delay_min": 2,
    "scraper.delay_max": 5,
    "scraper.timeout": 30,
    "scraper.max_retries": 3,
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
    "dedup.enabled": True,
    "dedup.threshold": 0.82,
    "dedup.price_tolerance": 0.05,
    "dedup.size_tolerance": 0.08,
    "dedup.cleanup_batch_size": 200,
}


@dataclass
class SearchConfig:
    regions: list[int]  # Changed from region: int to support multiple regions
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


def _get_nested(data: dict, dotted_key: str):
    """Get a value from nested dict using dotted key notation."""
    keys = dotted_key.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _validate(raw: dict) -> list[str]:
    """Validate required fields and types. Returns list of error messages."""
    errors = []
    for dotted_key, expected_type in REQUIRED_FIELDS.items():
        value = _get_nested(raw, dotted_key)
        if value is None:
            errors.append(f"Missing required field: {dotted_key}")
        elif not isinstance(value, expected_type):
            errors.append(
                f"Invalid type for {dotted_key}: expected {expected_type}, got {type(value).__name__}"
            )
    return errors


def _validate_filters(
    room_counts: list[int] | None,
    bathroom_counts: list[int] | None,
    size_min: float | None,
    size_max: float | None,
    year_min: int | None,
    year_max: int | None,
) -> list[str]:
    """Validate new filter fields and return error messages."""
    errors: list[str] = []

    def _check_counts(name: str, counts: list[int] | None):
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

    _check_counts("search.room_counts", room_counts)
    _check_counts("search.bathroom_counts", bathroom_counts)

    if size_min is not None and size_max is not None and size_min > size_max:
        errors.append("search.size.min_ping must be <= search.size.max_ping")

    if year_min is not None and year_max is not None and year_min > year_max:
        errors.append("search.year_built.min must be <= search.year_built.max")

    return errors


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. "
            "Copy config.example.yaml to config.yaml and fill in your values."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid config format: expected a YAML mapping, got {type(raw).__name__}")

    errors = _validate(raw)
    if errors:
        raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

    search = raw.get("search", {})
    telegram = raw.get("telegram", {})
    scraper_raw = raw.get("scraper", {})
    maps_raw = raw.get("maps", {})
    dedup_raw = raw.get("dedup", {})
    size = search.get("size", {})
    keywords = search.get("keywords", {})

    from tw_homedog.regions import resolve_region, EN_TO_ZH

    # Support both "region" (single) and "regions" (list) for backward compatibility
    regions_raw = search.get("regions")
    region_raw = search.get("region")

    if regions_raw is None and region_raw is None:
        raise ValueError("Config must specify either 'search.region' or 'search.regions'")

    if regions_raw is not None:
        # New format: regions as list
        if not isinstance(regions_raw, list):
            raise ValueError("search.regions must be a list")
        regions = [resolve_region(r) for r in regions_raw]
    else:
        # Old format: single region (backward compat)
        regions = [resolve_region(region_raw)]

    # Convert English district names to Chinese (backward compat)
    raw_districts = search["districts"]
    districts = [EN_TO_ZH.get(d, d) for d in raw_districts]

    room_counts = search.get("room_counts", [])
    bathroom_counts = search.get("bathroom_counts", [])
    year_built = search.get("year_built", {})
    year_built_min = year_built.get("min")
    year_built_max = year_built.get("max")
    size_max = size.get("max_ping")

    filter_errors = _validate_filters(
        room_counts, bathroom_counts, size.get("min_ping"), size_max, year_built_min, year_built_max
    )
    if filter_errors:
        raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in filter_errors))

    return Config(
        search=SearchConfig(
            regions=regions,
            districts=districts,
            price_min=search["price"]["min"],
            price_max=search["price"]["max"],
            mode=search.get("mode", "buy"),
            min_ping=size.get("min_ping"),
            max_ping=size_max,
            room_counts=room_counts or [],
            bathroom_counts=bathroom_counts or [],
            year_built_min=year_built_min,
            year_built_max=year_built_max,
            keywords_include=keywords.get("include", []),
            keywords_exclude=keywords.get("exclude", []),
            max_pages=search.get("max_pages", 3),
        ),
        telegram=TelegramConfig(
            bot_token=str(telegram["bot_token"]),
            chat_id=str(telegram["chat_id"]),
        ),
        database_path=raw.get("database", {}).get("path", "data/homedog.db"),
        scraper=ScraperConfig(
            delay_min=scraper_raw.get("delay_min", 2),
            delay_max=scraper_raw.get("delay_max", 5),
            timeout=scraper_raw.get("timeout", 30),
            max_retries=scraper_raw.get("max_retries", 3),
            max_workers=scraper_raw.get("max_workers", 4),
        ),
        maps=MapConfig(
            enabled=maps_raw.get("enabled", False),
            api_key=maps_raw.get("api_key"),
            base_url=maps_raw.get("base_url", DEFAULTS["maps.base_url"]),
            size=maps_raw.get("size", DEFAULTS["maps.size"]),
            zoom=maps_raw.get("zoom", DEFAULTS["maps.zoom"]),
            scale=maps_raw.get("scale", DEFAULTS["maps.scale"]),
            language=maps_raw.get("language", DEFAULTS["maps.language"]),
            region=maps_raw.get("region", DEFAULTS["maps.region"]),
            timeout=maps_raw.get("timeout", DEFAULTS["maps.timeout"]),
            cache_ttl_seconds=maps_raw.get("cache_ttl_seconds", DEFAULTS["maps.cache_ttl_seconds"]),
            cache_dir=maps_raw.get("cache_dir", DEFAULTS["maps.cache_dir"]),
            style=maps_raw.get("style", DEFAULTS["maps.style"]),
        ),
        dedup=DedupConfig(
            enabled=dedup_raw.get("enabled", DEFAULTS["dedup.enabled"]),
            threshold=dedup_raw.get("threshold", DEFAULTS["dedup.threshold"]),
            price_tolerance=dedup_raw.get("price_tolerance", DEFAULTS["dedup.price_tolerance"]),
            size_tolerance=dedup_raw.get("size_tolerance", DEFAULTS["dedup.size_tolerance"]),
            cleanup_batch_size=dedup_raw.get(
                "cleanup_batch_size", DEFAULTS["dedup.cleanup_batch_size"]
            ),
        ),
    )
