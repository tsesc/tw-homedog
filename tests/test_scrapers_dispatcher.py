"""Tests for the scraper plugin dispatcher (scrapers/__init__.py)."""

from unittest.mock import patch, MagicMock

import pytest

from tw_homedog.db_config import Config, SearchConfig, TelegramConfig, ScraperConfig
from tw_homedog.scrapers import scrape_all, SCRAPER_REGISTRY


@pytest.fixture
def config():
    return Config(
        search=SearchConfig(
            regions=[1],
            districts=["南港區"],
            price_min=2000,
            price_max=3000,
            mode="buy",
            min_ping=20,
            max_pages=1,
            sources=["591"],
        ),
        telegram=TelegramConfig(bot_token="test", chat_id="test"),
        database_path="data/test.db",
        scraper=ScraperConfig(delay_min=0, delay_max=0, timeout=10),
    )


def test_scrape_all_single_source(config):
    """Dispatcher calls registered scraper and returns results."""
    fake_listings = [{"source": "591", "listing_id": "1"}]

    with patch("tw_homedog.scrapers.scraper_591.scrape", return_value=fake_listings):
        results = scrape_all(config)

    assert "591" in results
    assert results["591"] == fake_listings


def test_scrape_all_unknown_source_skipped(config):
    """Unknown source names are logged and skipped."""
    config.search.sources = ["unknown_source"]

    results = scrape_all(config)

    assert results == {}


def test_scrape_all_source_failure_returns_empty(config):
    """If a source's scraper raises, it returns empty list for that source."""
    with patch("tw_homedog.scrapers.scraper_591.scrape", side_effect=RuntimeError("fail")):
        results = scrape_all(config)

    assert "591" in results
    assert results["591"] == []


def test_scrape_all_empty_sources(config):
    """Empty sources list returns empty results."""
    config.search.sources = []

    results = scrape_all(config)

    assert results == {}


def test_scrape_all_default_sources_without_field(config):
    """If sources attribute is missing, defaults to ['591']."""
    # Simulate old config without sources field
    del config.search.sources
    fake_listings = [{"source": "591", "listing_id": "1"}]

    with patch("tw_homedog.scrapers.scraper_591.scrape", return_value=fake_listings):
        results = scrape_all(config)

    assert "591" in results


def test_scrape_all_progress_callback_forwarded(config):
    """Progress callback is forwarded to each scraper."""
    messages = []

    def fake_scrape(cfg, progress_cb=None):
        if progress_cb:
            progress_cb("test progress")
        return []

    with patch("tw_homedog.scrapers.scraper_591.scrape", side_effect=fake_scrape):
        scrape_all(config, progress_cb=lambda m: messages.append(m))

    assert "test progress" in messages


def test_scraper_registry_has_591():
    """591 scraper is registered."""
    assert "591" in SCRAPER_REGISTRY
