"""Current weather and daylight at a point, mapped to the schema's weather and light groups.

OpenMeteoWeather uses the free Open-Meteo forecast API (no key). OfflineWeather assumes dry
weather and decides day or dark from the server clock, so the app works without network.
"""
from __future__ import annotations

import logging
from datetime import datetime

import requests
from flask import current_app

log = logging.getLogger(__name__)


def wmo_to_group(code: int) -> tuple[str, str]:
    """WMO weather interpretation code -> (weather_group, description)."""
    if code in (45, 48):
        return "low_visibility", "Fog"
    if code in (56, 57, 66, 67):
        return "snow_ice", "Freezing rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow_ice", "Snow"
    if 51 <= code <= 55 or 61 <= code <= 65 or 80 <= code <= 82 or code >= 95:
        return "wet", "Rain"
    if code in (1, 2, 3):
        return "dry", "Cloudy" if code == 3 else "Partly cloudy"
    return "dry", "Clear"


class OfflineWeather:
    name = "offline"

    def current(self, lat: float, lon: float) -> dict:
        hour = datetime.now().hour
        is_day = 6 <= hour < 18
        return {"weather_group": "dry", "light_group": "day" if is_day else "dark",
                "description": "Clear (assumed)", "temperature_c": None, "source": self.name}


class OpenMeteoWeather:
    name = "open-meteo"

    def __init__(self, base_url: str, timeout: float, user_agent: str):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def current(self, lat: float, lon: float) -> dict:
        resp = requests.get(f"{self.base_url}/v1/forecast",
                            params={"latitude": lat, "longitude": lon,
                                    "current": "weather_code,is_day,temperature_2m"},
                            headers=self.headers, timeout=self.timeout)
        resp.raise_for_status()
        cur = resp.json()["current"]
        group, description = wmo_to_group(int(cur["weather_code"]))
        return {"weather_group": group, "light_group": "day" if cur.get("is_day") else "dark",
                "description": description, "temperature_c": cur.get("temperature_2m"), "source": self.name}


def current_conditions(lat: float, lon: float) -> dict:
    cfg = current_app.config
    if cfg["WEATHER_PROVIDER"] == "offline":
        return OfflineWeather().current(lat, lon)
    provider = OpenMeteoWeather(cfg["OPEN_METEO_URL"], cfg["HTTP_TIMEOUT_S"], cfg["HTTP_USER_AGENT"])
    try:
        return provider.current(lat, lon)
    except Exception as exc:
        if not cfg["PROVIDER_FALLBACK"]:
            raise
        log.warning("weather provider failed (%s); assuming dry", exc)
        return OfflineWeather().current(lat, lon)
