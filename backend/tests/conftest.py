"""Test fixtures.

The tests run against a real MySQL 8 database so that constraints, triggers and the risk view
are exercised exactly as in production. They need an EMPTY scratch database whose name ends in
"_test"; every table in it is dropped and recreated. Configure it with:

  TEST_DB_HOST (127.0.0.1)  TEST_DB_PORT (3306)  TEST_DB_USER (resql)
  TEST_DB_PASSWORD ("")     TEST_DB_NAME (resql_test)

Never point these at Cloud SQL.
"""
from __future__ import annotations

import os
from datetime import date

import pymysql
import pytest

from app import create_app
from app.dbsetup import apply_schema, drop_all
from app.jobs.cell_counts import REFRESH_SQL

DB = {
    "host": os.environ.get("TEST_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("TEST_DB_PORT", "3306")),
    "user": os.environ.get("TEST_DB_USER", "resql"),
    "password": os.environ.get("TEST_DB_PASSWORD", ""),
    "database": os.environ.get("TEST_DB_NAME", "resql_test"),
}
if not DB["database"].endswith("_test"):
    raise RuntimeError("TEST_DB_NAME must end with '_test'; the tests drop every table in it")

USER_TABLES = ("Alert", "Subscription", "RouteOption", "RouteRequest", "ReportVote", "ReportCell",
               "CrashReport", "SavedLocation", "AppUser")

# Champaign, IL area (cells 401_-883 and 401_-884) plus one Chicago site (418_-877).
SITES = [
    # lat, lon, state, county, cell
    ("40.11060000", "-88.20730000", 17, 19, "401_-883"),
    ("40.11640000", "-88.24340000", 17, 19, "401_-883"),
    ("40.15000000", "-88.31000000", 17, 19, "401_-884"),
    ("41.87810000", "-87.62980000", 17, 31, "418_-877"),
]
# year, case, site index, date, hour, weather_code, light_code, func_sys, station?, fatalities
CRASHES = [
    (2024, 170001, 0, date(2024, 1, 15), 22, 2, 2, 1, True, 1),    # wet, dark, interstate
    (2024, 170002, 0, date(2024, 1, 20), 23, 2, 3, 1, True, 2),    # wet, dark
    (2024, 170003, 1, date(2024, 2, 3), 8, 4, 1, 3, True, 1),      # snow, day
    (2024, 170004, 1, date(2024, 7, 4), 14, 1, 1, 3, False, 1),    # dry, day, no station
    (2024, 170005, 2, date(2024, 10, 31), 19, 10, 2, 7, False, 1), # cloudy(dry), dark, local
    (2024, 170006, 3, date(2024, 12, 24), 3, 99, 9, 99, False, 1), # unknown weather/light
]


def _raw_conn():
    return pymysql.connect(**DB, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def _seed(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO State VALUES (17, 'Illinois')")
        cur.executemany("INSERT INTO County VALUES (%s, %s, %s)", [(17, 19, "Champaign"), (17, 31, "Cook")])
        cells = sorted({s[4] for s in SITES})
        for cell in cells:
            a, b = (int(x) for x in cell.split("_"))
            cur.execute("INSERT INTO GridCell VALUES (%s, %s, %s)", (cell, a / 10, b / 10))
        cur.executemany("INSERT INTO CrashSite VALUES (%s, %s, %s, %s, %s)", SITES)
        cur.execute("INSERT INTO WeatherStation VALUES ('USW00094870', 'CHAMPAIGN WILLARD AP', 40.0394, -88.2781)")
        for c in CRASHES:
            if c[8]:
                cur.execute("INSERT INTO DailyWeather VALUES ('USW00094870', %s, 12.7, %s, 0, 3.3, -1.1, 4.5)",
                            (c[3], 30.0 if c[5] == 4 else 0.0))
        for year, case, site, d, hour, wc, lc, fs, station, fat in CRASHES:
            lat, lon = SITES[site][0], SITES[site][1]
            cur.execute(
                "INSERT INTO Crash VALUES (%s, %s, %s, %s, %s, %s, 30, %s, %s, %s, %s, 2, %s, 2, 1)",
                (year, case, lat, lon, d, hour, wc, lc, fs, "USW00094870" if station else None, fat))
            cur.execute("INSERT INTO Vehicle VALUES (%s, %s, 1, 4, 2015, %s, %s)",
                        (year, case, 3 if case % 2 else 0, fat))
            cur.execute("INSERT INTO Person VALUES (%s, %s, 1, 1, 1, 4, 34, 3)", (year, case))
            cur.execute("INSERT INTO Person VALUES (%s, %s, 0, 1, 5, 4, 61, 0)", (year, case))
        cur.execute(REFRESH_SQL)
    conn.commit()


@pytest.fixture(scope="session")
def database():
    conn = _raw_conn()
    drop_all(conn)
    apply_schema(conn)
    _seed(conn)
    yield conn
    conn.close()


@pytest.fixture()
def db(database):
    """A raw connection for assertions; user-created rows are wiped after every test."""
    yield database
    database.rollback()
    with database.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in USER_TABLES:
            cur.execute(f"DELETE FROM {table}")
        cur.execute("DELETE FROM GridCell WHERE cell_id NOT IN (SELECT cell_id FROM CrashSite)")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    database.commit()


@pytest.fixture()
def app(db):
    return create_app({
        "TESTING": True,
        "DB_HOST": DB["host"], "DB_PORT": DB["port"], "DB_USER": DB["user"],
        "DB_PASSWORD": DB["password"], "DB_NAME": DB["database"], "DB_UNIX_SOCKET": None,
        "JWT_SECRET": "test-secret", "ROUTING_PROVIDER": "offline", "GEOCODER": "offline",
        "WEATHER_PROVIDER": "offline", "RISK_MODEL": "stage2_view",
    })


@pytest.fixture()
def client(app):
    return app.test_client()


class Api:
    """Convenience wrapper: sign up users and call the API as them."""

    def __init__(self, client, db):
        self.client, self.db = client, db

    def register(self, email="vinay@example.com", password="password123", name="Vinay", admin=False) -> dict:
        r = self.client.post("/api/auth/register", json={"email": email, "password": password, "display_name": name})
        assert r.status_code == 201, r.get_json()
        body = r.get_json()
        if admin:
            with self.db.cursor() as cur:
                cur.execute("UPDATE AppUser SET role = 'admin' WHERE user_id = %s", (body["user"]["user_id"],))
            self.db.commit()
            body["user"]["role"] = "admin"
        body["headers"] = {"Authorization": f"Bearer {body['token']}"}
        return body

    def call(self, method: str, url: str, user: dict | None = None, **kwargs):
        headers = kwargs.pop("headers", {})
        if user:
            headers.update(user["headers"])
        return self.client.open(url, method=method, headers=headers, **kwargs)


@pytest.fixture()
def api(client, db):
    return Api(client, db)

