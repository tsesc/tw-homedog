"""Tests for Telegram Bot handlers and helpers."""

import pytest

from tw_homedog.bot import (
    _parse_price_range,
    _build_district_keyboard,
    _build_keyword_keyboard,
    _build_list_keyboard,
    _get_unread_matched,
    LIST_PAGE_SIZE,
)
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
    keyboard = _build_district_keyboard([1], "buy", [])
    # Last row should be confirm button
    last_row = keyboard.inline_keyboard[-1]
    assert last_row[0].callback_data == "district_confirm"
    # No prefix on buttons
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            assert not btn.text.startswith("✅")


def test_build_district_keyboard_taipei_buy_with_selection():
    keyboard = _build_district_keyboard([1], "buy", ["大安區", "信義區"])
    texts = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            texts.append(btn.text)
    assert "✅ 大安區" in texts
    assert "✅ 信義區" in texts
    assert "內湖區" in texts  # unselected


def test_build_district_keyboard_all_taipei_buy_districts():
    keyboard = _build_district_keyboard([1], "buy", [])
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert set(data_values) == set(BUY_SECTION_CODES[1].keys())


def test_build_district_keyboard_taipei_rent():
    keyboard = _build_district_keyboard([1], "rent", [])
    assert keyboard is not None
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert set(data_values) == set(RENT_SECTION_CODES[1].keys())


def test_build_district_keyboard_newtaipei_buy():
    keyboard = _build_district_keyboard([3], "buy", [])
    assert keyboard is not None
    data_values = []
    for row in keyboard.inline_keyboard[:-1]:
        for btn in row:
            data_values.append(btn.callback_data.replace("district_toggle:", ""))
    assert "板橋區" in data_values
    assert "汐止區" in data_values


def test_build_district_keyboard_unsupported_region_rent():
    # Rent mode only supports Taipei (region=1)
    keyboard = _build_district_keyboard([3], "rent", [])
    assert keyboard is None


def test_build_district_keyboard_invalid_region():
    keyboard = _build_district_keyboard([999], "buy", [])
    assert keyboard is None


# --- DbConfig integration for bot ---

def test_db_config_has_config_false(db_config):
    assert db_config.has_config() is False


