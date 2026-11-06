"""Community crash and hazard reports: CRUD, voting and admin moderation."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..auth import admin_required, login_required, optional_auth
from ..db import execute, query, query_one, transaction
from ..errors import ApiError, not_found
from ..geo import cell_for
from ..validation import arg_int, as_text, bbox_args, json_body, latitude, longitude, one_of, require

bp = Blueprint("reports", __name__)

SELECT = """
SELECT cr.report_id, cr.user_id, u.display_name AS author, cr.latitude, cr.longitude, cr.reason, cr.status,
       cr.reported_at, cr.reviewed_by, cr.reviewed_at, rc.cell_id,
       (cr.status <> 'removed' AND cr.reported_at >= NOW() - INTERVAL 30 DAY) AS recent_ok,
       COALESCE(SUM(v.vote = 1), 0) AS confirms,
       COALESCE(SUM(v.vote = -1), 0) AS flags,
       MAX(CASE WHEN v.user_id = %s THEN v.vote END) AS my_vote
FROM CrashReport cr
JOIN AppUser u ON u.user_id = cr.user_id
LEFT JOIN ReportCell rc ON rc.report_id = cr.report_id
LEFT JOIN ReportVote v ON v.report_id = cr.report_id
"""
GROUP = " GROUP BY cr.report_id, rc.cell_id"


def _decorate(row: dict) -> dict:
    row["confirms"], row["flags"] = int(row["confirms"]), int(row["flags"])
    row["my_vote"] = None if row["my_vote"] is None else int(row["my_vote"])
    # Section 2.6: a report counts toward risk if not removed, under 30 days old, and confirms >= flags.
    row["counts_toward_risk"] = bool(row.pop("recent_ok")) and row["confirms"] >= row["flags"]
    return row


def _viewer_id() -> int:
    return g.user["user_id"] if g.get("user") else -1


def _load(report_id: int) -> dict:
    row = query_one(f"{SELECT} WHERE cr.report_id = %s {GROUP}", (_viewer_id(), report_id))
    if row is None:
        raise not_found("Report")
    user = g.get("user")
    if row["status"] == "removed" and not (user and (user["role"] == "admin" or user["user_id"] == row["user_id"])):
        raise not_found("Report")
    return _decorate(row)


def _place(report_id: int, lat: float, lon: float) -> None:
    cell_id, min_lat, min_lon = cell_for(lat, lon)
    execute("INSERT IGNORE INTO GridCell (cell_id, min_latitude, min_longitude) VALUES (%s, %s, %s)",
            (cell_id, min_lat, min_lon))
    execute("INSERT INTO ReportCell (report_id, cell_id) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE cell_id = VALUES(cell_id)", (report_id, cell_id))


@bp.get("/reports")
@optional_auth
def list_reports():
    clauses, params = [], [_viewer_id()]
    user = g.get("user")
    bbox = bbox_args()
    if bbox:
        clauses.append("cr.latitude BETWEEN %s AND %s AND cr.longitude BETWEEN %s AND %s")
        params += [bbox[0], bbox[2], bbox[1], bbox[3]]
    status = request.args.get("status")
    if status:
        wanted = tuple(s.strip() for s in status.split(","))
        for s in wanted:
            one_of(s, "status", ("active", "resolved", "removed"))
        clauses.append(f"cr.status IN ({', '.join(['%s'] * len(wanted))})")
        params += list(wanted)
    if request.args.get("mine") in ("1", "true"):
        if not user:
            raise ApiError(401, "Please sign in to see your reports")
        clauses.append("cr.user_id = %s")
        params.append(user["user_id"])
    if not (user and user["role"] == "admin"):
        clauses.append("(cr.status <> 'removed' OR cr.user_id = %s)")
        params.append(_viewer_id())
    limit = arg_int("limit", 1, 500, default=100)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = query(f"{SELECT} {where} {GROUP} ORDER BY cr.reported_at DESC, cr.report_id DESC LIMIT %s",
                 (*params, limit))
    return jsonify({"reports": [_decorate(r) for r in rows]})


@bp.post("/reports")
@login_required
def create_report():
    data = json_body()
    require(data, "lat", "lon", "reason")
    lat, lon = latitude(data["lat"], "lat"), longitude(data["lon"], "lon")
    reason = as_text(data["reason"], "reason", 255)
    with transaction():
        report_id, _ = execute("INSERT INTO CrashReport (user_id, latitude, longitude, reason) VALUES (%s, %s, %s, %s)",
                               (g.user["user_id"], lat, lon, reason))
        _place(report_id, lat, lon)
    return jsonify({"report": _load(report_id)}), 201


@bp.get("/reports/<int:report_id>")
@optional_auth
def get_report(report_id: int):
    return jsonify({"report": _load(report_id)})


@bp.put("/reports/<int:report_id>")
@login_required
def update_report(report_id: int):
    report = _load(report_id)
    if report["user_id"] != g.user["user_id"]:
        raise ApiError(403, "Only the author can edit this report")
    if report["status"] == "removed":
        raise ApiError(409, "An admin removed this report, so it can no longer be edited", code="report_removed")
    data = json_body()
    sets, params = [], []
    if "reason" in data:
        sets.append("reason = %s")
        params.append(as_text(data["reason"], "reason", 255))
    if "status" in data:
        sets.append("status = %s")
        params.append(one_of(data["status"], "status", ("active", "resolved")))
    moved = "lat" in data or "lon" in data
    if moved:
        require(data, "lat", "lon")
        lat, lon = latitude(data["lat"], "lat"), longitude(data["lon"], "lon")
        sets += ["latitude = %s", "longitude = %s"]
        params += [lat, lon]
    if not sets:
        raise ApiError(400, "Nothing to update")
    with transaction():
        execute(f"UPDATE CrashReport SET {', '.join(sets)} WHERE report_id = %s", (*params, report_id))
        if moved:
            _place(report_id, lat, lon)
    return jsonify({"report": _load(report_id)})


@bp.delete("/reports/<int:report_id>")
@login_required
def delete_report(report_id: int):
    report = _load(report_id)
    if report["user_id"] != g.user["user_id"] and g.user["role"] != "admin":
        raise ApiError(403, "Only the author or an admin can delete this report")
    with transaction():  # votes and the cell placement cascade
        execute("DELETE FROM CrashReport WHERE report_id = %s", (report_id,))
    return "", 204


@bp.post("/reports/<int:report_id>/vote")
@login_required
def vote(report_id: int):
    report = _load(report_id)
    if report["user_id"] == g.user["user_id"]:
        raise ApiError(403, "You cannot vote on your own report", code="own_report")
    if report["status"] == "removed":
        raise ApiError(409, "This report was removed", code="report_removed")
    value = json_body().get("vote")
    if value not in (1, -1):
        raise ApiError(400, "vote must be 1 (confirm) or -1 (flag)")
    with transaction():
        execute("INSERT INTO ReportVote (report_id, user_id, vote) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE vote = VALUES(vote), voted_at = CURRENT_TIMESTAMP",
                (report_id, g.user["user_id"], value))
    return jsonify({"report": _load(report_id)})


@bp.delete("/reports/<int:report_id>/vote")
@login_required
def unvote(report_id: int):
    _load(report_id)
    with transaction():
        execute("DELETE FROM ReportVote WHERE report_id = %s AND user_id = %s", (report_id, g.user["user_id"]))
    return jsonify({"report": _load(report_id)})


@bp.patch("/reports/<int:report_id>/moderate")
@admin_required
def moderate(report_id: int):
    _load(report_id)
    status = one_of(json_body().get("status"), "status", ("active", "resolved", "removed"))
    with transaction():
        execute("UPDATE CrashReport SET status = %s, reviewed_by = %s, reviewed_at = CURRENT_TIMESTAMP "
                "WHERE report_id = %s", (status, g.user["user_id"], report_id))
    return jsonify({"report": _load(report_id)})
