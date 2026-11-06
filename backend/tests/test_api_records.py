"""CRUD & records: saved locations, crash reports (votes, moderation), subscriptions and alerts."""
from __future__ import annotations

from tests.helpers import execute, scalar


# --- saved locations -------------------------------------------------------------------------
def test_location_crud(api):
    user = api.register()
    r = api.call("POST", "/api/locations", user, json={"label": "Home", "lat": 40.110612, "lon": -88.207301})
    assert r.status_code == 201
    loc = r.get_json()["location"]
    assert loc["cell_id"] == "401_-883" and loc["subscriptions"] == 0 and loc["latitude"] == 40.110612

    r = api.call("PUT", f"/api/locations/{loc['location_id']}", user, json={"label": "Work", "lat": 40.15, "lon": -88.31})
    assert r.get_json()["location"]["label"] == "Work" and r.get_json()["location"]["cell_id"] == "401_-884"
    assert len(api.call("GET", "/api/locations", user).get_json()["locations"]) == 1
    assert api.call("DELETE", f"/api/locations/{loc['location_id']}", user).status_code == 204
    assert api.call("GET", f"/api/locations/{loc['location_id']}", user).status_code == 404


def test_location_validation_and_ownership(api):
    user = api.register()
    other = api.register("other@example.com")
    assert api.call("POST", "/api/locations", user, json={"label": "X", "lat": 91, "lon": 0}).status_code == 400
    assert api.call("POST", "/api/locations", user, json={"label": "", "lat": 40, "lon": -88}).status_code == 400
    assert api.call("POST", "/api/locations", user, json={"label": "x" * 61, "lat": 40, "lon": -88}).status_code == 400
    assert api.call("POST", "/api/locations", json={"label": "X", "lat": 40, "lon": -88}).status_code == 401
    loc = api.call("POST", "/api/locations", user, json={"label": "Home", "lat": 40, "lon": -88}).get_json()["location"]
    for method in ("GET", "PUT", "DELETE"):
        assert api.call(method, f"/api/locations/{loc['location_id']}", other, json={"label": "Mine"}).status_code == 404
    assert api.call("PUT", f"/api/locations/{loc['location_id']}", user, json={"lat": 40}).status_code == 400
    assert api.call("PUT", f"/api/locations/{loc['location_id']}", user, json={}).status_code == 400


