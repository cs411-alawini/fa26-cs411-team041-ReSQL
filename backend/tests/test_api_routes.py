"""The safest-route recommender and route history."""
from __future__ import annotations

from app.services import routing
from tests.helpers import scalar

TRIP = {"origin": {"lat": 40.1164, "lon": -88.2434}, "destination": {"lat": 40.4842, "lon": -88.9937}}


def test_analyze_anonymous_is_not_saved(api, db):
    r = api.client.post("/api/routes/analyze", json={**TRIP, "conditions": {"weather": "wet", "time_of_day": "night"}})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["route_id"] is None and body["provider"] == "offline" and body["provider_fallback"] is False
    assert body["risk_model"] == {"name": "stage2_view", "placeholder": True}
    assert body["conditions"]["weather_group"] == "wet" and body["conditions"]["light_group"] == "dark"
    assert body["conditions"]["condition_id"] == 4 and body["conditions"]["hours"] == [21, 5]
    assert len(body["routes"]) == 3 and [o["option_type"] for o in body["options"]] == ["fastest", "safest", "balanced"]
    route = body["routes"][body["options"][0]["route_index"]]
    assert route["geometry"][0] == [40.1164, -88.2434]
    assert route["cells"][0]["cell_id"] == "401_-883"          # the trip starts in the Champaign cell
    assert route["cells"][0]["crash_count"] == 2              # its wet + dark history
    assert {f["key"] for f in route["stats"]["factors"]} == {"weather", "time", "road", "vehicle"}
    assert len(route["stats"]["by_month"]) == 12
    assert scalar(db, "SELECT COUNT(*) FROM RouteRequest") == 0


def test_analyze_signed_in_saves_request_and_three_options(api, db):
    user = api.register()
    body = api.call("POST", "/api/routes/analyze", user, json={**TRIP, "conditions": {"weather": "dry"}}).get_json()
    rid = body["route_id"]
    assert rid is not None
    assert scalar(db, "SELECT COUNT(*) FROM RouteOption WHERE route_id = %s", (rid,)) == 3
    fastest = next(o for o in body["options"] if o["option_type"] == "fastest")
    stored = scalar(db, "SELECT travel_time_s FROM RouteOption WHERE route_id = %s AND option_type = 'fastest'", (rid,))
    assert stored == int(fastest["duration_s"])
    # fastest really is the quickest, safest really is the lowest risk
    assert fastest["duration_s"] == min(r["duration_s"] for r in body["routes"])
    safest = next(o for o in body["options"] if o["option_type"] == "safest")
    assert safest["risk_score"] == min(r["risk_score"] for r in body["routes"])


def test_save_false_and_safety_weight_override(api, db):
    user = api.register()
    body = api.call("POST", "/api/routes/analyze", user, json={**TRIP, "save": False, "safety_weight": 1}).get_json()
    assert body["route_id"] is None and body["safety_weight"] == 1.0
    balanced = next(o for o in body["options"] if o["option_type"] == "balanced")
    assert balanced["route_index"] == next(o for o in body["options"] if o["option_type"] == "safest")["route_index"]


def test_user_safety_weight_is_used_by_default(api):
    user = api.register()
    api.call("PATCH", "/api/users/me", user, json={"safety_weight": 0})
    body = api.call("POST", "/api/routes/analyze", user, json=TRIP).get_json()
    assert body["safety_weight"] == 0.0
    by_type = {o["option_type"]: o["route_index"] for o in body["options"]}
    assert by_type["balanced"] == by_type["fastest"]


