"""Route analysis (the safest-route recommender) and route history."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..auth import login_required, optional_auth
from ..db import execute, query, query_one, transaction
from ..errors import ApiError, not_found
from ..geo import cells_along, haversine_km
from ..risk import get_risk_model, risk_level
from ..services import conditions as conditions_svc
from ..services.crash_stats import corridor_factors
from ..services.routing import find_routes
from ..validation import as_float, json_body, one_of, point

bp = Blueprint("routes", __name__)

OPTION_TYPES = ("fastest", "safest", "balanced")
MAX_TRIP_KM = 1500


def _normalise(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    return [0.0 if hi == lo else (v - lo) / (hi - lo) for v in values]


def choose_options(routes: list[dict], safety_weight: float) -> dict[str, int]:
    """Index of the route to offer as fastest, safest and balanced."""
    idx = range(len(routes))
    fastest = min(idx, key=lambda i: (routes[i]["duration_s"], routes[i]["risk_score"]))
    safest = min(idx, key=lambda i: (routes[i]["risk_score"], routes[i]["duration_s"]))
    t = _normalise([r["duration_s"] for r in routes])
    s = _normalise([r["risk_score"] for r in routes])
    balanced = min(idx, key=lambda i: (safety_weight * s[i] + (1 - safety_weight) * t[i], routes[i]["duration_s"]))
    return {"fastest": fastest, "safest": safest, "balanced": balanced}


@bp.post("/routes/analyze")
@optional_auth
def analyze():
    data = json_body()
    origin = point(data.get("origin"), "origin")
    dest = point(data.get("destination"), "destination")
    if haversine_km(*origin, *dest) > MAX_TRIP_KM:
        raise ApiError(400, f"Trips longer than {MAX_TRIP_KM} km are not supported", code="trip_too_long")
    user = g.get("user")
    if data.get("safety_weight") is not None:
        safety_weight = as_float(data["safety_weight"], "safety_weight", 0, 1)
    else:
        safety_weight = float(user["safety_weight"]) if user else 0.5

    cond = conditions_svc.resolve(data.get("conditions"), *origin)
    raw_routes, provider, fell_back = find_routes(origin, dest)
    model = get_risk_model()

    routes = []
    for i, r in enumerate(raw_routes):
        cells = cells_along(r.geometry)
        risk = model.score_route(cells, cond["condition_id"])
        routes.append({
            "index": i, "summary": r.summary, "distance_m": round(r.distance_m), "duration_s": round(r.duration_s),
            "geometry": [[lat, lon] for lat, lon in r.geometry],
            "risk_score": risk.score, "risk_level": risk.level, "cells": risk.cells,
        })
    picks = choose_options(routes, safety_weight)
    hours = tuple(cond["hours"]) if cond["hours"] else None
    months = tuple(cond["months"]) if cond["months"] else None
    for i in set(picks.values()):
        routes[i]["stats"] = corridor_factors([c["cell_id"] for c in routes[i]["cells"]],
                                              cond["weather_group"], cond["light_group"], hours, months)
    options = [{"option_type": t, "route_index": picks[t], "distance_m": routes[picks[t]]["distance_m"],
                "duration_s": routes[picks[t]]["duration_s"], "risk_score": routes[picks[t]]["risk_score"],
                "risk_level": routes[picks[t]]["risk_level"]} for t in OPTION_TYPES]

    route_id = None
    if user and data.get("save", True):
        with transaction():
            route_id, _ = execute(
                "INSERT INTO RouteRequest (user_id, origin_lat, origin_lon, dest_lat, dest_lon) VALUES (%s, %s, %s, %s, %s)",
                (user["user_id"], *origin, *dest))
            for o in options:
                execute("INSERT INTO RouteOption (route_id, option_type, travel_time_s, risk_score) VALUES (%s, %s, %s, %s)",
                        (route_id, o["option_type"], int(o["duration_s"]), min(100.0, max(0.0, o["risk_score"]))))

    return jsonify({
        "route_id": route_id,
        "provider": provider,
        "provider_fallback": fell_back,
        "risk_model": {"name": model.name, "placeholder": model.is_placeholder},
        "safety_weight": safety_weight,
        "conditions": cond,
        "routes": routes,
        "options": options,
        "recommended": "balanced",
    })


def _history_rows(where: str, params: tuple) -> list[dict]:
    reqs = query("SELECT route_id, origin_lat, origin_lon, dest_lat, dest_lon, chosen_option, requested_at "
                 f"FROM RouteRequest {where} ORDER BY requested_at DESC, route_id DESC LIMIT 50", params)
    if not reqs:
        return []
    ids = [r["route_id"] for r in reqs]
    opts = query("SELECT route_id, option_type, travel_time_s, risk_score FROM RouteOption "
                 f"WHERE route_id IN ({', '.join(['%s'] * len(ids))}) ORDER BY FIELD(option_type, 'fastest', 'balanced', 'safest')",
                 tuple(ids))
    by_route: dict[int, list] = {}
    for o in opts:
        o["risk_level"] = risk_level(float(o["risk_score"]))
        by_route.setdefault(o["route_id"], []).append(o)
    for r in reqs:
        r["options"] = by_route.get(r["route_id"], [])
    return reqs


@bp.get("/routes")
@login_required
def history():
    return jsonify({"routes": _history_rows("WHERE user_id = %s", (g.user["user_id"],))})


@bp.get("/routes/<int:route_id>")
@login_required
def get_route(route_id: int):
    rows = _history_rows("WHERE user_id = %s AND route_id = %s", (g.user["user_id"], route_id))
    if not rows:
        raise not_found("Route")
    return jsonify({"route": rows[0]})


@bp.patch("/routes/<int:route_id>")
@login_required
def choose(route_id: int):
    if query_one("SELECT 1 FROM RouteRequest WHERE route_id = %s AND user_id = %s", (route_id, g.user["user_id"])) is None:
        raise not_found("Route")
    choice = json_body().get("chosen_option")
    if choice is not None:
        one_of(choice, "chosen_option", OPTION_TYPES)
        # Same rule as trg_routerequest_choice_bu, checked here too because a database restored
        # from a Cloud SQL export has no triggers (the export leaves them out).
        if query_one("SELECT 1 FROM RouteOption WHERE route_id = %s AND option_type = %s", (route_id, choice)) is None:
            raise ApiError(409, "chosen_option was not offered for this route", "conflict")
    with transaction():
        execute("UPDATE RouteRequest SET chosen_option = %s WHERE route_id = %s", (choice, route_id))
    return get_route(route_id)


@bp.delete("/routes/<int:route_id>")
@login_required
def delete_route(route_id: int):
    with transaction():
        _, n = execute("DELETE FROM RouteRequest WHERE route_id = %s AND user_id = %s", (route_id, g.user["user_id"]))
    if n == 0:
        raise not_found("Route")
    return "", 204