# --- crash reports ---------------------------------------------------------------------------
def _report(api, user, **kw):
    body = {"lat": 40.1106, "lon": -88.2073, "reason": "Black ice on the overpass", **kw}
    r = api.call("POST", "/api/reports", user, json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()["report"]


def test_report_create_places_it_in_a_cell(api, db):
    user = api.register()
    rep = _report(api, user)
    assert rep["cell_id"] == "401_-883" and rep["status"] == "active" and rep["counts_toward_risk"] is True
    assert rep["author"] == "Vinay" and rep["confirms"] == 0 and rep["my_vote"] is None
    # a report in a brand-new cell creates the GridCell row too
    far = _report(api, user, lat=35.0001, lon=-100.0001)
    assert far["cell_id"] == "350_-1001"
    assert scalar(db, "SELECT COUNT(*) FROM GridCell WHERE cell_id = '350_-1001'") == 1


def test_report_edit_rules(api):
    author = api.register()
    other = api.register("other@example.com")
    rep = _report(api, author)
    rid = rep["report_id"]
    assert api.call("PUT", f"/api/reports/{rid}", other, json={"reason": "mine now"}).status_code == 403
    r = api.call("PUT", f"/api/reports/{rid}", author, json={"reason": "Cleared", "status": "resolved",
                                                            "lat": 40.15, "lon": -88.31})
    body = r.get_json()["report"]
    assert body["reason"] == "Cleared" and body["status"] == "resolved" and body["cell_id"] == "401_-884"
    assert api.call("PUT", f"/api/reports/{rid}", author, json={"status": "removed"}).status_code == 400
    assert api.call("PUT", f"/api/reports/{rid}", author, json={"reason": ""}).status_code == 400


def test_voting(api):
    author = api.register()
    voter = api.register("voter@example.com")
    rid = _report(api, author)["report_id"]
    assert api.call("POST", f"/api/reports/{rid}/vote", author, json={"vote": 1}).status_code == 403
    assert api.call("POST", f"/api/reports/{rid}/vote", voter, json={"vote": 2}).status_code == 400
    r = api.call("POST", f"/api/reports/{rid}/vote", voter, json={"vote": -1}).get_json()["report"]
    assert (r["flags"], r["my_vote"], r["counts_toward_risk"]) == (1, -1, False)   # more flags than confirms
    r = api.call("POST", f"/api/reports/{rid}/vote", voter, json={"vote": 1}).get_json()["report"]
    assert (r["confirms"], r["flags"], r["my_vote"], r["counts_toward_risk"]) == (1, 0, 1, True)
    r = api.call("DELETE", f"/api/reports/{rid}/vote", voter).get_json()["report"]
    assert (r["confirms"], r["my_vote"]) == (0, None)


def test_moderation(api, db):
    author = api.register()
    admin = api.register("admin@example.com", admin=True)
    stranger = api.register("stranger@example.com")
    rid = _report(api, author)["report_id"]
    assert api.call("PATCH", f"/api/reports/{rid}/moderate", author, json={"status": "removed"}).status_code == 403
    r = api.call("PATCH", f"/api/reports/{rid}/moderate", admin, json={"status": "removed"})
    rep = r.get_json()["report"]
    assert rep["status"] == "removed" and rep["reviewed_by"] == admin["user"]["user_id"] and rep["reviewed_at"]
    # removed reports are hidden from everyone except the author and admins
    assert api.call("GET", f"/api/reports/{rid}", stranger).status_code == 404
    assert api.call("GET", f"/api/reports/{rid}", author).status_code == 200
    assert rid not in [x["report_id"] for x in api.call("GET", "/api/reports").get_json()["reports"]]
    assert rid in [x["report_id"] for x in api.call("GET", "/api/reports", admin).get_json()["reports"]]
    # and can no longer be edited by their author or voted on
    assert api.call("PUT", f"/api/reports/{rid}", author, json={"reason": "x"}).status_code == 409
    assert api.call("POST", f"/api/reports/{rid}/vote", admin, json={"vote": 1}).status_code == 409
    # an admin may delete it outright
    assert api.call("DELETE", f"/api/reports/{rid}", admin).status_code == 204
    assert scalar(db, "SELECT COUNT(*) FROM ReportCell WHERE report_id = %s", (rid,)) == 0


def test_report_listing_filters(api):
    a = api.register()
    b = api.register("b@example.com")
    r1 = _report(api, a)["report_id"]
    r2 = _report(api, b, lat=41.88, lon=-87.63)["report_id"]
    api.call("PUT", f"/api/reports/{r1}", a, json={"status": "resolved"})
    ids = lambda **q: [x["report_id"] for x in api.call("GET", "/api/reports", a, query_string=q).get_json()["reports"]]
    assert set(ids()) == {r1, r2}
    assert ids(mine="1") == [r1]
    assert ids(status="active") == [r2]
    assert ids(min_lat=40, min_lon=-88.4, max_lat=40.3, max_lon=-88.1) == [r1]
    assert api.call("GET", "/api/reports", query_string={"mine": "1"}).status_code == 401
    assert api.call("GET", "/api/reports", query_string={"status": "weird"}).status_code == 400


def test_delete_report_permissions(api):
    author = api.register()
    other = api.register("other@example.com")
    rid = _report(api, author)["report_id"]
    assert api.call("DELETE", f"/api/reports/{rid}", other).status_code == 403
    assert api.call("DELETE", f"/api/reports/{rid}", author).status_code == 204
    assert api.call("GET", f"/api/reports/{rid}").status_code == 404


# --- subscriptions and alerts ----------------------------------------------------------------
def _location(api, user, lat=40.1106, lon=-88.2073):
    return api.call("POST", "/api/locations", user, json={"label": "Home", "lat": lat, "lon": lon}).get_json()["location"]


def test_subscription_crud(api):
    user = api.register()
    other = api.register("other@example.com")
    loc = _location(api, user)
    r = api.call("POST", "/api/subscriptions", user,
                 json={"location_id": loc["location_id"], "condition_id": 4, "alert_threshold": 5})
    assert r.status_code == 201
    sub = r.get_json()["subscription"]
    assert sub["weather_group"] == "wet" and sub["light_group"] == "dark" and sub["is_active"] is True
    assert sub["baseline_score"] == sub["current_score"] > 0          # the wet+dark history in this cell
    dup = api.call("POST", "/api/subscriptions", user,
                   json={"location_id": loc["location_id"], "condition_id": 4, "alert_threshold": 5})
    assert dup.status_code == 409
    assert api.call("POST", "/api/subscriptions", other,
                    json={"location_id": loc["location_id"], "condition_id": 1, "alert_threshold": 5}).status_code == 404
    assert api.call("POST", "/api/subscriptions", user,
                    json={"location_id": loc["location_id"], "condition_id": 1, "alert_threshold": 0}).status_code == 400
    sid = sub["subscription_id"]
    r = api.call("PATCH", f"/api/subscriptions/{sid}", user, json={"alert_threshold": 12.5, "is_active": False})
    assert (r.get_json()["subscription"]["alert_threshold"], r.get_json()["subscription"]["is_active"]) == (12.5, False)
    assert api.call("PATCH", f"/api/subscriptions/{sid}", user, json={"is_active": "no"}).status_code == 400
    assert api.call("PATCH", f"/api/subscriptions/{sid}", other, json={"is_active": True}).status_code == 404
    assert len(api.call("GET", "/api/subscriptions", user).get_json()["subscriptions"]) == 1
    assert api.call("DELETE", f"/api/subscriptions/{sid}", user).status_code == 204
    assert api.call("GET", "/api/subscriptions", user).get_json()["subscriptions"] == []


def test_alert_job_fires_on_report_spike_once(api, db):
    user = api.register()
    admin = api.register("admin@example.com", admin=True)
    reporter = api.register("reporter@example.com")
    loc = _location(api, user, lat=40.15, lon=-88.31)      # cell 401_-884: one dry/dark crash
    sub = api.call("POST", "/api/subscriptions", user,
                   json={"location_id": loc["location_id"], "condition_id": 3, "alert_threshold": 10}).get_json()
    baseline = sub["subscription"]["baseline_score"]
    assert baseline == 0.0                                  # no wet/day history in that cell

    assert api.call("POST", "/api/alerts/run", user).status_code == 403
    first = api.call("POST", "/api/alerts/run", admin).get_json()
    assert first["alerts_created"] == 0

    for i in range(3):                                      # three fresh reports in the same cell
        _report(api, reporter, lat=40.151 + i / 1000, lon=-88.311)
    second = api.call("POST", "/api/alerts/run", admin).get_json()
    assert second["alerts_created"] == 1 and second["alerts"][0]["current"] > baseline + 10
    third = api.call("POST", "/api/alerts/run", admin).get_json()
    assert third["alerts_created"] == 0                     # compared against the last alert, not the baseline

    alerts = api.call("GET", "/api/alerts", user).get_json()["alerts"]
    assert len(alerts) == 1 and alerts[0]["location_label"] == "Home"
    assert scalar(db, "SELECT COUNT(*) FROM Alert") == 1
    # pausing a subscription stops the job from checking it
    api.call("PATCH", f"/api/subscriptions/{sub['subscription']['subscription_id']}", user, json={"is_active": False})
    assert api.call("POST", "/api/alerts/run", admin).get_json()["checked"] == 0
    execute(db, "DELETE FROM Alert")
