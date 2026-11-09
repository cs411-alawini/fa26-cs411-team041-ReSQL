"""Risk subscriptions on saved locations, and the alerts they produce."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..auth import admin_required, login_required
from ..db import execute, query, query_one, transaction
from ..errors import ApiError, not_found
from ..geo import cell_for
from ..jobs.alerts import run_alert_job
from ..risk import get_risk_model, risk_level
from ..validation import as_float, as_int, json_body, require

bp = Blueprint("subscriptions", __name__)

SELECT = """
SELECT s.subscription_id, s.location_id, l.label AS location_label, l.latitude, l.longitude,
       s.condition_id, p.weather_group, p.light_group, s.alert_threshold, s.baseline_score, s.is_active, s.created_at,
       (SELECT MAX(a.sent_at) FROM Alert a WHERE a.subscription_id = s.subscription_id) AS last_alert_at
FROM Subscription s
JOIN SavedLocation l ON l.location_id = s.location_id
JOIN ConditionProfile p ON p.condition_id = s.condition_id
"""


def _decorate(row: dict) -> dict:
    cell_id = cell_for(row["latitude"], row["longitude"])[0]
    current = get_risk_model().score_cell(cell_id, row["condition_id"]).score
    row["cell_id"] = cell_id
    row["is_active"] = bool(row["is_active"])
    row["current_score"] = current
    row["current_level"] = risk_level(current)
    return row


def _owned(subscription_id: int) -> dict:
    row = query_one(f"{SELECT} WHERE s.subscription_id = %s AND l.user_id = %s", (subscription_id, g.user["user_id"]))
    if row is None:
        raise not_found("Subscription")
    return _decorate(row)


@bp.get("/subscriptions")
@login_required
def list_subscriptions():
    rows = query(f"{SELECT} WHERE l.user_id = %s ORDER BY s.created_at DESC, s.subscription_id DESC",
                 (g.user["user_id"],))
    return jsonify({"subscriptions": [_decorate(r) for r in rows]})


@bp.post("/subscriptions")
@login_required
def create_subscription():
    data = json_body()
    require(data, "location_id", "condition_id", "alert_threshold")
    location_id = as_int(data["location_id"], "location_id", 1)
    condition_id = as_int(data["condition_id"], "condition_id", 1, 255)
    threshold = round(as_float(data["alert_threshold"], "alert_threshold", 0.01, 100), 2)
    loc = query_one("SELECT latitude, longitude FROM SavedLocation WHERE location_id = %s AND user_id = %s",
                    (location_id, g.user["user_id"]))
    if loc is None:
        raise not_found("Saved location")
    if query_one("SELECT 1 FROM ConditionProfile WHERE condition_id = %s", (condition_id,)) is None:
        raise ApiError(400, "Unknown condition profile")
    if query_one("SELECT 1 FROM Subscription WHERE location_id = %s AND condition_id = %s",
                 (location_id, condition_id)):
        raise ApiError(409, "You already watch this location under that condition", code="duplicate")
    baseline = get_risk_model().score_cell(cell_for(loc["latitude"], loc["longitude"])[0], condition_id).score
    with transaction():
        sub_id, _ = execute("INSERT INTO Subscription (location_id, condition_id, alert_threshold, baseline_score) "
                            "VALUES (%s, %s, %s, %s)", (location_id, condition_id, threshold, round(baseline, 2)))
    return jsonify({"subscription": _owned(sub_id)}), 201


@bp.patch("/subscriptions/<int:subscription_id>")
@login_required
def update_subscription(subscription_id: int):
    _owned(subscription_id)
    data = json_body()
    sets, params = [], []
    if "alert_threshold" in data:
        sets.append("alert_threshold = %s")
        params.append(round(as_float(data["alert_threshold"], "alert_threshold", 0.01, 100), 2))
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            raise ApiError(400, "is_active must be true or false")
        sets.append("is_active = %s")
        params.append(data["is_active"])
    if not sets:
        raise ApiError(400, "Nothing to update")
    with transaction():
        execute(f"UPDATE Subscription SET {', '.join(sets)} WHERE subscription_id = %s", (*params, subscription_id))
    return jsonify({"subscription": _owned(subscription_id)})


@bp.delete("/subscriptions/<int:subscription_id>")
@login_required
def delete_subscription(subscription_id: int):
    _owned(subscription_id)
    with transaction():
        execute("DELETE FROM Subscription WHERE subscription_id = %s", (subscription_id,))
    return "", 204


@bp.get("/alerts")
@login_required
def list_alerts():
    rows = query(
        "SELECT a.alert_id, a.subscription_id, a.risk_score_at_send, a.sent_at, l.label AS location_label, "
        "p.weather_group, p.light_group "
        "FROM Alert a JOIN Subscription s ON s.subscription_id = a.subscription_id "
        "JOIN SavedLocation l ON l.location_id = s.location_id "
        "JOIN ConditionProfile p ON p.condition_id = s.condition_id "
        "WHERE l.user_id = %s ORDER BY a.sent_at DESC, a.alert_id DESC LIMIT 100", (g.user["user_id"],))
    for r in rows:
        r["risk_level"] = risk_level(float(r["risk_score_at_send"]))
    return jsonify({"alerts": rows})


@bp.post("/alerts/run")
@admin_required
def run_alerts():
    return jsonify(run_alert_job())
