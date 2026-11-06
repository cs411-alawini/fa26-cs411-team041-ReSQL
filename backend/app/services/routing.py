"""Candidate routes from A to B.

OSRMRouter calls an OSRM server (the public demo server by default; set OSRM_URL to your own).
OfflineRouter needs no network: it draws a direct path plus two detours, so tests and offline
demos still exercise the full route-comparison flow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests
from flask import current_app

from ..errors import ApiError
from ..geo import haversine_km, offset_point, path_length_km

log = logging.getLogger(__name__)


@dataclass
class Route:
    geometry: list[tuple[float, float]]  # (lat, lon) pairs
    distance_m: float
    duration_s: float
    summary: str = ""


class OSRMRouter:
    name = "osrm"

    def __init__(self, base_url: str, timeout: float, user_agent: str):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def routes(self, origin: tuple[float, float], dest: tuple[float, float], max_routes: int = 3) -> list[Route]:
        coords = f"{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
        resp = requests.get(
            f"{self.base_url}/route/v1/driving/{coords}",
            params={"alternatives": "true", "overview": "full", "geometries": "geojson", "steps": "false"},
            headers=self.headers, timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ApiError(422, "No drivable route was found between those points", code="no_route")
        out = []
        for r in data["routes"][:max_routes]:
            geometry = [(lat, lon) for lon, lat in r["geometry"]["coordinates"]]
            out.append(Route(geometry, float(r["distance"]), float(r["duration"]), r.get("weight_name", "")))
        return out


class OfflineRouter:
    name = "offline"
    SPEEDS_KMH = (80.0, 72.0, 68.0)  # direct path, then the two detours

    def routes(self, origin: tuple[float, float], dest: tuple[float, float], max_routes: int = 3) -> list[Route]:
        dist = haversine_km(*origin, *dest)
        if dist < 0.05:
            raise ApiError(422, "Start and destination are the same place", code="no_route")
        mid = ((origin[0] + dest[0]) / 2, (origin[1] + dest[1]) / 2)
        # unit vector perpendicular to the trip, in km space
        north = (dest[0] - origin[0]) * 110.574
        east = haversine_km(origin[0], origin[1], origin[0], dest[1]) * (1 if dest[1] >= origin[1] else -1)
        norm = max(1e-9, (north ** 2 + east ** 2) ** 0.5)
        perp_n, perp_e = -east / norm, north / norm
        routes = [self._make([origin, dest], self.SPEEDS_KMH[0], "Direct")]
        for sign, speed, label in ((1, self.SPEEDS_KMH[1], "Alternative 1"), (-1, self.SPEEDS_KMH[2], "Alternative 2")):
            via = offset_point(*mid, sign * perp_n * dist * 0.18, sign * perp_e * dist * 0.18)
            routes.append(self._make([origin, via, dest], speed, label))
        return routes[:max_routes]

    @staticmethod
    def _make(waypoints: list[tuple[float, float]], speed_kmh: float, label: str) -> Route:
        geometry: list[tuple[float, float]] = []
        for (a_lat, a_lon), (b_lat, b_lon) in zip(waypoints, waypoints[1:]):
            n = 24
            for i in range(n):
                t = i / n
                geometry.append((round(a_lat + (b_lat - a_lat) * t, 6), round(a_lon + (b_lon - a_lon) * t, 6)))
        geometry.append(waypoints[-1])
        km = path_length_km(geometry)
        return Route(geometry, km * 1000, km / speed_kmh * 3600, label)


def get_router():
    cfg = current_app.config
    if cfg["ROUTING_PROVIDER"] == "offline":
        return OfflineRouter()
    return OSRMRouter(cfg["OSRM_URL"], cfg["HTTP_TIMEOUT_S"], cfg["HTTP_USER_AGENT"])


def find_routes(origin: tuple[float, float], dest: tuple[float, float]) -> tuple[list[Route], str, bool]:
    """Returns (routes, provider name, fell_back)."""
    router = get_router()
    try:
        return router.routes(origin, dest), router.name, False
    except ApiError:
        raise
    except Exception as exc:  # network failure, bad response, ...
        if not current_app.config["PROVIDER_FALLBACK"] or router.name == "offline":
            raise ApiError(502, "The routing service is unavailable", code="routing_unavailable") from exc
        log.warning("routing provider %s failed (%s); using offline routes", router.name, exc)
        fallback = OfflineRouter()
        return fallback.routes(origin, dest), fallback.name, True
