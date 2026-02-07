"""Configuration loader and validator."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_FIELDS = {
    "search.region": (int, str),
    "search.districts": list,
    "search.price.min": (int, float),
    "search.price.max": (int, float),
    "telegram.bot_token": str,
    "telegram.chat_id": (str, int),
}

DEFAULTS = {
    "search.size.min_ping": None,
    "search.keywords.include": [],
    "search.keywords.exclude": [],
    "search.max_pages": 3,
    "database.path": "data/homedog.db",
    "scraper.delay_min": 2,
    "scraper.delay_max": 5,
    "scraper.timeout": 30,
    "scraper.max_retries": 3,
}


@dataclass
class SearchConfig:
    region: int
    districts: list[str]
    price_min: int | float
    price_max: int | float
    mode: str = "buy"  # "buy" or "rent"
    min_ping: float | None = None
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


@dataclass
class Config:
    search: SearchConfig
    telegram: TelegramConfig
    database_path: str
    scraper: ScraperConfig


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
    size = search.get("size", {})
    keywords = search.get("keywords", {})

    from tw_homedog.regions import resolve_region, EN_TO_ZH

    region = resolve_region(search["region"])

    # Convert English district names to Chinese (backward compat)
    raw_districts = search["districts"]
    districts = [EN_TO_ZH.get(d, d) for d in raw_districts]

    return Config(
        search=SearchConfig(
            region=region,
            districts=districts,
            price_min=search["price"]["min"],
            price_max=search["price"]["max"],
            mode=search.get("mode", "buy"),
            min_ping=size.get("min_ping"),
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
        ),
    )
