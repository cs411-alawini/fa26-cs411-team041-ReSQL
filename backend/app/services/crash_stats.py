"""Shared SQL for crash search, breakdowns and route-corridor statistics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..db import placeholders, query, query_one
from ..errors import ApiError

SEASONS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8), "fall": (9, 10, 11)}
TIME_OF_DAY = {  # inclusive hour ranges
    "morning": (6, 11), "afternoon": (12, 16), "evening": (17, 20), "night": (21, 5),
}
SPEEDING_CODES = (2, 3, 4, 5)  # FARS SPEEDREL: yes, for any reason
WEATHER_WORDS = {"dry": "clear or dry", "wet": "rainy", "snow_ice": "snowy or icy", "low_visibility": "foggy"}

BASE_FROM = """
FROM Crash c
JOIN CrashSite s ON s.latitude = c.latitude AND s.longitude = c.longitude
JOIN WeatherCondition w ON w.weather_code = c.weather_code
JOIN LightCondition l ON l.light_code = c.light_code
JOIN RoadClass r ON r.func_sys_code = c.func_sys_code
"""


@dataclass
class CrashFilter:
    bbox: tuple[float, float, float, float] | None = None
    cell_ids: list[str] | None = None
    state_code: int | None = None
    county_code: int | None = None
    weather_group: str | None = None
    light_group: str | None = None
    func_sys_code: int | None = None
    months: tuple[int, ...] | None = None
    hours: tuple[int, int] | None = None   # inclusive, may wrap midnight
    year: int | None = None
    extra: list[str] = field(default_factory=list)

    def where(self) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if self.bbox:
            min_lat, min_lon, max_lat, max_lon = self.bbox
            clauses.append("c.latitude BETWEEN %s AND %s AND c.longitude BETWEEN %s AND %s")
            params += [min_lat, max_lat, min_lon, max_lon]
        if self.cell_ids is not None:
            if not self.cell_ids:
                clauses.append("1 = 0")
            else:
                clauses.append(f"s.cell_id IN ({placeholders(len(self.cell_ids))})")
                params += list(self.cell_ids)
        if self.state_code is not None:
            clauses.append("s.state_code = %s")
            params.append(self.state_code)
        if self.county_code is not None:
            clauses.append("s.county_code = %s")
            params.append(self.county_code)
        if self.weather_group:
            clauses.append("w.weather_group = %s")
            params.append(self.weather_group)
        if self.light_group:
            clauses.append("l.light_group = %s")
            params.append(self.light_group)
        if self.func_sys_code is not None:
            clauses.append("c.func_sys_code = %s")
            params.append(self.func_sys_code)
        if self.months:
            clauses.append(f"MONTH(c.crash_date) IN ({placeholders(len(self.months))})")
            params += list(self.months)
        if self.hours:
            lo, hi = self.hours
            if lo <= hi:
                clauses.append("c.crash_hour BETWEEN %s AND %s")
                params += [lo, hi]
            else:
                clauses.append("(c.crash_hour >= %s OR c.crash_hour <= %s) AND c.crash_hour <> 99")
                params += [lo, hi]
        if self.year is not None:
            clauses.append("c.data_year = %s")
            params.append(self.year)
        clauses += self.extra
        return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def months_for(month: Any = None, season: Any = None) -> tuple[int, ...] | None:
    if month not in (None, "", "any"):
        try:
            m = int(month)
        except (TypeError, ValueError):
            raise ApiError(400, "month must be 1-12")
        if not 1 <= m <= 12:
            raise ApiError(400, "month must be 1-12")
        return (m,)
    if season not in (None, "", "any"):
        if season not in SEASONS:
            raise ApiError(400, f"season must be one of: {', '.join(SEASONS)}")
        return SEASONS[season]
    return None


def search(f: CrashFilter, limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = f.where()
    total = query_one(f"SELECT COUNT(*) AS n {BASE_FROM} {where}", params)["n"]
    rows = query(
        "SELECT c.data_year, c.st_case, c.latitude, c.longitude, c.crash_date, c.crash_hour, c.crash_minute, "
        "c.fatalities, c.persons_involved, c.vehicles_involved, w.description AS weather, w.weather_group, "
        "l.description AS light, l.light_group, r.description AS road_class, s.cell_id, "
        "st.state_name, co.county_name "
        f"{BASE_FROM} "
        "JOIN County co ON co.state_code = s.state_code AND co.county_code = s.county_code "
        "JOIN State st ON st.state_code = s.state_code "
        f"{where} ORDER BY c.crash_date DESC, c.st_case LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return rows, int(total)


def breakdown(f: CrashFilter) -> dict:
    """Totals and breakdowns for crashes matching the filter."""
    where, params = f.where()
    totals = query_one(
        "SELECT COUNT(*) AS crashes, COALESCE(SUM(c.fatalities), 0) AS fatalities, "
        "SUM(c.weather_station_id IS NOT NULL) AS with_station "
        f"{BASE_FROM} {where}", params)

    def grouped(expr: str, label: str) -> list[dict]:
        return query(f"SELECT {expr} AS {label}, COUNT(*) AS crashes, SUM(c.fatalities) AS fatalities "
                     f"{BASE_FROM} {where} GROUP BY {label} ORDER BY crashes DESC", params)

    by_month = {r["month"]: r["crashes"] for r in grouped("MONTH(c.crash_date)", "month")}
    by_hour = {r["hour"]: r["crashes"] for r in grouped("c.crash_hour", "hour")}
    weather_join = query_one(
        "SELECT SUM(d.precipitation_mm > 0) AS wet_days, SUM(d.snowfall_mm > 0) AS snow_days, "
        "COUNT(d.station_id) AS days, ROUND(AVG(d.temp_max_c), 1) AS avg_temp_max_c "
        f"{BASE_FROM} LEFT JOIN DailyWeather d ON d.station_id = c.weather_station_id AND d.obs_date = c.crash_date "
        f"{where}", params)
    return {
        "crashes": int(totals["crashes"] or 0),
        "fatalities": int(totals["fatalities"] or 0),
        "by_weather_group": grouped("w.weather_group", "weather_group"),
        "by_light_group": grouped("l.light_group", "light_group"),
        "by_road_class": grouped("r.description", "road_class"),
        "by_month": [{"month": m, "crashes": int(by_month.get(m, 0))} for m in range(1, 13)],
        "by_hour": [{"hour": h, "crashes": int(by_hour.get(h, 0))} for h in range(24)],
        "station_weather": {
            "crashes_with_station": int(totals["with_station"] or 0),
            "on_wet_days": int(weather_join["wet_days"] or 0),
            "on_snow_days": int(weather_join["snow_days"] or 0),
            "avg_temp_max_c": weather_join["avg_temp_max_c"],
        },
    }


def corridor_factors(cell_ids: list[str], weather_group: str, light_group: str,
                     hours: tuple[int, int] | None, months: tuple[int, ...] | None) -> dict:
    """What share of the crashes along a route happened under the selected conditions."""
    if not cell_ids:
        return {"crashes": 0, "fatalities": 0, "factors": [], "by_month": [], "by_hour": []}
    f = CrashFilter(cell_ids=cell_ids, months=months)
    where, params = f.where()
    row = query_one(
        "SELECT COUNT(*) AS crashes, COALESCE(SUM(c.fatalities), 0) AS fatalities, "
        "SUM(w.weather_group <> 'unknown') AS known_weather, SUM(w.weather_group = %s) AS same_weather, "
        "SUM(l.light_group <> 'unknown') AS known_light, SUM(l.light_group = %s) AS same_light, "
        "SUM(c.crash_hour <> 99) AS known_hour, "
        "SUM(c.crash_hour <> 99 AND " + _hour_expr(hours) + ") AS same_hour "
        f"{BASE_FROM} {where}",
        [weather_group, light_group, *_hour_params(hours), *params])
    road = query_one(f"SELECT r.description AS road_class, COUNT(*) AS n {BASE_FROM} {where} "
                     "AND c.func_sys_code < 96 GROUP BY r.description ORDER BY n DESC LIMIT 1", params)
    veh = query_one(
        f"SELECT COUNT(*) AS vehicles, SUM(v.speeding_related IN ({placeholders(len(SPEEDING_CODES))})) AS speeding "
        f"{BASE_FROM} JOIN Vehicle v ON v.data_year = c.data_year AND v.st_case = c.st_case {where}",
        [*SPEEDING_CODES, *params])
    crashes = int(row["crashes"] or 0)

    def share(part, whole) -> float | None:
        part, whole = int(part or 0), int(whole or 0)
        return round(100 * part / whole, 1) if whole else None

    factors = [
        {"key": "weather", "label": f"Crashes in {WEATHER_WORDS.get(weather_group, weather_group)} weather",
         "percent": share(row["same_weather"], row["known_weather"])},
        {"key": "time", "label": "Crashes at this time of day" if hours else "Crashes in this light",
         "percent": share(row["same_hour"], row["known_hour"]) if hours else share(row["same_light"], row["known_light"])},
        {"key": "road", "label": f"On {road['road_class']} roads" if road else "Road type",
         "percent": share(road["n"], crashes) if road else None},
        {"key": "vehicle", "label": "Vehicles speeding-related",
         "percent": share(veh["speeding"], veh["vehicles"])},
    ]
    # The charts show the whole year and day so the selected season or time stands out against them.
    stats = breakdown(CrashFilter(cell_ids=cell_ids))
    return {"crashes": crashes, "fatalities": int(row["fatalities"] or 0), "factors": factors,
            "by_month": stats["by_month"], "by_hour": stats["by_hour"],
            "station_weather": stats["station_weather"]}


def _hour_expr(hours: tuple[int, int] | None) -> str:
    if not hours:
        return "0"
    lo, hi = hours
    return "c.crash_hour BETWEEN %s AND %s" if lo <= hi else "(c.crash_hour >= %s OR c.crash_hour <= %s)"


def _hour_params(hours: tuple[int, int] | None) -> list[int]:
    return list(hours) if hours else []
