"""Deterministic dedup helpers for listings."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

DEFAULT_DEDUP_THRESHOLD = 0.82
DEFAULT_PRICE_TOLERANCE = 0.05
DEFAULT_SIZE_TOLERANCE = 0.08


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().lower().replace("台", "臺")
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text)


def normalize_address(value: str | None) -> str:
    """Normalize address-like text to stable comparable text."""
    text = _normalize_text(value)
    # remove common floor suffixes that often differ between brokers
    text = re.sub(r"\d+樓", "", text)
    return text


def _bigram_set(text: str) -> set[str]:
    if len(text) <= 1:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _token_set(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]", text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _parse_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_layout(text: str | None) -> tuple[int | None, int | None, int | None]:
    raw = str(text or "")
    room = _extract_int(raw, r"(\d+)\s*房")
    hall = _extract_int(raw, r"(\d+)\s*廳")
    bath = _extract_int(raw, r"(\d+)\s*[衛厕廁]")
    return room, hall, bath


def _extract_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_floor(text: str | None) -> int | None:
    raw = str(text or "")
    m = re.search(r"(\d+)\s*(?:f|樓)", raw, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)", raw)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


@dataclass(frozen=True)
class DedupFeatures:
    district: str
    address: str
    community: str
    price: float | None
    size_ping: float | None
    rooms: int | None
    halls: int | None
    baths: int | None
    floor: int | None


@dataclass(frozen=True)
class DedupScore:
    score: float
    address_similarity: float
    price_similarity: float
    size_similarity: float
    layout_similarity: float
    district_match: bool
    reason: str


def listing_to_features(listing: dict) -> DedupFeatures:
    room, hall, bath = _parse_layout(listing.get("room"))
    return DedupFeatures(
        district=_normalize_text(listing.get("district")),
        address=normalize_address(listing.get("address")),
        community=_normalize_text(listing.get("community_name")),
        price=_parse_float(listing.get("price")),
        size_ping=_parse_float(listing.get("size_ping")),
        rooms=room,
        halls=hall,
        baths=bath,
        floor=_parse_floor(listing.get("floor")),
    )


def _relative_similarity(a: float | None, b: float | None, tolerance: float) -> float:
    if a is None or b is None:
        return 0.5
    if a == 0 and b == 0:
        return 1.0
    baseline = max(abs(a), abs(b), 1.0)
    diff = abs(a - b) / baseline
    if diff <= tolerance:
        return 1.0 - (diff / max(tolerance, 1e-6)) * 0.2
    if diff <= tolerance * 2:
        return 0.6 * (1.0 - (diff - tolerance) / max(tolerance, 1e-6))
    return 0.0


def _layout_similarity(a: DedupFeatures, b: DedupFeatures) -> float:
    def one_dim(x: int | None, y: int | None) -> float:
        if x is None and y is None:
            return 0.5
        if x is None or y is None:
            return 0.3
        if x == y:
            return 1.0
        if abs(x - y) == 1:
            return 0.4
        return 0.0

    score = (
        one_dim(a.rooms, b.rooms)
        + one_dim(a.halls, b.halls)
        + one_dim(a.baths, b.baths)
        + one_dim(a.floor, b.floor)
    ) / 4.0
    return score


def _address_similarity(a: DedupFeatures, b: DedupFeatures) -> float:
    if not a.address or not b.address:
        return 0.0
    if a.address == b.address:
        return 1.0
    seq = SequenceMatcher(None, a.address, b.address).ratio()
    gram = _jaccard(_bigram_set(a.address), _bigram_set(b.address))
    tok = _jaccard(_token_set(a.address), _token_set(b.address))
    return max(seq, (gram + tok) / 2.0)


def score_duplicate(
    left: dict,
    right: dict,
    *,
    price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
    size_tolerance: float = DEFAULT_SIZE_TOLERANCE,
) -> DedupScore:
    """Return deterministic dedup score and reason for two listings."""
    a = listing_to_features(left)
    b = listing_to_features(right)

    district_match = bool(a.district and a.district == b.district)
    address_sim = _address_similarity(a, b)
    price_sim = _relative_similarity(a.price, b.price, price_tolerance)
    size_sim = _relative_similarity(a.size_ping, b.size_ping, size_tolerance)
    layout_sim = _layout_similarity(a, b)

    community_match = bool(a.community and a.community == b.community)
    score = (
        0.55 * address_sim
        + 0.10 * (1.0 if district_match else 0.0)
        + 0.15 * price_sim
        + 0.10 * size_sim
        + 0.10 * layout_sim
    )
    if not community_match and address_sim < 0.45:
        score = min(score, 0.69)

    reasons: list[str] = []
    if district_match:
        reasons.append("district")
    if community_match:
        reasons.append("community")
    if address_sim >= 0.7:
        reasons.append("address")
    if price_sim >= 0.8:
        reasons.append("price")
    if size_sim >= 0.8:
        reasons.append("size")
    if layout_sim >= 0.7:
        reasons.append("layout")

    return DedupScore(
        score=round(score, 4),
        address_similarity=round(address_sim, 4),
        price_similarity=round(price_sim, 4),
        size_similarity=round(size_sim, 4),
        layout_similarity=round(layout_sim, 4),
        district_match=district_match,
        reason=",".join(reasons) if reasons else "low_signal",
    )


def is_duplicate(score: DedupScore | float, threshold: float = DEFAULT_DEDUP_THRESHOLD) -> bool:
    if isinstance(score, DedupScore):
        return score.score >= threshold
    return float(score) >= threshold


def _coarse_address_key(address: str) -> str:
    if not address:
        return ""
    # remove house numbers to stabilize against partial masking differences
    key = re.sub(r"\d+", "", address)
    return key[:24]


def build_entity_fingerprint(listing: dict) -> str:
    """Build stable entity fingerprint for candidate lookup."""
    f = listing_to_features(listing)
    address_key = _coarse_address_key(f.address)
    district = f.district

    if not address_key:
        fallback = _normalize_text(listing.get("title"))
        address_key = fallback[:24]

    payload = "|".join(
        part for part in (district, address_key) if part
    )
    if not payload:
        payload = str(listing.get("listing_id") or "")
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _completeness_score(listing: dict) -> int:
    keys = (
        "title",
        "address",
        "district",
        "price",
        "size_ping",
        "floor",
        "room",
        "houseage",
        "community_name",
        "main_area",
        "direction",
        "unit_price",
        "kind_name",
    )
    return sum(1 for k in keys if listing.get(k) not in (None, "", []))


def _linked_state_score(linked: dict | None) -> int:
    if not linked:
        return 0
    return (
        int(linked.get("favorites", 0)) * 4
        + int(linked.get("notifications", 0)) * 3
        + int(linked.get("reads", 0)) * 2
    )


def _timestamp_score(listing: dict) -> float:
    for key in ("published_at", "created_at"):
        value = listing.get(key)
        if not value:
            continue
        try:
            if isinstance(value, str):
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                parsed = value
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            continue
    return 0.0


def choose_canonical_listing(
    listings: list[dict],
    relation_counts: dict[str, dict[str, int]] | None = None,
) -> dict:
    """Choose canonical record by linked-state, completeness, then recency."""
    if not listings:
        raise ValueError("No listings provided")

    relation_counts = relation_counts or {}

    def key_func(item: dict) -> tuple[int, int, float, str]:
        lid = str(item.get("listing_id") or "")
        linked = _linked_state_score(relation_counts.get(lid))
        complete = _completeness_score(item)
        ts = _timestamp_score(item)
        return (linked, complete, ts, lid)

    return max(listings, key=key_func)
