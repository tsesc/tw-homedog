"""Base types and protocol for scraper plugins.

SCRAPER PLUGIN FLOW:
┌──────────┐     ┌───────────────┐     ┌──────────┐
│ dispatcher│────►│ scraper_591   │────►│ normalized│
│ (sources) │     │ scraper_sinyi │     │ listings  │
│           │     │ scraper_yc    │     │ (dicts)   │
└──────────┘     └───────────────┘     └──────────┘
Each scraper fetches + normalizes internally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from tw_homedog.db_config import Config


class NormalizedListing(TypedDict, total=False):
    """Unified listing format returned by all scrapers.

    Fields marked 'required' must always be present.
    """

    source: str  # required: "591", "sinyi", "yungching"
    listing_id: str  # required: source-specific listing ID
    title: str | None
    price: int | None  # buy mode unit: 萬 (10k NTD)
    address: str | None
    district: str | None  # e.g. "內湖區"
    size_ping: float | None
    floor: str | None
    url: str | None  # required: listing detail page URL
    published_at: str | None
    raw_hash: str  # required: content hash for change detection
    houseage: str | None
    unit_price: str | None
    kind_name: str | None
    room: str | None
    tags: list[str]
    community_name: str | None
    entity_fingerprint: str  # required: cross-source dedup key


class ListingScraper(Protocol):
    """Protocol that all scraper plugins must satisfy."""

    source: str

    def scrape(self, config: Config, progress_cb=None) -> list[dict]:
        """Fetch and normalize listings from this source.

        Returns list of dicts matching NormalizedListing shape.
        Each scraper handles its own session bootstrap, API calls,
        pagination, and normalization internally.
        """
        ...
