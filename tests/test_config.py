"""Tests for config loader."""

import pytest
import yaml

from tw_homedog.config import load_config, Config


@pytest.fixture
def valid_config_data():
    return {
        "search": {
            "region": "台北市",
            "districts": ["大安區", "中山區"],
            "price": {"min": 20000, "max": 40000},
            "size": {"min_ping": 20},
            "keywords": {"include": ["電梯"], "exclude": ["頂樓"]},
            "max_pages": 3,
        },
        "telegram": {"bot_token": "123:ABC", "chat_id": "456"},
        "database": {"path": "data/test.db"},
        "scraper": {"delay_min": 2, "delay_max": 5, "timeout": 30, "max_retries": 3},
    }


@pytest.fixture
def config_file(tmp_path, valid_config_data):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    return p


def test_load_valid_config(config_file):
    cfg = load_config(config_file)
    assert isinstance(cfg, Config)
    assert cfg.search.regions == [1]  # "台北市" resolved to [1]
    assert cfg.search.districts == ["大安區", "中山區"]
    assert cfg.search.price_min == 20000
    assert cfg.search.price_max == 40000
    assert cfg.search.min_ping == 20
    assert cfg.search.keywords_include == ["電梯"]
    assert cfg.search.keywords_exclude == ["頂樓"]
    assert cfg.telegram.bot_token == "123:ABC"
    assert cfg.telegram.chat_id == "456"
    assert cfg.database_path == "data/test.db"


def test_load_config_numeric_region(tmp_path, valid_config_data):
    valid_config_data["search"]["region"] = 1
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    cfg = load_config(p)
    assert cfg.search.regions == [1]


def test_load_config_english_districts_backward_compat(tmp_path, valid_config_data):
    valid_config_data["search"]["districts"] = ["Daan", "Zhongshan"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    cfg = load_config(p)
    assert cfg.search.districts == ["大安區", "中山區"]


def test_load_config_mixed_districts(tmp_path, valid_config_data):
    valid_config_data["search"]["districts"] = ["大安區", "Zhongshan"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    cfg = load_config(p)
    assert cfg.search.districts == ["大安區", "中山區"]


def test_config_file_not_found():
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/config.yaml")


def test_invalid_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(": invalid: yaml: {{{{")
    with pytest.raises(Exception):
        load_config(p)


def test_missing_required_field(tmp_path, valid_config_data):
    del valid_config_data["telegram"]["bot_token"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    with pytest.raises(ValueError, match="Missing required field.*telegram.bot_token"):
        load_config(p)


def test_regions_list_format(tmp_path, valid_config_data):
    """New 'regions' list format should work."""
    del valid_config_data["search"]["region"]
    valid_config_data["search"]["regions"] = ["台北市", "新北市"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    cfg = load_config(p)
    assert cfg.search.regions == [1, 3]


def test_regions_must_be_list(tmp_path, valid_config_data):
    """regions as non-list should raise ValueError."""
    del valid_config_data["search"]["region"]
    valid_config_data["search"]["regions"] = "台北市"
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    with pytest.raises(ValueError, match="search.regions must be a list"):
        load_config(p)


def test_missing_region_and_regions(tmp_path, valid_config_data):
    """Neither region nor regions should raise ValueError."""
    del valid_config_data["search"]["region"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    with pytest.raises(ValueError, match="search.region.*search.regions"):
        load_config(p)


def test_defaults_applied(tmp_path, valid_config_data):
    del valid_config_data["database"]
    del valid_config_data["scraper"]
    del valid_config_data["search"]["size"]
    del valid_config_data["search"]["keywords"]
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(valid_config_data))
    cfg = load_config(p)
    assert cfg.database_path == "data/homedog.db"
    assert cfg.scraper.delay_min == 2
    assert cfg.search.min_ping is None
    assert cfg.search.keywords_include == []
