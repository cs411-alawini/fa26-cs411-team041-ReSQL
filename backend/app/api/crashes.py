"""Search & lookup: historical crashes, their breakdowns, and grid cells."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..db import query, query_one
from ..errors import ApiError, not_found
from ..geo import cell_bounds
from ..risk import get_risk_model
from ..services.crash_stats import TIME_OF_DAY, CrashFilter, breakdown, months_for, search
from ..validation import (LIGHT_GROUPS, WEATHER_GROUPS, arg_choice, arg_int, bbox_args)

bp = Blueprint("crashes", __name__)


def _filter_from_args() -> CrashFilter:
    hours = None
    tod = arg_choice("time_of_day", tuple(TIME_OF_DAY))
    if tod:
        hours = TIME_OF_DAY[tod]
    hour_from, hour_to = arg_int("hour_from", 0, 23), arg_int("hour_to", 0, 23)
    if hour_from is not None or hour_to is not None:
        hours = (hour_from if hour_from is not None else 0, hour_to if hour_to is not None else 23)
    f = CrashFilter(
        bbox=bbox_args(),
        state_code=arg_int("state_code", 0, 99),
        county_code=arg_int("county_code", 0, 999),
        weather_group=arg_choice("weather_group", WEATHER_GROUPS + ("unknown",)),
        light_group=arg_choice("light_group", LIGHT_GROUPS + ("unknown",)),
        func_sys_code=arg_int("func_sys_code", 0, 99),
        months=months_for(request.args.get("month"), request.args.get("season")),
        hours=hours,
        year=arg_int("year", 1975, 2100),
    )
    if f.county_code is not None and f.state_code is None:
        raise ApiError(400, "county_code needs state_code")
    if f.bbox is None and f.state_code is None:
        raise ApiError(400, "Choose an area: a map bounding box or a state")
    return f


@bp.get("/crashes")
def list_crashes():
    f = _filter_from_args()
    limit = arg_int("limit", 1, 1000, default=200)
    offset = arg_int("offset", 0, 10_000_000, default=0)
    rows, total = search(f, limit, offset)
    return jsonify({"crashes": rows, "total": total, "limit": limit, "offset": offset})


@bp.get("/crashes/stats")
def crash_stats():
    return jsonify(breakdown(_filter_from_args()))


@bp.get("/crashes/<int:year>/<int:st_case>")
def crash_detail(year: int, st_case: int):
    crash = query_one(
        "SELECT c.*, w.description AS weather, w.weather_group, l.description AS light, l.light_group, "
        "r.description AS road_class, s.cell_id, s.state_code, s.county_code, st.state_name, co.county_name "
        "FROM Crash c "
        "JOIN CrashSite s ON s.latitude = c.latitude AND s.longitude = c.longitude "
        "JOIN County co ON co.state_code = s.state_code AND co.county_code = s.county_code "
        "JOIN State st ON st.state_code = s.state_code "
        "JOIN WeatherCondition w ON w.weather_code = c.weather_code "
        "JOIN LightCondition l ON l.light_code = c.light_code "
        "JOIN RoadClass r ON r.func_sys_code = c.func_sys_code "
        "WHERE c.data_year = %s AND c.st_case = %s", (year, st_case))
    if crash is None:
        raise not_found("Crash")
    station_weather = None
    if crash["weather_station_id"]:
        station_weather = query_one(
            "SELECT ws.station_id, ws.station_name, ws.latitude, ws.longitude, d.precipitation_mm, d.snowfall_mm, "
            "d.snow_depth_mm, d.temp_max_c, d.temp_min_c, d.avg_wind_ms "
            "FROM DailyWeather d JOIN WeatherStation ws ON ws.station_id = d.station_id "
            "WHERE d.station_id = %s AND d.obs_date = %s", (crash["weather_station_id"], crash["crash_date"]))
    vehicles = query("SELECT veh_no, body_type, model_year, speeding_related, deaths_in_vehicle FROM Vehicle "
                     "WHERE data_year = %s AND st_case = %s ORDER BY veh_no", (year, st_case))
    people = query("SELECT veh_no, per_no, person_type, injury_severity, age, restraint_use FROM Person "
                   "WHERE data_year = %s AND st_case = %s ORDER BY veh_no, per_no", (year, st_case))
    return jsonify({"crash": crash, "station_weather": station_weather, "vehicles": vehicles, "people": people})


@bp.get("/cells")
def cells_in_area():
    """Grid cells in a map area with crash counts and their risk score under one condition."""
    bbox = bbox_args(required=True)
    min_lat, min_lon, max_lat, max_lon = bbox
    if (max_lat - min_lat) * (max_lon - min_lon) > 60:
        raise ApiError(400, "Zoom in further: the area is too large", code="area_too_large")
    condition_id = arg_int("condition_id", 1, 8, default=1)
    rows = query(
        "SELECT g.cell_id, g.min_latitude, g.min_longitude, s.crash_count, s.fatality_count "
        "FROM GridCell g JOIN CellRiskScore s ON s.cell_id = g.cell_id AND s.condition_id = %s "
        "WHERE g.min_latitude BETWEEN %s AND %s AND g.min_longitude BETWEEN %s AND %s",
        (condition_id, min_lat - 0.1, max_lat, min_lon - 0.1, max_lon))
    scores = get_risk_model().score_cells([r["cell_id"] for r in rows], condition_id)
    for r in rows:
        cs = scores.get(r["cell_id"])
        r["risk_score"] = cs.score if cs else 0.0
        r["risk_level"] = cs.level if cs else "low"
    return jsonify({"cells": rows, "condition_id": condition_id})


@bp.get("/cells/<cell_id>")
def cell_detail(cell_id: str):
    try:
        min_lat, min_lon, max_lat, max_lon = cell_bounds(cell_id)
    except ValueError:
        raise ApiError(400, "Not a valid cell id")
    if query_one("SELECT 1 FROM GridCell WHERE cell_id = %s", (cell_id,)) is None:
        raise not_found("Grid cell")
    profiles = query("SELECT condition_id, weather_group, light_group FROM ConditionProfile ORDER BY condition_id")
    model = get_risk_model()
    counts = {r["condition_id"]: r for r in query(
        "SELECT condition_id, crash_count, fatality_count FROM CellRiskScore WHERE cell_id = %s", (cell_id,))}
    by_condition = []
    for p in profiles:
        cs = model.score_cell(cell_id, p["condition_id"])
        c = counts.get(p["condition_id"], {})
        by_condition.append({**p, "crash_count": c.get("crash_count", 0), "fatality_count": c.get("fatality_count", 0),
                             "risk_score": cs.score, "risk_level": cs.level})
    reports = query(
        "SELECT cr.report_id, cr.reason, cr.status, cr.reported_at FROM CrashReport cr "
        "JOIN ReportCell rc ON rc.report_id = cr.report_id "
        "WHERE rc.cell_id = %s AND cr.status <> 'removed' ORDER BY cr.reported_at DESC LIMIT 20", (cell_id,))
    stats = breakdown(CrashFilter(cell_ids=[cell_id]))
    return jsonify({"cell_id": cell_id, "bounds": [min_lat, min_lon, max_lat, max_lon],
                    "by_condition": by_condition, "recent_reports": reports, "stats": stats,
                    "risk_model": {"name": model.name, "placeholder": model.is_placeholder}})
