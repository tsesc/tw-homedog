from datetime import datetime, timezone

from tw_homedog.dedup import (
    DEFAULT_DEDUP_THRESHOLD,
    build_entity_fingerprint,
    choose_canonical_listing,
    normalize_address,
    score_duplicate,
)


def _listing(**overrides):
    base = {
        "source": "591",
        "listing_id": "10001",
        "title": "南港電梯三房車位",
        "price": 2980,
        "address": "台北市南港區向陽路258巷10號5樓",
        "district": "南港區",
        "size_ping": 36.5,
        "floor": "5F/12F",
        "room": "3房2廳2衛",
        "community_name": "陽光水岸",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def test_normalize_address_stable():
    assert normalize_address("台北市 南港區 向陽路258巷10號5樓") == normalize_address(
        "臺北市南港區向陽路258巷10號"
    )


def test_score_duplicate_same_entity_with_format_variance():
    left = _listing()
    right = _listing(
        listing_id="10002",
        title="南港陽光水岸｜電梯大兩房車",
        address="臺北市南港區向陽路258巷10號",
        size_ping=36.49,
        price=2988,
        room="3房2廳2衛",
    )
    scored = score_duplicate(left, right)
    assert scored.score >= DEFAULT_DEDUP_THRESHOLD


def test_score_duplicate_different_property_same_district_price_band():
    left = _listing()
    right = _listing(
        listing_id="20002",
        address="台北市南港區研究院路二段70巷1號",
        community_name="中研首席",
        size_ping=35.8,
        price=3010,
    )
    scored = score_duplicate(left, right)
    assert scored.score < DEFAULT_DEDUP_THRESHOLD


def test_fingerprint_equal_for_same_entity():
    left = _listing()
    right = _listing(
        listing_id="10003",
        address="臺北市南港區向陽路258巷10號",
    )
    assert build_entity_fingerprint(left) == build_entity_fingerprint(right)


def test_choose_canonical_prefers_linked_state_then_completeness():
    older_more_links = _listing(
        listing_id="old",
        published_at="2024-01-01T00:00:00+00:00",
        community_name=None,
    )
    newer_more_complete = _listing(
        listing_id="new",
        published_at="2025-01-01T00:00:00+00:00",
        community_name="陽光水岸",
    )
    relation_counts = {
        "old": {"notifications": 1, "reads": 1, "favorites": 1},
        "new": {"notifications": 0, "reads": 0, "favorites": 0},
    }
    chosen = choose_canonical_listing([older_more_links, newer_more_complete], relation_counts)
    assert chosen["listing_id"] == "old"