def test_choose_option_history_and_delete(api, db):
    user = api.register()
    other = api.register("other@example.com")
    rid = api.call("POST", "/api/routes/analyze", user, json=TRIP).get_json()["route_id"]
    r = api.call("PATCH", f"/api/routes/{rid}", user, json={"chosen_option": "safest"})
    assert r.status_code == 200 and r.get_json()["route"]["chosen_option"] == "safest"
    assert api.call("PATCH", f"/api/routes/{rid}", user, json={"chosen_option": "scenic"}).status_code == 400
    assert api.call("PATCH", f"/api/routes/{rid}", other, json={"chosen_option": "fastest"}).status_code == 404
    hist = api.call("GET", "/api/routes", user).get_json()["routes"]
    assert len(hist) == 1 and len(hist[0]["options"]) == 3 and hist[0]["options"][0]["risk_level"]
    assert api.call("GET", "/api/routes", other).get_json()["routes"] == []
    assert api.call("DELETE", f"/api/routes/{rid}", other).status_code == 404
    assert api.call("DELETE", f"/api/routes/{rid}", user).status_code == 204
    assert scalar(db, "SELECT COUNT(*) FROM RouteOption") == 0


def test_analyze_validation(api):
    c = api.client
    assert c.post("/api/routes/analyze", json={"origin": {"lat": 40}}).status_code == 400
    same = {"origin": TRIP["origin"], "destination": TRIP["origin"]}
    assert c.post("/api/routes/analyze", json=same).status_code == 422
    far = {"origin": {"lat": 47.6, "lon": -122.3}, "destination": {"lat": 25.8, "lon": -80.2}}
    assert c.post("/api/routes/analyze", json=far).get_json()["error"]["code"] == "trip_too_long"
    assert c.post("/api/routes/analyze", json={**TRIP, "conditions": {"weather": "hail"}}).status_code == 400
    assert c.post("/api/routes/analyze", json={**TRIP, "conditions": {"time_of_day": "noon"}}).status_code == 400
    assert c.post("/api/routes/analyze", json={**TRIP, "conditions": {"month": 13}}).status_code == 400
    assert c.post("/api/routes/analyze", json={**TRIP, "conditions": {"hour": 30}}).status_code == 400
    assert c.post("/api/routes/analyze", json={**TRIP, "safety_weight": 3}).status_code == 400


def test_routing_service_failure_falls_back_to_offline(app, monkeypatch):
    app.config["ROUTING_PROVIDER"] = "osrm"

    def boom(*a, **k):
        raise routing.requests.ConnectionError("no network")

    monkeypatch.setattr(routing.requests, "get", boom)
    body = app.test_client().post("/api/routes/analyze", json=TRIP).get_json()
    assert body["provider"] == "offline" and body["provider_fallback"] is True

    app.config["PROVIDER_FALLBACK"] = False
    r = app.test_client().post("/api/routes/analyze", json=TRIP)
    assert r.status_code == 502 and r.get_json()["error"]["code"] == "routing_unavailable"


def test_choosing_an_option_that_was_not_offered_is_rejected_without_the_trigger(api, db):
    """A database restored from a Cloud SQL export has no triggers, so the API checks the rule itself."""
    import os

    from app.dbsetup import DATABASE_DIR, split_sql
    from tests.helpers import execute

    user = api.register()
    rid = api.call("POST", "/api/routes/analyze", user, json=TRIP).get_json()["route_id"]
    execute(db, "DELETE FROM RouteOption WHERE route_id = %s AND option_type = 'safest'", (rid,))
    with open(os.path.join(DATABASE_DIR, "triggers.sql"), encoding="utf-8") as fh:
        create = next(s for s in split_sql(fh.read()) if "trg_routerequest_choice_bu" in s)
    execute(db, "DROP TRIGGER trg_routerequest_choice_bu")
    try:
        r = api.call("PATCH", f"/api/routes/{rid}", user, json={"chosen_option": "safest"})
        assert r.status_code == 409 and "not offered" in r.get_json()["error"]["message"]
        assert scalar(db, "SELECT chosen_option FROM RouteRequest WHERE route_id = %s", (rid,)) is None
        assert api.call("PATCH", f"/api/routes/{rid}", user, json={"chosen_option": "fastest"}).status_code == 200
    finally:
        execute(db, create)
