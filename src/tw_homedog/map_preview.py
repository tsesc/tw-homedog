"""Map thumbnail generation and caching for Telegram pushes."""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import time
from typing import Optional
from urllib.parse import urlencode, quote_plus

import requests

logger = logging.getLogger(__name__)


@dataclass
class MapThumbnail:
    cache_key: str
    file_path: Optional[Path]
    file_id: Optional[str]


@dataclass
class MapConfig:
    enabled: bool
    api_key: str | None
    base_url: str = "https://maps.googleapis.com/maps/api/staticmap"
    size: str = "640x400"
    zoom: int | None = None
    scale: int = 2
    language: str = "zh-TW"
    region: str = "tw"
    timeout: int = 6
    cache_ttl_seconds: int = 86400
    cache_dir: str = "data/map_cache"
    style: str | None = None
    monthly_limit: int = 10000


def geocode_address(
    address: str,
    *,
    api_key: str,
    language: str = "zh-TW",
    region: str = "tw",
    timeout: int = 6,
    cache: dict | None = None,
) -> tuple[Optional[float], Optional[float]]:
    """Geocode an address via Google Maps Geocoding API.

    Returns (lat, lng) or (None, None) on failure.
    If *cache* dict is provided, results are stored/retrieved from it
    to avoid duplicate API calls within the same batch.
    """
    if cache is not None:
        cached = cache.get(address)
        if cached:
            return cached.get("lat"), cached.get("lng")

    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "language": language, "region": region, "key": api_key}
    try:
        resp = requests.get(geocode_url, params=params, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Geocode request failed: %s %s", resp.status_code, resp.text[:200])
            return None, None
        data = resp.json()
        results = data.get("results") or []
        if not results:
            logger.info("Geocode no results for address: %s", address)
            return None, None
        location = results[0]["geometry"]["location"]
        lat, lng = float(location["lat"]), float(location["lng"])
        if cache is not None:
            cache[address] = {"lat": lat, "lng": lng}
        return lat, lng
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Geocode error for %s: %s", address, exc)
        return None, None


class MapThumbnailProvider:
    def __init__(self, config: MapConfig):
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._file_id_index_path = self.cache_dir / "file_ids.json"
        self._geocode_cache_path = self.cache_dir / "geocode_cache.json"
        self._monthly_usage_path = self.cache_dir / "monthly_usage.json"
        self._file_id_index = self._load_file_id_index()
        self._geocode_cache = self._load_geocode_cache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_thumbnail(self, *, address: str, lat: float | None = None, lng: float | None = None) -> Optional[MapThumbnail]:
        """Return cached or freshly downloaded thumbnail. None on failure or when disabled."""
        if not self.config.enabled:
            return None
        if not address and (lat is None or lng is None):
            logger.debug("Map skipped: no address and no coordinates")
            return None
        if not self.config.api_key:
            logger.warning("Map thumbnail requested but no API key configured; skipping")
            return None

        # Geocode if needed
        if (lat is None or lng is None) and address:
            lat, lng = self._geocode(address)

        cache_key = self._build_cache_key(address=address, lat=lat, lng=lng)

        # Reuse stored Telegram file_id if present
        file_id = self._file_id_index.get(cache_key)
        file_path = self._cached_file_path(cache_key)

        if self._is_cache_valid(file_path):
            logger.debug("Map cache hit for %s", cache_key[:12])
            return MapThumbnail(cache_key=cache_key, file_path=file_path, file_id=file_id)

        if not self._check_monthly_limit():
            return MapThumbnail(cache_key=cache_key, file_path=None, file_id=file_id) if file_id else None

        logger.debug("Map cache miss for %s; fetching from API", cache_key[:12])
        url = self._build_request_url(address=address, lat=lat, lng=lng)
        try:
            resp = requests.get(url, timeout=self.config.timeout)
            if resp.status_code in (429, 403):
                logger.warning("Map API quota/auth error: %s %s", resp.status_code, resp.text[:200])
                return None
            if resp.status_code != 200:
                logger.warning("Static map request failed: %s %s", resp.status_code, resp.text[:200])
                return None
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(resp.content)
            self._increment_monthly_usage()
            logger.debug("Map fetched and cached: %s", cache_key[:12])
            return MapThumbnail(cache_key=cache_key, file_path=file_path, file_id=file_id)
        except requests.RequestException as exc:
            logger.warning("Static map fetch error: %s", exc)
            return None

    def remember_file_id(self, cache_key: str, file_id: str) -> None:
        """Persist Telegram file_id for future reuse."""
        if not file_id:
            return
        self._file_id_index[cache_key] = file_id
        try:
            tmp_path = self._file_id_index_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(self._file_id_index, ensure_ascii=False, indent=2))
            tmp_path.replace(self._file_id_index_path)
        except OSError as exc:
            logger.warning("Failed to persist map file_id index: %s", exc)

    # ------------------------------------------------------------------
    # Geocoding (simple, cached)
    # ------------------------------------------------------------------
    def _geocode(self, address: str) -> tuple[Optional[float], Optional[float]]:
        cached = self._geocode_cache.get(address)
        if cached:
            return cached.get("lat"), cached.get("lng")

        if not self._check_monthly_limit():
            return None, None

        lat, lng = geocode_address(
            address,
            api_key=self.config.api_key,
            language=self.config.language,
            region=self.config.region,
            timeout=self.config.timeout,
        )
        if lat is not None and lng is not None:
            self._increment_monthly_usage()
            self._geocode_cache[address] = {"lat": lat, "lng": lng, "ts": time()}
            self._persist_geocode_cache()
        return lat, lng

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_request_url(self, *, address: str, lat: float | None, lng: float | None) -> str:
        if lat is not None and lng is not None:
            center = f"{lat},{lng}"
            marker = f"{lat},{lng}"
        else:
            center = address
            marker = address

        params = {
            "center": center,
            "markers": f"color:red|{marker}",
            "size": self.config.size,
            "scale": self.config.scale,
            "language": self.config.language,
            "region": self.config.region,
            "key": self.config.api_key,
        }
        if self.config.zoom is not None:
            params["zoom"] = self.config.zoom
        if self.config.style:
            params["style"] = self.config.style

        query = urlencode(params, quote_via=quote_plus)
        return f"{self.config.base_url}?{query}"

    def _build_cache_key(self, *, address: str, lat: float | None, lng: float | None) -> str:
        key_src = f"{address}|{lat}|{lng}|{self.config.size}|{self.config.zoom}|{self.config.style}"
        return hashlib.sha256(key_src.encode("utf-8")).hexdigest()

    def _cached_file_path(self, cache_key: str) -> Path:
        return self.cache_dir / f"{cache_key}.png"

    def _is_cache_valid(self, file_path: Path) -> bool:
        if not file_path.exists():
            return False
        age = time() - file_path.stat().st_mtime
        return age < self.config.cache_ttl_seconds

    def _load_file_id_index(self) -> dict:
        if self._file_id_index_path.exists():
            try:
                return json.loads(self._file_id_index_path.read_text())
            except (OSError, json.JSONDecodeError):
                logger.warning("Failed to read file_id index; starting empty")
                return {}
        return {}

    def _load_geocode_cache(self) -> dict:
        if self._geocode_cache_path.exists():
            try:
                return json.loads(self._geocode_cache_path.read_text())
            except (OSError, json.JSONDecodeError):
                logger.warning("Failed to read geocode cache; starting empty")
                return {}
        return {}

    # ------------------------------------------------------------------
    # Monthly API usage tracking
    # ------------------------------------------------------------------
    @staticmethod
    def _current_month() -> str:
        return date.today().strftime("%Y-%m")

    def _load_monthly_usage(self) -> dict:
        if self._monthly_usage_path.exists():
            try:
                return json.loads(self._monthly_usage_path.read_text())
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_monthly_usage(self, data: dict) -> None:
        try:
            tmp_path = self._monthly_usage_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, ensure_ascii=False))
            tmp_path.replace(self._monthly_usage_path)
        except OSError as exc:
            logger.warning("Failed to persist monthly usage: %s", exc)

    def _check_monthly_limit(self) -> bool:
        """Return True if under monthly limit, False if exhausted."""
        if self.config.monthly_limit <= 0:
            return True  # 0 or negative = unlimited
        usage = self._load_monthly_usage()
        month = self._current_month()
        if usage.get("month") != month:
            return True  # new month, counter reset
        count = usage.get("count", 0)
        if count >= self.config.monthly_limit:
            logger.warning(
                "Maps API monthly limit reached (%d/%d); skipping",
                count, self.config.monthly_limit,
            )
            return False
        return True

    def _increment_monthly_usage(self) -> None:
        usage = self._load_monthly_usage()
        month = self._current_month()
        if usage.get("month") != month:
            usage = {"month": month, "count": 0}
        usage["count"] = usage.get("count", 0) + 1
        self._save_monthly_usage(usage)

    def get_monthly_usage(self) -> tuple[int, int]:
        """Return (used_this_month, monthly_limit) for status display."""
        usage = self._load_monthly_usage()
        month = self._current_month()
        count = usage.get("count", 0) if usage.get("month") == month else 0
        return count, self.config.monthly_limit

    def _persist_geocode_cache(self) -> None:
        try:
            tmp_path = self._geocode_cache_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(self._geocode_cache, ensure_ascii=False, indent=2))
            tmp_path.replace(self._geocode_cache_path)
        except OSError as exc:
            logger.warning("Failed to persist geocode cache: %s", exc)
