"""Tests for database-backed configuration management."""

import pytest

from tw_homedog.db_config import DbConfig
from tw_homedog.storage import Storage


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def db_config(storage):
    return DbConfig(storage.conn)


def test_get_missing_key_returns_default(db_config):
    assert db_config.get("nonexistent") is None
    assert db_config.get("nonexistent", 42) == 42


def test_set_and_get_string(db_config):
    db_config.set("search.mode", "buy")
    assert db_config.get("search.mode") == "buy"


def test_set_and_get_int(db_config):
    db_config.set("search.region", 1)
    assert db_config.get("search.region") == 1


def test_set_and_get_list(db_config):
    db_config.set("search.districts", ["大安區", "信義區"])
    assert db_config.get("search.districts") == ["大安區", "信義區"]


def test_set_and_get_none(db_config):
    db_config.set("search.min_ping", None)
    assert db_config.get("search.min_ping") is None


def test_set_overwrites(db_config):
    db_config.set("search.mode", "buy")
    db_config.set("search.mode", "rent")
    assert db_config.get("search.mode") == "rent"


def test_set_many(db_config):
    db_config.set_many({"search.mode": "buy", "search.region": 1})
    assert db_config.get("search.mode") == "buy"
    assert db_config.get("search.region") == 1


def test_delete_existing(db_config):
    db_config.set("search.mode", "buy")
    assert db_config.delete("search.mode") is True
    assert db_config.get("search.mode") is None


def test_delete_nonexistent(db_config):
    assert db_config.delete("nonexistent") is False


def test_get_all(db_config):
    db_config.set_many({"a": 1, "b": "two", "c": [3]})
    result = db_config.get_all()
    assert result == {"a": 1, "b": "two", "c": [3]}


def test_has_config_false_when_empty(db_config):
    assert db_config.has_config() is False


def test_has_config_true_with_required_key(db_config):
    db_config.set("search.region", 1)
    assert db_config.has_config() is True


def test_build_config_missing_required(db_config):
    with pytest.raises(ValueError, match="Missing required config keys"):
        db_config.build_config()


def test_build_config_with_chinese_districts(db_config):
    """Chinese district names in DB should pass through unchanged."""
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["大安區", "信義區"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "search.mode": "buy",
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
    })
    config = db_config.build_config()
    assert config.search.regions == [1]
    assert config.search.districts == ["大安區", "信義區"]
    assert config.search.price_min == 1000
    assert config.search.price_max == 3000
    assert config.search.mode == "buy"
    assert config.telegram.bot_token == "123:ABC"
    assert config.telegram.chat_id == "456"
    assert config.search.max_pages == 3  # default
    assert config.database_path == "data/homedog.db"  # default


def test_build_config_english_districts_converted(db_config):
    """English district names in DB should be converted to Chinese via EN_TO_ZH."""
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["Daan", "Xinyi", "Neihu"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
    })
    config = db_config.build_config()
    assert config.search.districts == ["大安區", "信義區", "內湖區"]


def test_build_config_mixed_districts(db_config):
    """Mix of English and Chinese district names — English converted, Chinese kept."""
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["Daan", "內湖區", "Wenshan"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
    })
    config = db_config.build_config()
    assert config.search.districts == ["大安區", "內湖區", "文山區"]


def test_build_config_with_all_fields(db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["大安區"],
        "search.price_min": 500,
        "search.price_max": 2000,
        "search.mode": "rent",
        "search.min_ping": 15.0,
        "search.keywords_include": ["電梯"],
        "search.keywords_exclude": ["頂加"],
        "search.max_pages": 5,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "789",
        "database.path": "/tmp/test.db",
        "scraper.delay_min": 3,
        "scraper.delay_max": 8,
        "scraper.timeout": 60,
        "scraper.max_retries": 5,
    })
    config = db_config.build_config()
    assert config.search.mode == "rent"
    assert config.search.min_ping == 15.0
    assert config.search.keywords_include == ["電梯"]
    assert config.search.keywords_exclude == ["頂加"]
    assert config.search.max_pages == 5
    assert config.database_path == "/tmp/test.db"
    assert config.scraper.delay_min == 3
    assert config.scraper.timeout == 60


def test_build_config_backward_compat_old_region(db_config):
    """Old 'search.region' (single int) format should still work."""
    db_config.set_many({
        "search.region": 1,
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
    })
    config = db_config.build_config()
    assert config.search.regions == [1]


def test_migrate_from_yaml(db_config, tmp_path):
    yaml_content = """
search:
  region: 1
  mode: buy
  districts:
    - Daan
    - Xinyi
  price:
    min: 1000
    max: 3000
  size:
    min_ping: 20
  keywords:
    include:
      - 電梯
    exclude:
      - 頂加
  max_pages: 5
telegram:
  bot_token: "123:ABC"
  chat_id: "456"
database:
  path: "data/my.db"
scraper:
  delay_min: 3
  delay_max: 8
"""
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text(yaml_content)

    count = db_config.migrate_from_yaml(str(yaml_file))
    assert count > 0

    config = db_config.build_config()
    assert config.search.regions == [1]
    # English names migrated from YAML are converted to Chinese in build_config
    assert config.search.districts == ["大安區", "信義區"]


def test_build_config_validates_size_range(db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
        "search.min_ping": 50,
        "search.max_ping": 40,
    })
    with pytest.raises(ValueError, match="min_ping must be <= search.max_ping"):
        db_config.build_config()


def test_build_config_validates_year_range(db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
        "search.year_built_min": 2025,
        "search.year_built_max": 2000,
    })
    with pytest.raises(ValueError, match="year_built_min must be <= search.year_built_max"):
        db_config.build_config()


def test_migrate_from_yaml_file_not_found(db_config):
    with pytest.raises(FileNotFoundError):
        db_config.migrate_from_yaml("/nonexistent/config.yaml")


def test_migrate_from_yaml_invalid_format(db_config, tmp_path):
    yaml_file = tmp_path / "bad.yaml"
    yaml_file.write_text("just a string")
    with pytest.raises(ValueError, match="Invalid config format"):
        db_config.migrate_from_yaml(str(yaml_file))
