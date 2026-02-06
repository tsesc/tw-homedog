"""Tests for data normalizer."""

from tw_homedog.normalizer import extract_price, generate_content_hash, normalize_591_listing


def test_extract_price_int():
    assert extract_price(35000) == 35000


def test_extract_price_string_with_comma():
    assert extract_price("35,000") == 35000


def test_extract_price_with_unit():
    assert extract_price("35,000 元/月") == 35000


def test_extract_price_nt_dollar():
    assert extract_price("NT$35000") == 35000


def test_extract_price_none():
    assert extract_price(None) is None


def test_extract_price_empty_string():
    assert extract_price("") is None


def test_generate_content_hash():
    h1 = generate_content_hash("title", 35000, "address")
    h2 = generate_content_hash("title", 35000, "address")
    assert h1 == h2
    assert len(h1) == 64  # SHA256 hex


def test_generate_content_hash_different():
    h1 = generate_content_hash("title1", 35000, "address")
    h2 = generate_content_hash("title2", 35000, "address")
    assert h1 != h2


def test_normalize_full_listing():
    raw = {
        "id": "12345678",
        "title_zh": "大安區電梯套房",
        "base_rent_nt": 35000,
        "address_zh": "台北市大安區忠孝東路",
        "district": "Daan",
        "size_ping": 28,
        "floor": "5/12",
        "url": "https://rent.591.com.tw/12345678",
        "published_at": "2025-01-01",
    }
    result = normalize_591_listing(raw)
    assert result["source"] == "591"
    assert result["listing_id"] == "12345678"
    assert result["title"] == "大安區電梯套房"
    assert result["price"] == 35000
    assert result["size_ping"] == 28.0
    assert result["raw_hash"] is not None


def test_normalize_missing_optional_fields():
    raw = {"id": "999", "title": "Test", "price": 20000, "address": "Addr"}
    result = normalize_591_listing(raw)
    assert result["listing_id"] == "999"
    assert result["floor"] is None
    assert result["size_ping"] is None
    assert result["district"] is None


def test_normalize_same_content_same_hash():
    raw1 = {"id": "111", "title": "Same", "price": 30000, "address": "Same Addr"}
    raw2 = {"id": "222", "title": "Same", "price": 30000, "address": "Same Addr"}
    r1 = normalize_591_listing(raw1)
    r2 = normalize_591_listing(raw2)
    assert r1["raw_hash"] == r2["raw_hash"]
