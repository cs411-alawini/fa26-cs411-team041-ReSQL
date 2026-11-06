"""Health check, lookup lists, place search and current conditions."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..db import query, query_one
from ..errors import ApiError
from ..risk import get_risk_model
from ..services.conditions import profile_id
from ..services.geocoding import search_places
from ..services.weather import current_conditions
from ..validation import as_text, latitude, longitude

bp = Blueprint("meta", __name__)


@bp.get("/health")
def health():
    try:
        query_one("SELECT 1 AS ok")
        db = "ok"
    except Exception:
        db = "unavailable"
    model = get_risk_model()
    status = 200 if db == "ok" else 503
    return jsonify({
        "status": "ok" if db == "ok" else "degraded",
        "database": db,
        "risk_model": {"name": model.name, "placeholder": model.is_placeholder},
        "routing_provider": current_app.config["ROUTING_PROVIDER"],
    }), status


@bp.get("/lookups")
def lookups():
    return jsonify({
        "weather_conditions": query("SELECT weather_code, description, weather_group FROM WeatherCondition ORDER BY weather_code"),
        "light_conditions": query("SELECT light_code, description, light_group FROM LightCondition ORDER BY light_code"),
        "road_classes": query("SELECT func_sys_code, description FROM RoadClass ORDER BY func_sys_code"),
        "condition_profiles": query("SELECT condition_id, weather_group, light_group, national_est_crashes, "
                                    "national_serious_fatal_pct FROM ConditionProfile ORDER BY condition_id"),
        "states": query("SELECT state_code, state_name FROM State ORDER BY state_name"),
        "years": [r["data_year"] for r in query("SELECT DISTINCT data_year FROM Crash ORDER BY data_year")],
    })


@bp.get("/states/<int:state_code>/counties")
def counties(state_code: int):
    return jsonify({"counties": query("SELECT county_code, county_name FROM County WHERE state_code = %s "
                                      "ORDER BY county_name", (state_code,))})


@bp.get("/geocode")
def geocode():
    q = as_text(request.args.get("q", ""), "q", 200)
    results, source = search_places(q)
    return jsonify({"results": results, "source": source})


@bp.get("/conditions/current")
def conditions_now():
    lat = latitude(request.args.get("lat"), "lat")
    lon = longitude(request.args.get("lon"), "lon")
    live = current_conditions(lat, lon)
    try:
        live["condition_id"] = profile_id(live["weather_group"], live["light_group"])
    except ApiError:
        live["condition_id"] = None
    return jsonify(live)
