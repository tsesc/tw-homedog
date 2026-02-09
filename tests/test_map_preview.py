import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tw_homedog.map_preview import MapConfig, MapThumbnailProvider, geocode_address


class _Resp:
    def __init__(self, status_code=200, json_data=None, content=b"img"):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = json.dumps(self._json)

    def json(self):
        return self._json


def test_build_request_url_uses_coords():
    cfg = MapConfig(enabled=True, api_key="k", zoom=16)
    provider = MapThumbnailProvider(cfg)

    url = provider._build_request_url(address="Taipei", lat=25.0, lng=121.5)

    assert "center=25.0%2C121.5" in url
    assert "markers=color%3Ared%7C25.0%2C121.5" in url
    assert "zoom=16" in url


def test_get_thumbnail_geocode_and_cache(monkeypatch, tmp_path):
    cfg = MapConfig(
        enabled=True,
        api_key="k",
        cache_dir=str(tmp_path),
        cache_ttl_seconds=86400,
    )
    provider = MapThumbnailProvider(cfg)

    calls = {"geocode": 0, "static": 0}

    def fake_get(url, *args, **kwargs):
        if "geocode" in url:
            calls["geocode"] += 1
            return _Resp(json_data={"results": [{"geometry": {"location": {"lat": 25.0, "lng": 121.5}}}]})
        calls["static"] += 1
        return _Resp()

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    thumb1 = provider.get_thumbnail(address="台北市大安區", lat=None, lng=None)
    assert thumb1 is not None
    assert thumb1.file_path.exists()
    assert calls["geocode"] == 1
    assert calls["static"] == 1

    # second call should hit cache and avoid http
    thumb2 = provider.get_thumbnail(address="台北市大安區", lat=None, lng=None)
    assert thumb2 is not None
    assert calls["geocode"] == 1  # cached
    assert calls["static"] == 1   # cached


def test_remember_file_id_persists(tmp_path):
    cfg = MapConfig(enabled=True, api_key="k", cache_dir=str(tmp_path))
    provider = MapThumbnailProvider(cfg)

    provider.remember_file_id("abc", "file123")

    saved = json.loads((Path(tmp_path) / "file_ids.json").read_text())
    assert saved["abc"] == "file123"


# --- geocode_address standalone function ---

def test_geocode_address_success(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return _Resp(json_data={
            "results": [{"geometry": {"location": {"lat": 25.033, "lng": 121.543}}}],
        })

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    lat, lng = geocode_address("台北市大安區", api_key="test-key")
    assert lat == pytest.approx(25.033)
    assert lng == pytest.approx(121.543)


def test_geocode_address_no_results(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return _Resp(json_data={"results": []})

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    lat, lng = geocode_address("nowhere", api_key="test-key")
    assert lat is None
    assert lng is None


def test_geocode_address_with_cache(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, *args, **kwargs):
        calls["count"] += 1
        return _Resp(json_data={
            "results": [{"geometry": {"location": {"lat": 25.0, "lng": 121.5}}}],
        })

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    cache: dict = {}
    lat1, lng1 = geocode_address("台北市", api_key="k", cache=cache)
    lat2, lng2 = geocode_address("台北市", api_key="k", cache=cache)

    assert lat1 == lat2 == pytest.approx(25.0)
    assert lng1 == lng2 == pytest.approx(121.5)
    assert calls["count"] == 1  # second call used cache


def test_geocode_address_api_error(monkeypatch):
    def fake_get(url, *args, **kwargs):
        return _Resp(status_code=500)

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    lat, lng = geocode_address("台北市", api_key="k")
    assert lat is None
    assert lng is None


# --- Monthly usage tracking ---


def test_monthly_usage_increments_and_resets(tmp_path):
    cfg = MapConfig(enabled=True, api_key="k", cache_dir=str(tmp_path), monthly_limit=100)
    provider = MapThumbnailProvider(cfg)

    assert provider.get_monthly_usage() == (0, 100)

    provider._increment_monthly_usage()
    provider._increment_monthly_usage()
    assert provider.get_monthly_usage() == (2, 100)

    # Simulate month rollover by writing a stale month
    usage_path = tmp_path / "monthly_usage.json"
    usage_path.write_text(json.dumps({"month": "1999-01", "count": 50}))
    assert provider.get_monthly_usage() == (0, 100)  # old month → 0


def test_monthly_limit_blocks_api_calls(monkeypatch, tmp_path):
    cfg = MapConfig(
        enabled=True, api_key="k", cache_dir=str(tmp_path),
        monthly_limit=2, cache_ttl_seconds=86400,
    )
    provider = MapThumbnailProvider(cfg)

    api_calls = {"count": 0}

    def fake_get(url, *args, **kwargs):
        api_calls["count"] += 1
        if "geocode" in url:
            return _Resp(json_data={"results": [{"geometry": {"location": {"lat": 25.0, "lng": 121.5}}}]})
        return _Resp()

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    # First call: geocode (1) + static map (2) = 2 API calls, hits limit
    thumb1 = provider.get_thumbnail(address="addr1", lat=None, lng=None)
    assert thumb1 is not None
    assert api_calls["count"] == 2  # geocode + static

    # Second call with new address: should be blocked by monthly limit
    thumb2 = provider.get_thumbnail(address="addr2", lat=None, lng=None)
    assert thumb2 is None  # blocked
    assert api_calls["count"] == 2  # no new API calls


def test_monthly_limit_zero_means_unlimited(tmp_path):
    cfg = MapConfig(enabled=True, api_key="k", cache_dir=str(tmp_path), monthly_limit=0)
    provider = MapThumbnailProvider(cfg)

    assert provider._check_monthly_limit() is True

    # Even with high count, 0 = unlimited
    (tmp_path / "monthly_usage.json").write_text(
        json.dumps({"month": provider._current_month(), "count": 999999})
    )
    assert provider._check_monthly_limit() is True


def test_monthly_usage_persists_across_instances(tmp_path):
    cfg = MapConfig(enabled=True, api_key="k", cache_dir=str(tmp_path), monthly_limit=100)

    provider1 = MapThumbnailProvider(cfg)
    provider1._increment_monthly_usage()
    provider1._increment_monthly_usage()
    provider1._increment_monthly_usage()

    # New instance should read persisted usage
    provider2 = MapThumbnailProvider(cfg)
    assert provider2.get_monthly_usage() == (3, 100)


def test_cache_hit_does_not_increment_usage(monkeypatch, tmp_path):
    cfg = MapConfig(
        enabled=True, api_key="k", cache_dir=str(tmp_path),
        monthly_limit=100, cache_ttl_seconds=86400,
    )
    provider = MapThumbnailProvider(cfg)

    def fake_get(url, *args, **kwargs):
        if "geocode" in url:
            return _Resp(json_data={"results": [{"geometry": {"location": {"lat": 25.0, "lng": 121.5}}}]})
        return _Resp()

    monkeypatch.setattr("tw_homedog.map_preview.requests.get", fake_get)

    # First call: hits API
    provider.get_thumbnail(address="台北市大安區", lat=None, lng=None)
    used_after_first, _ = provider.get_monthly_usage()

    # Second call: should hit cache, no increment
    provider.get_thumbnail(address="台北市大安區", lat=None, lng=None)
    used_after_second, _ = provider.get_monthly_usage()

    assert used_after_second == used_after_first
