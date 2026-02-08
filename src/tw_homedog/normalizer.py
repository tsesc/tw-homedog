"""Normalize raw 591 data to unified listing format."""

import hashlib
import re


def extract_price(raw_price: str | int | float | None) -> int | None:
    """Extract integer price from various formats.

    Handles: 35000, "35,000", "35,000 元/月", "NT$35000", etc.
    """
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        return int(raw_price)
    cleaned = re.sub(r"[^\d]", "", str(raw_price))
    if not cleaned:
        return None
    return int(cleaned)


def generate_content_hash(title: str | None, price: int | None, address: str | None) -> str:
    """Generate SHA256 hash from title + price + address."""
    parts = [str(title or ""), str(price or ""), str(address or "")]
    content = "|".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_591_listing(raw: dict) -> dict:
    """Convert raw 591 scraped data to unified listing format."""
    price = extract_price(raw.get("price") or raw.get("base_rent_nt"))
    title = raw.get("title") or raw.get("title_zh")
    address = raw.get("address") or raw.get("address_zh")

    size_ping = raw.get("size_ping")
    if size_ping is not None:
        try:
            size_ping = float(size_ping)
        except (ValueError, TypeError):
            size_ping = None

    return {
        "source": "591",
        "listing_id": str(raw.get("id") or raw.get("listing_id", "")),
        "title": title,
        "price": price,
        "address": address,
        "district": raw.get("district"),
        "size_ping": size_ping,
        "floor": raw.get("floor"),
        "url": raw.get("url"),
        "published_at": raw.get("published_at"),
        "raw_hash": generate_content_hash(title, price, address),
        "houseage": raw.get("houseage"),
        "unit_price": raw.get("unit_price"),
        "kind_name": raw.get("kind_name"),
        "room": raw.get("room"),
        "tags": raw.get("tags") or [],
        "community_name": raw.get("community_name"),
    }
