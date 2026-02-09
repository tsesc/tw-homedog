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
