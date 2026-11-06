"""Unit tests for code that needs no database: geometry, risk levels, providers, route choice."""
from __future__ import annotations

from decimal import Decimal

import pytest
import requests

from app.api.routes import choose_options
from app.dbsetup import split_sql
from app.errors import ApiError
from app.geo import cell_bounds, cell_for, cells_along, haversine_km
from app.risk.base import CellScore, RiskModel, risk_level
from app.services import geocoding, routing, weather


# --- grid formula (Stage 2, section 2.2) -----------------------------------------------------
@pytest.mark.parametrize("lat, lon, expected", [
    (40.1106, -88.2073, "401_-883"),      # the worked example in the design doc
    ("40.1", "-88.3", "401_-883"),        # exact boundaries belong to the cell above/right
    (40.0999999, -88.3000001, "400_-884"),
    (-33.86, 151.21, "-339_1512"),        # southern and eastern hemispheres
    (0, 0, "0_0"),
])
def test_cell_for(lat, lon, expected):
    assert cell_for(lat, lon)[0] == expected


def test_cell_for_returns_lower_left_corner():
    cell, min_lat, min_lon = cell_for(40.1106, -88.2073)
    assert (min_lat, min_lon) == (Decimal("40.1"), Decimal("-88.3"))
    assert cell_bounds(cell) == (40.1, -88.3, 40.2, -88.2)


def test_cell_bounds_rejects_garbage():
    with pytest.raises(ValueError):
        cell_bounds("not-a-cell")


def test_haversine_champaign_to_chicago():
    assert 195 < haversine_km(40.1164, -88.2434, 41.8781, -87.6298) < 205


def test_cells_along_is_ordered_and_sums_to_path_length():
    path = [(40.05, -88.25), (40.35, -88.25)]
    cells = cells_along(path)
    assert [c for c, _ in cells] == ["400_-883", "401_-883", "402_-883", "403_-883"]
    assert abs(sum(km for _, km in cells) - haversine_km(*path[0], *path[1])) < 0.01


def test_cells_along_single_point():
    assert cells_along([(40.11, -88.21)]) == [("401_-883", 0.0)]


# --- risk ------------------------------------------------------------------------------------
@pytest.mark.parametrize("score, level", [(None, None), (0, "low"), (24.99, "low"), (25, "moderate"),
                                          (50, "high"), (74.9, "high"), (75, "very_high"), (100, "very_high")])
def test_risk_level(score, level):
    assert risk_level(score) == level


class FakeModel(RiskModel):
    name = "fake"

    def score_cells(self, cell_ids, condition_id):
        return {"a": CellScore("a", 80.0, crash_count=3), "b": CellScore("b", 20.0)}


def test_score_route_is_distance_weighted_and_missing_cells_score_zero():
    risk = FakeModel().score_route([("a", 1.0), ("b", 3.0), ("c", 4.0)], condition_id=1)
    assert risk.score == pytest.approx((80 * 1 + 20 * 3 + 0 * 4) / 8)
    assert [c["cell_id"] for c in risk.cells] == ["a", "b", "c"]
    assert risk.cells[0]["crash_count"] == 3 and risk.cells[2]["score"] == 0.0


def test_score_cell_defaults_to_zero():
    assert FakeModel().score_cell("zzz", 1).score == 0.0


# --- route choice ----------------------------------------------------------------------------
ROUTES = [
    {"duration_s": 1000, "risk_score": 60.0},   # fastest, riskiest
    {"duration_s": 1100, "risk_score": 30.0},   # a little slower, much safer
    {"duration_s": 2000, "risk_score": 25.0},   # safest, slow
]


def test_choose_options_extremes():
    picks = choose_options(ROUTES, safety_weight=0.5)
    assert picks["fastest"] == 0 and picks["safest"] == 2


@pytest.mark.parametrize("weight, expected", [(0.0, 0), (0.5, 1), (1.0, 2)])
def test_choose_options_balanced_follows_safety_weight(weight, expected):
    assert choose_options(ROUTES, weight)["balanced"] == expected


def test_choose_options_single_route():
    assert choose_options([{"duration_s": 5, "risk_score": 5}], 0.5) == {"fastest": 0, "safest": 0, "balanced": 0}


# --- SQL file splitting ----------------------------------------------------------------------
def test_split_sql_handles_delimiter_blocks():
    text = """-- comment
CREATE TABLE a (x INT);
DELIMITER //
CREATE TRIGGER t BEFORE INSERT ON a FOR EACH ROW
BEGIN
  SET NEW.x = 1;
END//
DELIMITER ;
INSERT INTO a VALUES (1);
"""
    stmts = split_sql(text)
    assert len(stmts) == 3
    assert stmts[1].startswith("CREATE TRIGGER") and stmts[1].endswith("END")


# --- offline providers -----------------------------------------------------------------------
def test_offline_router_offers_three_routes_direct_is_fastest():
    routes = routing.OfflineRouter().routes((40.1164, -88.2434), (41.8781, -87.6298))
    assert len(routes) == 3
    assert routes[0].duration_s < routes[1].duration_s and routes[0].duration_s < routes[2].duration_s
    assert routes[0].geometry[0] == (40.1164, -88.2434) and routes[0].geometry[-1] == (41.8781, -87.6298)


def test_offline_router_rejects_zero_length_trip():
    with pytest.raises(ApiError) as exc:
        routing.OfflineRouter().routes((40.1, -88.2), (40.1, -88.2))
    assert exc.value.status == 422


def test_offline_geocoder_coordinates_and_cities():
    g = geocoding.OfflineGeocoder()
    assert g.search("40.11, -88.24")[0]["lat"] == 40.11
    assert g.search("champaign")[0]["label"] == "Champaign, IL"
    assert g.search("nowhere-ville") == []


@pytest.mark.parametrize("code, group", [(0, "dry"), (3, "dry"), (45, "low_visibility"), (61, "wet"),
                                         (66, "snow_ice"), (73, "snow_ice"), (81, "wet"), (95, "wet")])
def test_wmo_to_group(code, group):
    assert weather.wmo_to_group(code)[0] == group


# --- online providers with the network mocked ------------------------------------------------
class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self.payload


def test_osrm_router_parses_alternatives(monkeypatch):
    payload = {"code": "Ok", "routes": [
        {"distance": 1000.0, "duration": 100.0, "geometry": {"coordinates": [[-88.2, 40.1], [-88.1, 40.2]]}},
        {"distance": 1200.0, "duration": 90.0, "geometry": {"coordinates": [[-88.2, 40.1], [-88.0, 40.2]]}},
    ]}
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers)
        return FakeResponse(payload)

    monkeypatch.setattr(routing.requests, "get", fake_get)
    routes = routing.OSRMRouter("https://osrm.test", 5, "ua").routes((40.1, -88.2), (40.2, -88.1))
    assert seen["url"] == "https://osrm.test/route/v1/driving/-88.2,40.1;-88.1,40.2"
    assert seen["params"]["alternatives"] == "true" and seen["headers"]["User-Agent"] == "ua"
    assert routes[0].geometry == [(40.1, -88.2), (40.2, -88.1)] and routes[1].duration_s == 90.0


def test_osrm_router_no_route(monkeypatch):
    monkeypatch.setattr(routing.requests, "get", lambda *a, **k: FakeResponse({"code": "NoRoute", "routes": []}))
    with pytest.raises(ApiError) as exc:
        routing.OSRMRouter("https://osrm.test", 5, "ua").routes((40.1, -88.2), (40.2, -88.1))
    assert exc.value.code == "no_route"


def test_open_meteo_mapping(monkeypatch):
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: FakeResponse(
        {"current": {"weather_code": 71, "is_day": 0, "temperature_2m": -3.5}}))
    now = weather.OpenMeteoWeather("https://om.test", 5, "ua").current(40.1, -88.2)
    assert now == {"weather_group": "snow_ice", "light_group": "dark", "description": "Snow",
                   "temperature_c": -3.5, "source": "open-meteo"}


def test_nominatim_parses_results(monkeypatch):
    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: FakeResponse(
        [{"display_name": "Urbana, Illinois", "lat": "40.11", "lon": "-88.20"}]))
    hits = geocoding.NominatimGeocoder("https://nom.test", 5, "ua").search("urbana")
    assert hits == [{"label": "Urbana, Illinois", "lat": 40.11, "lon": -88.2, "source": "nominatim"}]
