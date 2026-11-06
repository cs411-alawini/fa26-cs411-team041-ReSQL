"""Search & lookup: lookups, crash search, breakdowns, crash detail, grid cells."""
from __future__ import annotations

CHAMPAIGN = {"min_lat": 40.0, "min_lon": -88.4, "max_lat": 40.3, "max_lon": -88.1}


def test_lookups(client):
    body = client.get("/api/lookups").get_json()
    assert len(body["weather_conditions"]) == 13 and len(body["light_conditions"]) == 9
    assert len(body["condition_profiles"]) == 8
    assert body["states"] == [{"state_code": 17, "state_name": "Illinois"}]
    assert body["years"] == [2024]
    counties = client.get("/api/states/17/counties").get_json()["counties"]
    assert [c["county_name"] for c in counties] == ["Champaign", "Cook"]


def test_search_by_bbox(client):
    body = client.get("/api/crashes", query_string=CHAMPAIGN).get_json()
    assert body["total"] == 5
    assert [c["st_case"] for c in body["crashes"]] == [170005, 170004, 170003, 170002, 170001]  # newest first
    first = body["crashes"][0]
    assert first["county_name"] == "Champaign" and first["state_name"] == "Illinois"
    assert first["road_class"] == "Local" and first["light_group"] == "dark"


def test_search_filters(client):
    q = lambda **kw: client.get("/api/crashes", query_string={**CHAMPAIGN, **kw}).get_json()["total"]
    assert q(weather_group="wet") == 2
    assert q(weather_group="wet", light_group="dark") == 2
    assert q(light_group="day") == 2
    assert q(func_sys_code=1) == 2
    assert q(month=1) == 2
    assert q(season="winter") == 3
    assert q(time_of_day="night") == 2           # 22:00 and 23:00
    assert q(hour_from=8, hour_to=14) == 2
    assert q(year=2023) == 0


def test_search_by_state_and_county_with_paging(client):
    body = client.get("/api/crashes", query_string={"state_code": 17, "limit": 2, "offset": 1}).get_json()
    assert body["total"] == 6 and len(body["crashes"]) == 2
    assert client.get("/api/crashes", query_string={"state_code": 17, "county_code": 31}).get_json()["total"] == 1


def test_search_validation(client):
    assert client.get("/api/crashes").status_code == 400                                   # no area
    assert client.get("/api/crashes", query_string={"county_code": 19}).status_code == 400
    assert client.get("/api/crashes", query_string={**CHAMPAIGN, "weather_group": "lava"}).status_code == 400
    assert client.get("/api/crashes", query_string={**CHAMPAIGN, "month": 13}).status_code == 400
    assert client.get("/api/crashes", query_string={**CHAMPAIGN, "limit": 5000}).status_code == 400
    bad = {**CHAMPAIGN, "min_lat": 41}
    assert client.get("/api/crashes", query_string=bad).status_code == 400


def test_stats(client):
    s = client.get("/api/crashes/stats", query_string=CHAMPAIGN).get_json()
    assert s["crashes"] == 5 and s["fatalities"] == 6
    groups = {g["weather_group"]: g["crashes"] for g in s["by_weather_group"]}
    assert groups == {"wet": 2, "snow_ice": 1, "dry": 2}
    assert sum(m["crashes"] for m in s["by_month"]) == 5 and len(s["by_month"]) == 12
    assert len(s["by_hour"]) == 24 and s["by_hour"][22]["crashes"] == 1
    # the weather join: 3 crashes matched a station; all had rain, one had snowfall
    assert s["station_weather"] == {"crashes_with_station": 3, "on_wet_days": 3, "on_snow_days": 1,
                                    "avg_temp_max_c": 3.3}


def test_crash_detail(client):
    body = client.get("/api/crashes/2024/170003").get_json()
    assert body["crash"]["weather"] == "Snow" and body["crash"]["cell_id"] == "401_-883"
    assert body["station_weather"]["station_name"] == "CHAMPAIGN WILLARD AP"
    assert body["station_weather"]["snowfall_mm"] == 30.0
    assert len(body["vehicles"]) == 1 and len(body["people"]) == 2
    assert client.get("/api/crashes/2024/170004").get_json()["station_weather"] is None
    assert client.get("/api/crashes/2024/1").status_code == 404


def test_cells_in_area(client):
    body = client.get("/api/cells", query_string={**CHAMPAIGN, "condition_id": 4}).get_json()  # wet + dark
    assert [c["cell_id"] for c in body["cells"]] == ["401_-883"]
    cell = body["cells"][0]
    assert cell["crash_count"] == 2 and cell["fatality_count"] == 3 and cell["risk_score"] > 0
    big = {"min_lat": 25, "min_lon": -120, "max_lat": 49, "max_lon": -70}
    assert client.get("/api/cells", query_string=big).status_code == 400


def test_cell_detail(client):
    body = client.get("/api/cells/401_-883").get_json()
    assert body["bounds"] == [40.1, -88.3, 40.2, -88.2]
    wet_dark = next(c for c in body["by_condition"] if c["weather_group"] == "wet" and c["light_group"] == "dark")
    assert wet_dark["crash_count"] == 2 and wet_dark["risk_level"] is not None
    assert body["stats"]["crashes"] == 4 and body["risk_model"]["placeholder"] is True
    assert client.get("/api/cells/999_999").status_code == 404
    assert client.get("/api/cells/garbage").status_code == 400


def test_geocode_and_current_conditions(client):
    hits = client.get("/api/geocode", query_string={"q": "Urbana"}).get_json()
    assert hits["results"][0]["label"] == "Urbana, IL" and hits["source"] == "offline"
    assert client.get("/api/geocode", query_string={"q": ""}).status_code == 400
    now = client.get("/api/conditions/current", query_string={"lat": 40.1, "lon": -88.2}).get_json()
    assert now["weather_group"] == "dry" and now["condition_id"] in (1, 2)
    assert client.get("/api/conditions/current", query_string={"lat": 99, "lon": 0}).status_code == 400