def test_db_config_has_config_true_after_setup(db_config):
    db_config.set_many({
        "search.regions": [1],
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


# --- _build_keyword_keyboard ---

def test_build_keyword_keyboard_empty():
    kb = _build_keyword_keyboard([], [])
    rows = kb.inline_keyboard
    # First row: "尚無關鍵字" placeholder
    assert rows[0][0].callback_data == "kw_noop"
    # Action row: ➕ 包含, ➖ 排除
    assert rows[1][0].callback_data == "kw_add_include"
    assert rows[1][1].callback_data == "kw_add_exclude"
    # Bottom row: no clear button, only 完成
    assert len(rows[2]) == 1
    assert rows[2][0].callback_data == "kw_done"


def test_build_keyword_keyboard_with_include():
    kb = _build_keyword_keyboard(["車位", "電梯"], [])
    rows = kb.inline_keyboard
    # First two rows are include keyword buttons
    assert rows[0][0].callback_data == "kw_del_i:車位"
    assert "車位" in rows[0][0].text
    assert rows[1][0].callback_data == "kw_del_i:電梯"
    # Has clear button when keywords exist
    bottom = rows[-1]
    data_values = [b.callback_data for b in bottom]
    assert "kw_clear" in data_values
    assert "kw_done" in data_values


def test_build_keyword_keyboard_with_exclude():
    kb = _build_keyword_keyboard([], ["機械車位"])
    rows = kb.inline_keyboard
    assert rows[0][0].callback_data == "kw_del_e:機械車位"
    assert "排除" in rows[0][0].text


def test_build_keyword_keyboard_mixed():
    kb = _build_keyword_keyboard(["車位"], ["機械車位", "頂加"])
    rows = kb.inline_keyboard
    # 1 include + 2 exclude + action row + bottom row = 5 rows
    assert rows[0][0].callback_data == "kw_del_i:車位"
    assert rows[1][0].callback_data == "kw_del_e:機械車位"
    assert rows[2][0].callback_data == "kw_del_e:頂加"
    assert rows[3][0].callback_data == "kw_add_include"
    assert "kw_clear" in [b.callback_data for b in rows[4]]


def test_build_keyword_keyboard_no_duplicate_add():
    """Verify duplicate check logic in handler (unit test for the handler pattern)."""
    current = ["車位", "電梯"]
    new_kws = [kw for kw in ["車位", "陽台"] if kw not in current]
    assert new_kws == ["陽台"]


# --- _build_list_keyboard ---

def _make_bot_listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "12345678",
        "title": "大安區電梯套房",
        "price": 2680,
        "district": "大安區",
        "size_ping": 28.0,
        "url": "https://sale.591.com.tw/home/house/detail/2/12345678.html",
    }
    base.update(overrides)
    return base


def test_build_list_keyboard_single_page():
    listings = [_make_bot_listing(listing_id=str(i)) for i in range(3)]
    kb = _build_list_keyboard(listings, offset=0, total=3, mode="buy")
    rows = kb.inline_keyboard
    # Each listing has 2 buttons (title/community + detail row), then nav + actions
    assert len(rows) == 8
    # First listing row
    assert rows[0][0].callback_data == "list:d:0"
    assert "大安區" in rows[0][0].text
    assert rows[1][0].callback_data == "list:d:0"
    # Nav row shows 1/1
    assert "1/1" in rows[6][0].text
    # Action row
    action_data = [b.callback_data for b in rows[7]]
    assert "list:filter" in action_data
    assert "list:ra" in action_data


def test_build_list_keyboard_multi_page_first():
    listings = [_make_bot_listing(listing_id=str(i)) for i in range(5)]
    kb = _build_list_keyboard(listings, offset=0, total=12, mode="buy")
    nav_row = kb.inline_keyboard[10]  # after 5 listings * 2 rows
    nav_data = [b.callback_data for b in nav_row]
    assert "list:p:5" in nav_data  # next page
    assert "list:noop" in nav_data  # page indicator


def test_build_list_keyboard_multi_page_middle():
    listings = [_make_bot_listing(listing_id=str(i)) for i in range(5)]
    kb = _build_list_keyboard(listings, offset=5, total=15, mode="buy")
    nav_row = kb.inline_keyboard[10]
    nav_data = [b.callback_data for b in nav_row]
    assert "list:p:0" in nav_data  # prev page
    assert "list:p:10" in nav_data  # next page


def test_build_list_keyboard_rent_mode():
    listings = [_make_bot_listing(price=35000)]
    kb = _build_list_keyboard(listings, offset=0, total=1, mode="rent")
    assert "35,000元" in kb.inline_keyboard[1][0].text


def test_build_list_keyboard_community_fallback_from_title():
    listings = [_make_bot_listing(
        listing_id="x1",
        title="屋主誠售~冠德公園家溫馨美居!!車位可另購",
        community_name=None,
    )]
    kb = _build_list_keyboard(listings, offset=0, total=1, mode="buy")
    assert "社區 冠德公園家溫馨美居" in kb.inline_keyboard[0][0].text


# --- _get_unread_matched ---

def test_get_unread_matched_returns_matching(storage, db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.mode": "buy",
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 5000,
        "telegram.bot_token": "test:TOKEN",
        "telegram.chat_id": "123",
    })
    storage.insert_listing({
        "source": "591", "listing_id": "111", "title": "test",
        "price": 2680, "district": "大安區", "size_ping": 28.0,
        "raw_hash": "abc",
    })
    result = _get_unread_matched(storage, db_config)
    assert len(result) == 1


def test_get_unread_matched_excludes_read(storage, db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.mode": "buy",
        "search.districts": ["大安區"],
        "search.price_min": 1000,
        "search.price_max": 5000,
        "telegram.bot_token": "test:TOKEN",
        "telegram.chat_id": "123",
    })
    storage.insert_listing({
        "source": "591", "listing_id": "111", "title": "test",
        "price": 2680, "district": "大安區", "size_ping": 28.0,
        "raw_hash": "abc",
    })
    storage.mark_as_read("591", "111")
    result = _get_unread_matched(storage, db_config)
    assert len(result) == 0


def test_get_unread_matched_with_district_filter(storage, db_config):
    db_config.set_many({
        "search.regions": [1],
        "search.mode": "buy",
        "search.districts": ["大安區", "信義區"],
        "search.price_min": 1000,
        "search.price_max": 5000,
        "telegram.bot_token": "test:TOKEN",
        "telegram.chat_id": "123",
    })
    storage.insert_listing({
        "source": "591", "listing_id": "111", "title": "test1",
        "price": 2680, "district": "大安區", "size_ping": 28.0,
        "raw_hash": "abc",
    })
    storage.insert_listing({
        "source": "591", "listing_id": "222", "title": "test2",
        "price": 3000, "district": "信義區", "size_ping": 30.0,
        "raw_hash": "def",
    })
    result = _get_unread_matched(storage, db_config, district_filter="大安區")
    assert len(result) == 1
    assert result[0]["listing_id"] == "111"


def test_get_unread_matched_no_config(storage, db_config):
    result = _get_unread_matched(storage, db_config)
    assert result == []
