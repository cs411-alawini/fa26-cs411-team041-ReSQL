"""Geometry helpers: the 0.1 degree grid from the Stage 2 design, distances, route sampling."""
from __future__ import annotations

import math
from decimal import ROUND_FLOOR, Decimal

EARTH_RADIUS_KM = 6371.0088
CELL_SIZE = Decimal("0.1")


def cell_for(lat: float | str | Decimal, lon: float | str | Decimal) -> tuple[str, Decimal, Decimal]:
    """cell_id = CONCAT(FLOOR(lat * 10), '_', FLOOR(lon * 10)), computed with exact decimals."""
    lat_d = (Decimal(str(lat)) * 10).to_integral_value(rounding=ROUND_FLOOR)
    lon_d = (Decimal(str(lon)) * 10).to_integral_value(rounding=ROUND_FLOOR)
    return f"{int(lat_d)}_{int(lon_d)}", lat_d / 10, lon_d / 10


def cell_bounds(cell_id: str) -> tuple[float, float, float, float]:
    """(min_lat, min_lon, max_lat, max_lon) of a cell id such as '401_-883'."""
    try:
        a, b = cell_id.split("_")
        lat10, lon10 = int(a), int(b)
    except (ValueError, AttributeError):
        raise ValueError(f"not a cell id: {cell_id!r}")
    return lat10 / 10, lon10 / 10, (lat10 + 1) / 10, (lon10 + 1) / 10


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def path_length_km(points: list[tuple[float, float]]) -> float:
    return sum(haversine_km(*points[i], *points[i + 1]) for i in range(len(points) - 1))


def cells_along(points: list[tuple[float, float]], step_km: float = 0.5) -> list[tuple[str, float]]:
    """Cells a polyline passes through, in travel order, with the km driven inside each.

    The path is resampled every `step_km`, which is far below the ~6-11 km cell size,
    so a cell is only missed when the route clips one of its corners.
    """
    if not points:
        return []
    order: list[str] = []
    km_in: dict[str, float] = {}

    def add(cell: str, km: float) -> None:
        if cell not in km_in:
            km_in[cell] = 0.0
            order.append(cell)
        km_in[cell] += km

    add(cell_for(*points[0])[0], 0.0)
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        seg = haversine_km(lat1, lon1, lat2, lon2)
        n = max(1, math.ceil(seg / step_km))
        for i in range(n):
            t = (i + 0.5) / n
            add(cell_for(lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t)[0], seg / n)
    return [(c, round(km_in[c], 3)) for c in order]


def offset_point(lat: float, lon: float, north_km: float, east_km: float) -> tuple[float, float]:
    dlat = north_km / 110.574
    dlon = east_km / (111.320 * max(0.01, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon
