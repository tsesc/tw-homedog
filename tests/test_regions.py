"""Tests for region/district code resolution."""

import pytest

from tw_homedog.regions import (
    REGION_CODES,
    BUY_SECTION_CODES,
    RENT_SECTION_CODES,
    EN_TO_ZH,
    resolve_region,
    resolve_districts,
)


# Region resolution
def test_resolve_region_by_int():
    assert resolve_region(1) == 1
    assert resolve_region(3) == 3


def test_resolve_region_by_chinese_name():
    assert resolve_region("台北市") == 1
    assert resolve_region("新北市") == 3
    assert resolve_region("桃園市") == 6
    assert resolve_region("台中市") == 8
    assert resolve_region("高雄市") == 17


def test_resolve_region_unknown_name():
    with pytest.raises(ValueError, match="Unknown region"):
        resolve_region("火星市")


def test_resolve_region_invalid_type():
    with pytest.raises(TypeError, match="region must be int or str"):
        resolve_region(3.14)


# District resolution — buy mode
def test_resolve_districts_buy_chinese():
    result = resolve_districts(1, ["內湖區", "南港區"], mode="buy")
    assert result == {"內湖區": 10, "南港區": 11}


def test_resolve_districts_buy_english_backward_compat():
    result = resolve_districts(1, ["Neihu", "Nangang"], mode="buy")
    assert result == {"內湖區": 10, "南港區": 11}


def test_resolve_districts_buy_mixed():
    result = resolve_districts(1, ["內湖區", "Nangang"], mode="buy")
    assert result == {"內湖區": 10, "南港區": 11}


def test_resolve_districts_buy_unknown_skipped():
    result = resolve_districts(1, ["內湖區", "不存在區"], mode="buy")
    assert result == {"內湖區": 10}


def test_resolve_districts_buy_newtaipei():
    result = resolve_districts(3, ["板橋區", "中和區"], mode="buy")
    assert result == {"板橋區": 26, "中和區": 38}


def test_resolve_districts_buy_taoyuan():
    result = resolve_districts(6, ["桃園區", "中壢區"], mode="buy")
    assert result == {"桃園區": 55, "中壢區": 56}


# District resolution — rent mode
def test_resolve_districts_rent_chinese():
    result = resolve_districts(1, ["大安區", "中山區"], mode="rent")
    assert result == {"大安區": 7, "中山區": 1}


def test_resolve_districts_rent_english_backward_compat():
    result = resolve_districts(1, ["Daan", "Zhongshan"], mode="rent")
    assert result == {"大安區": 7, "中山區": 1}


def test_resolve_districts_rent_unsupported_region():
    result = resolve_districts(3, ["板橋區"], mode="rent")
    assert result == {}


# EN_TO_ZH mapping
def test_en_to_zh_mapping():
    assert EN_TO_ZH["Neihu"] == "內湖區"
    assert EN_TO_ZH["Nangang"] == "南港區"
    assert EN_TO_ZH["Daan"] == "大安區"
    assert len(EN_TO_ZH) == 12


# Data integrity
def test_all_22_regions_present():
    assert len(REGION_CODES) == 22


def test_taipei_buy_has_12_districts():
    assert len(BUY_SECTION_CODES[1]) == 12


def test_taipei_rent_has_12_districts():
    assert len(RENT_SECTION_CODES[1]) == 12


def test_all_regions_have_buy_sections():
    for name, code in REGION_CODES.items():
        assert code in BUY_SECTION_CODES, f"Missing buy sections for {name} (region={code})"
