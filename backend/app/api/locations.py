"""Saved locations (CRUD)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..auth import login_required
from ..db import execute, query, query_one, transaction
from ..errors import ApiError, not_found
from ..geo import cell_for
from ..validation import as_text, json_body, latitude, longitude, require

bp = Blueprint("locations", __name__)

SELECT = ("SELECT l.location_id, l.label, l.latitude, l.longitude, l.created_at, "
          "(SELECT COUNT(*) FROM Subscription s WHERE s.location_id = l.location_id) AS subscriptions "
          "FROM SavedLocation l")


def owned_location(location_id: int) -> dict:
    row = query_one(f"{SELECT} WHERE l.location_id = %s AND l.user_id = %s", (location_id, g.user["user_id"]))
    if row is None:
        raise not_found("Saved location")
    row["cell_id"] = cell_for(row["latitude"], row["longitude"])[0]
    return row


@bp.get("/locations")
@login_required
def list_locations():
    rows = query(f"{SELECT} WHERE l.user_id = %s ORDER BY l.created_at DESC, l.location_id DESC", (g.user["user_id"],))
    for r in rows:
        r["cell_id"] = cell_for(r["latitude"], r["longitude"])[0]
    return jsonify({"locations": rows})


@bp.post("/locations")
@login_required
def create_location():
    data = json_body()
    require(data, "label", "lat", "lon")
    label = as_text(data["label"], "label", 60)
    lat, lon = latitude(data["lat"], "lat"), longitude(data["lon"], "lon")
    with transaction():
        location_id, _ = execute(
            "INSERT INTO SavedLocation (user_id, label, latitude, longitude) VALUES (%s, %s, %s, %s)",
            (g.user["user_id"], label, lat, lon))
    return jsonify({"location": owned_location(location_id)}), 201


@bp.get("/locations/<int:location_id>")
@login_required
def get_location(location_id: int):
    return jsonify({"location": owned_location(location_id)})


@bp.put("/locations/<int:location_id>")
@login_required
def update_location(location_id: int):
    owned_location(location_id)
    data = json_body()
    sets, params = [], []
    if "label" in data:
        sets.append("label = %s")
        params.append(as_text(data["label"], "label", 60))
    if "lat" in data or "lon" in data:
        require(data, "lat", "lon")
        sets += ["latitude = %s", "longitude = %s"]
        params += [latitude(data["lat"], "lat"), longitude(data["lon"], "lon")]
    if not sets:
        raise ApiError(400, "Nothing to update")
    with transaction():
        execute(f"UPDATE SavedLocation SET {', '.join(sets)} WHERE location_id = %s AND user_id = %s",
                (*params, location_id, g.user["user_id"]))
    return jsonify({"location": owned_location(location_id)})


@bp.delete("/locations/<int:location_id>")
@login_required
def delete_location(location_id: int):
    owned_location(location_id)
    with transaction():  # subscriptions and their alerts cascade
        execute("DELETE FROM SavedLocation WHERE location_id = %s AND user_id = %s", (location_id, g.user["user_id"]))
    return "", 204
