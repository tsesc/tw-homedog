"""Tests for preset configuration templates."""

import pytest

from tw_homedog.templates import TEMPLATES, get_template, apply_template


def test_all_templates_have_required_fields():
    required = {"id", "name", "description", "mode", "regions", "districts", "price_min", "price_max"}
    for t in TEMPLATES:
        missing = required - set(t.keys())
        assert not missing, f"Template '{t.get('id', '?')}' missing fields: {missing}"


def test_all_template_ids_unique():
    ids = [t["id"] for t in TEMPLATES]
    assert len(ids) == len(set(ids))


def test_template_count():
    assert len(TEMPLATES) == 6


def test_get_template_found():
    t = get_template("buy_family_taipei")
    assert t is not None
    assert t["name"] == "台北家庭自住"
    assert t["mode"] == "buy"
    assert "內湖區" in t["districts"]


def test_get_template_not_found():
    assert get_template("nonexistent") is None


def test_apply_template_returns_flat_dict():
    result = apply_template("buy_family_taipei")
    assert result["search.mode"] == "buy"
    assert result["search.regions"] == [1]  # 台北市
    assert result["search.districts"] == ["內湖區", "南港區", "文山區", "士林區", "北投區"]
    assert result["search.price_min"] == 2000
    assert result["search.price_max"] == 4000
    assert result["search.min_ping"] == 30
    assert result["search.keywords_exclude"] == ["頂加", "工業宅"]


def test_apply_template_rent():
    result = apply_template("rent_single_taipei")
    assert result["search.mode"] == "rent"
    assert result["search.price_min"] == 15000
    assert result["search.price_max"] == 30000


def test_apply_template_newtaipei():
    result = apply_template("buy_invest_newtaipei")
    assert result["search.regions"] == [3]  # 新北市
    assert "板橋區" in result["search.districts"]


def test_apply_template_not_found():
    with pytest.raises(KeyError, match="Template not found"):
        apply_template("nonexistent")


def test_all_districts_are_chinese():
    for t in TEMPLATES:
        for d in t["districts"]:
            assert any(c >= "\u4e00" for c in d), f"District '{d}' in template '{t['id']}' is not Chinese"
