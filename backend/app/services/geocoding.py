"""Place search for the start and destination boxes.

NominatimGeocoder uses OpenStreetMap's Nominatim (keep traffic light; its usage policy allows
about one request per second). OfflineGeocoder understands "lat, lon" input and a short list
of cities, so the app and its tests work without network access.
"""
from __future__ import annotations

import logging
import re

import requests
from flask import current_app

log = logging.getLogger(__name__)

COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

CITIES = [
    ("Champaign, IL", 40.1164, -88.2434), ("Urbana, IL", 40.1106, -88.2073),
    ("Chicago, IL", 41.8781, -87.6298), ("Springfield, IL", 39.7817, -89.6501),
    ("Peoria, IL", 40.6936, -89.5890), ("Bloomington, IL", 40.4842, -88.9937),
    ("Indianapolis, IN", 39.7684, -86.1581), ("St. Louis, MO", 38.6270, -90.1994),
    ("Milwaukee, WI", 43.0389, -87.9065), ("Detroit, MI", 42.3314, -83.0458),
    ("New York, NY", 40.7128, -74.0060), ("Philadelphia, PA", 39.9526, -75.1652),
    ("Boston, MA", 42.3601, -71.0589), ("Atlanta, GA", 33.7490, -84.3880),
    ("Miami, FL", 25.7617, -80.1918), ("Houston, TX", 29.7604, -95.3698),
    ("Dallas, TX", 32.7767, -96.7970), ("Austin, TX", 30.2672, -97.7431),
    ("Denver, CO", 39.7392, -104.9903), ("Phoenix, AZ", 33.4484, -112.0740),
    ("Los Angeles, CA", 34.0522, -118.2437), ("San Francisco, CA", 37.7749, -122.4194),
    ("Seattle, WA", 47.6062, -122.3321),
]


def _coordinates(q: str) -> list[dict]:
    m = COORD_RE.match(q)
    if not m:
        return []
    lat, lon = float(m.group(1)), float(m.group(2))
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return [{"label": f"{lat:.5f}, {lon:.5f}", "lat": lat, "lon": lon, "source": "coordinates"}]
    return []


class OfflineGeocoder:
    name = "offline"

    def search(self, q: str, limit: int = 5) -> list[dict]:
        hits = _coordinates(q)
        if hits:
            return hits
        needle = q.strip().lower()
        return [{"label": name, "lat": lat, "lon": lon, "source": "offline"}
                for name, lat, lon in CITIES if needle and needle in name.lower()][:limit]


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, base_url: str, timeout: float, user_agent: str):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def search(self, q: str, limit: int = 5) -> list[dict]:
        hits = _coordinates(q)
        if hits:
            return hits
        resp = requests.get(f"{self.base_url}/search",
                            params={"q": q, "format": "jsonv2", "limit": limit, "countrycodes": "us"},
                            headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        return [{"label": r.get("display_name", ""), "lat": float(r["lat"]), "lon": float(r["lon"]),
                 "source": "nominatim"} for r in resp.json()]


def search_places(q: str, limit: int = 5) -> tuple[list[dict], str]:
    cfg = current_app.config
    if cfg["GEOCODER"] == "offline":
        geocoder = OfflineGeocoder()
        return geocoder.search(q, limit), geocoder.name
    geocoder = NominatimGeocoder(cfg["NOMINATIM_URL"], cfg["HTTP_TIMEOUT_S"], cfg["HTTP_USER_AGENT"])
    try:
        return geocoder.search(q, limit), geocoder.name
    except Exception as exc:
        if not cfg["PROVIDER_FALLBACK"]:
            raise
        log.warning("geocoder failed (%s); using offline list", exc)
        return OfflineGeocoder().search(q, limit), "offline"
