"""Tests for Telegram Bot handlers and helpers."""

import pytest

from tw_homedog.bot import _parse_price_range, _build_district_keyboard
from tw_homedog.db_config import DbConfig
from tw_homedog.regions import BUY_SECTION_CODES, RENT_SECTION_CODES
from tw_homedog.storage import Storage


@pytest.fixture
def storage(tmp_path):
    s = Storage(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def db_config(storage):
    return DbConfig(storage.conn)


# --- _parse_price_range ---

def test_parse_price_range_valid():
    assert _parse_price_range("1000-3000") == (1000, 3000)


def test_parse_price_range_with_commas():
    assert _parse_price_range("1,000-3,000") == (1000, 3000)


def test_parse_price_range_with_spaces():
    assert _parse_price_range(" 500 - 2000 ") == (500, 2000)


def test_parse_price_range_invalid_format():
    assert _parse_price_range("abc") is None
    assert _parse_price_range("1000") is None
    assert _parse_price_range("1000-2000-3000") is None


def test_parse_price_range_min_ge_max():
    assert _parse_price_range("3000-1000") is None
    assert _parse_price_range("1000-1000") is None


def test_parse_price_range_negative():
    assert _parse_price_range("-100-1000") is None


# --- _build_district_keyboard ---

def test_build_district_keyboard_taipei_buy_none_selected():
    keyboard = _build_district_keyboard(1, "buy", [])
    # Last row should be confirm button
    last_row = keyboard.inline_keyboard[-1]
    assert last_row[0].callback_data == "district_confirm"
    # No prefix on buttons
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            assert not btn.text.startswith("✅")


def test_build_district_keyboard_taipei_buy_with_selection():
    keyboard = _build_district_keyboard(1, "buy", ["大安區", "信義區"])
    texts = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            texts.append(btn.text)
    assert "✅ 大安區" in texts
    assert "✅ 信義區" in texts
    assert "內湖區" in texts  # unselected


def test_build_district_keyboard_all_taipei_buy_districts():
    keyboard = _build_district_keyboard(1, "buy", [])
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert set(data_values) == set(BUY_SECTION_CODES[1].keys())


def test_build_district_keyboard_taipei_rent():
    keyboard = _build_district_keyboard(1, "rent", [])
    assert keyboard is not None
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert set(data_values) == set(RENT_SECTION_CODES[1].keys())


def test_build_district_keyboard_newtaipei_buy():
    keyboard = _build_district_keyboard(3, "buy", [])
    assert keyboard is not None
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert "板橋區" in data_values
    assert "汐止區" in data_values


def test_build_district_keyboard_unsupported_region_rent():
    # Rent mode only supports Taipei (region=1)
    keyboard = _build_district_keyboard(3, "rent", [])
    assert keyboard is None


def test_build_district_keyboard_invalid_region():
    keyboard = _build_district_keyboard(999, "buy", [])
    assert keyboard is None


# --- DbConfig integration for bot ---

def test_db_config_has_config_false(db_config):
    assert db_config.has_config() is False


def test_db_config_has_config_true_after_setup(db_config):
    db_config.set_many({
        "search.region": 1,
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 3000,
        "telegram.bot_token": "123:ABC",
        "telegram.chat_id": "456",
    })
    assert db_config.has_config() is True


def test_scheduler_config_defaults(db_config):
    assert db_config.get("scheduler.interval_minutes", 30) == 30
    assert db_config.get("scheduler.paused", False) is False


def test_scheduler_config_update(db_config):
    db_config.set("scheduler.interval_minutes", 60)
    assert db_config.get("scheduler.interval_minutes") == 60

    db_config.set("scheduler.paused", True)
    assert db_config.get("scheduler.paused") is True
