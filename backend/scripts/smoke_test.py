"""Smoke test the app against a real database, such as the team's Cloud SQL instance.

Run from the backend folder with the same settings the app uses (backend/.env or DB_* variables):

    python scripts/smoke_test.py            # read-only checks
    python scripts/smoke_test.py --write    # also a full create/update/delete round trip

Read-only mode changes nothing. --write creates two throwaway accounts (smoke-...@example.invalid)
with a saved location, subscription, report, vote and saved route, then deletes the accounts; the
delete rules remove everything they created. Add --admin-email/--admin-password to also check
moderation with an existing admin account.

Exit code 0 means no FAIL lines. WARN lines are worth reading but do not stop the app working.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pymysql  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# Tables and columns the application reads or writes (doc/stage2_database_design-p2.md, section 5).
EXPECTED = {
    "State": ["state_code", "state_name"],
    "County": ["state_code", "county_code", "county_name"],
    "WeatherCondition": ["weather_code", "description", "weather_group"],
    "LightCondition": ["light_code", "description", "light_group"],
    "RoadClass": ["func_sys_code", "description"],
    "GridCell": ["cell_id", "min_latitude", "min_longitude"],
    "WeatherStation": ["station_id", "station_name", "latitude", "longitude"],
    "DailyWeather": ["station_id", "obs_date", "precipitation_mm", "snowfall_mm", "snow_depth_mm",
                     "temp_max_c", "temp_min_c", "avg_wind_ms"],
    "CrashSite": ["latitude", "longitude", "state_code", "county_code", "cell_id"],
    "Crash": ["data_year", "st_case", "latitude", "longitude", "crash_date", "crash_hour", "crash_minute",
              "weather_code", "light_code", "func_sys_code", "weather_station_id", "rural_urban", "fatalities",
              "persons_involved", "vehicles_involved"],
    "Vehicle": ["data_year", "st_case", "veh_no", "body_type", "model_year", "speeding_related", "deaths_in_vehicle"],
    "Person": ["data_year", "st_case", "veh_no", "per_no", "person_type", "injury_severity", "age", "restraint_use"],
    "ConditionProfile": ["condition_id", "weather_group", "light_group", "national_est_crashes",
                         "national_serious_fatal_pct"],
    "CellRiskScore": ["cell_id", "condition_id", "crash_count", "fatality_count", "computed_at"],
    "AppUser": ["user_id", "email", "password_hash", "display_name", "role", "safety_weight", "units", "created_at"],
    "SavedLocation": ["location_id", "user_id", "label", "latitude", "longitude", "created_at"],
    "CrashReport": ["report_id", "user_id", "latitude", "longitude", "reason", "status", "reported_at",
                    "reviewed_by", "reviewed_at"],
    "ReportCell": ["report_id", "cell_id"],
    "ReportVote": ["report_id", "user_id", "vote", "voted_at"],
    "RouteRequest": ["route_id", "user_id", "origin_lat", "origin_lon", "dest_lat", "dest_lon", "chosen_option",
                     "requested_at"],
    "RouteOption": ["route_id", "option_type", "travel_time_s", "risk_score"],
    "Subscription": ["subscription_id", "location_id", "condition_id", "alert_threshold", "baseline_score",
                     "is_active", "created_at"],
    "Alert": ["alert_id", "subscription_id", "risk_score_at_send", "sent_at"],
}
VIEW = ("CellRiskCurrent", ["cell_id", "condition_id", "crash_count", "fatality_count", "recent_reports", "risk_score"])
TRIGGERS = ["trg_crashreport_review_bi", "trg_crashreport_review_bu", "trg_person_vehicle_bi",
            "trg_person_vehicle_bu", "trg_routerequest_choice_bi", "trg_routerequest_choice_bu"]
AUTO_INCREMENT = ["AppUser.user_id", "SavedLocation.location_id", "CrashReport.report_id", "RouteRequest.route_id",
                  "Subscription.subscription_id", "Alert.alert_id"]


class Report:
    def __init__(self) -> None:
        self.counts = {"PASS": 0, "WARN": 0, "FAIL": 0}

    def line(self, level: str, msg: str) -> None:
        self.counts[level] += 1
        print(f"  {level:<4}  {msg}", flush=True)

    def ok(self, msg: str) -> None:
        self.line("PASS", msg)

    def warn(self, msg: str) -> None:
        self.line("WARN", msg)

    def fail(self, msg: str) -> None:
        self.line("FAIL", msg)

    def section(self, title: str) -> None:
        print(f"\n{title}", flush=True)


def connect():
    kwargs = dict(user=os.environ.get("DB_USER", ""), password=os.environ.get("DB_PASSWORD", ""),
                  database=os.environ.get("DB_NAME", ""), charset="utf8mb4",
                  cursorclass=pymysql.cursors.DictCursor, connect_timeout=10)
    if os.environ.get("DB_UNIX_SOCKET"):
        kwargs["unix_socket"] = os.environ["DB_UNIX_SOCKET"]
    else:
        kwargs["host"] = os.environ.get("DB_HOST", "127.0.0.1")
        kwargs["port"] = int(os.environ.get("DB_PORT", "3306"))
    if os.environ.get("DB_SSL_CA"):
        kwargs["ssl"] = {"ca": os.environ["DB_SSL_CA"]}
    return pymysql.connect(**kwargs)


def q(conn, sql: str, args=None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def check_database(conn, rep: Report) -> dict:
    rep.section("1. Connection")
    info = q(conn, "SELECT VERSION() AS v, DATABASE() AS db, @@session.time_zone AS tz, @@sql_mode AS mode")[0]
    rep.ok(f"connected to {info['db']} on MySQL {info['v']}")
    major, minor, patch = (int("".join(c for c in p if c.isdigit()) or 0) for p in info["v"].split(".")[:3])
    if (major, minor, patch) < (8, 0, 16):
        rep.fail("MySQL 8.0.16 or later is needed for CHECK constraints")
    if "ONLY_FULL_GROUP_BY" not in info["mode"]:
        rep.warn("sql_mode lacks ONLY_FULL_GROUP_BY (fine, but it differs from MySQL's default)")

    rep.section("2. Tables and columns")
    cols = q(conn, "SELECT table_name AS t, column_name AS c, extra AS x FROM information_schema.columns "
                   "WHERE table_schema = DATABASE()")
    have: dict[str, dict[str, str]] = {}
    for r in cols:
        have.setdefault(r["t"], {})[r["c"]] = r["x"] or ""
    lower = {t.lower(): t for t in have}
    missing_tables = []
    for table, columns in EXPECTED.items():
        actual = have.get(table) or have.get(lower.get(table.lower(), ""), None)
        if actual is None:
            missing_tables.append(table)
            rep.fail(f"table {table} is missing")
            continue
        if table not in have:
            rep.warn(f"table {table} exists as {lower[table.lower()]} (case differs; Linux MySQL is case-sensitive)")
        gone = [c for c in columns if c not in actual]
        if gone:
            rep.fail(f"{table} is missing column(s): {', '.join(gone)}")
        else:
            rep.ok(f"{table}: all {len(columns)} columns present")
    for ref in AUTO_INCREMENT:
        table, col = ref.split(".")
        if table in have and col in have[table] and "auto_increment" not in have[table][col]:
            rep.fail(f"{ref} must be AUTO_INCREMENT; the app inserts rows without an id")

    rep.section("3. View and triggers")
    views = {r["t"] for r in q(conn, "SELECT table_name AS t FROM information_schema.views WHERE table_schema = DATABASE()")}
    if VIEW[0] not in views:
        rep.fail(f"view {VIEW[0]} is missing; risk scores and route analysis need it (database/views.sql)")
    else:
        try:
            q(conn, f"SELECT {', '.join(VIEW[1])} FROM {VIEW[0]} LIMIT 1")
            rep.ok(f"view {VIEW[0]} answers queries")
        except pymysql.MySQLError as exc:
            rep.fail(f"view {VIEW[0]} fails: {exc}")
    triggers = {r["t"] for r in q(conn, "SELECT trigger_name AS t FROM information_schema.triggers "
                                        "WHERE trigger_schema = DATABASE()")}
    for t in TRIGGERS:
        (rep.ok if t in triggers else rep.warn)(f"trigger {t} {'present' if t in triggers else 'missing (rule not enforced in the database)'}")
    if missing_tables:
        return {"usable": False}

    rep.section("4. Reference data")
    profiles = q(conn, "SELECT weather_group, light_group FROM ConditionProfile")
    combos = {(p["weather_group"], p["light_group"]) for p in profiles}
    wanted = {(w, l) for w in ("dry", "wet", "snow_ice", "low_visibility") for l in ("day", "dark")}
    if wanted - combos:
        rep.fail(f"ConditionProfile is missing: {sorted(wanted - combos)}")
    else:
        rep.ok("ConditionProfile has all 8 weather x light profiles")
    for table, col in (("WeatherCondition", "weather_group"), ("LightCondition", "light_group")):
        groups = {r["g"] for r in q(conn, f"SELECT DISTINCT {col} AS g FROM {table}")}
        (rep.ok if groups else rep.fail)(f"{table} groups: {sorted(groups) or 'none'}")
    n = q(conn, "SELECT COUNT(*) AS n FROM RoadClass")[0]["n"]
    (rep.ok if n else rep.fail)(f"RoadClass has {n} rows")

    rep.section("5. Data")
    counts = {t: q(conn, f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in EXPECTED}
    for t in ("Crash", "CrashSite", "Vehicle", "Person", "WeatherStation", "DailyWeather", "GridCell", "CellRiskScore",
              "AppUser", "SavedLocation", "CrashReport", "RouteRequest", "Subscription", "Alert"):
        print(f"        {t:<16} {counts[t]:>12,}")
    (rep.ok if counts["Crash"] else rep.fail)(f"{counts['Crash']:,} crashes loaded")
    if counts["Crash"] and not counts["CellRiskScore"]:
        rep.warn("CellRiskScore is empty; run `flask --app wsgi refresh-cell-counts` so risk scores reflect crashes")
    elif counts["CellRiskScore"]:
        rep.ok(f"CellRiskScore has {counts['CellRiskScore']:,} rows")
    if counts["Crash"] and not counts["DailyWeather"]:
        rep.warn("DailyWeather is empty; crash details and the weather breakdown will show no station readings")
    matched = q(conn, "SELECT AVG(weather_station_id IS NOT NULL) AS r FROM Crash")[0]["r"]
    if matched is not None:
        rep.ok(f"{float(matched):.1%} of crashes are matched to a weather station")
    years = [r["y"] for r in q(conn, "SELECT DISTINCT data_year AS y FROM Crash ORDER BY y")]
    if years:
        rep.ok(f"crash years: {', '.join(map(str, years))}")
    return {"usable": counts["Crash"] > 0}


def check_api(rep: Report, write: bool, admin: tuple[str, str] | None) -> None:
    from app import create_app

    app = create_app({"TESTING": True, "ROUTING_PROVIDER": "offline", "GEOCODER": "offline",
                      "WEATHER_PROVIDER": "offline", "JWT_SECRET": os.environ.get("JWT_SECRET") or "smoke-test"})
    c = app.test_client()

    def call(method: str, url: str, expect: int = 200, token: str | None = None, **kw):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = c.open(url, method=method, headers=headers, **kw)
        body = r.get_json(silent=True)
        if r.status_code != expect:
            msg = body.get("error", {}).get("message") if isinstance(body, dict) else r.data[:200]
            raise AssertionError(f"{method} {url} returned {r.status_code}, expected {expect}: {msg}")
        return body

    def step(label: str, fn):
        try:
            result = fn()
            rep.ok(label + (f": {result}" if isinstance(result, str) else ""))
            return True
        except Exception as exc:  # report and continue with the next check
            rep.fail(f"{label}: {exc}")
            if os.environ.get("SMOKE_DEBUG"):
                traceback.print_exc()
            return False

    rep.section("6. API, read-only (nothing is written)")
    ctx: dict = {}
    step("GET /api/health", lambda: call("GET", "/api/health")["database"])

    def lookups():
        body = call("GET", "/api/lookups")
        ctx["profiles"] = body["condition_profiles"]
        return f"{len(body['states'])} states, years {body['years']}"
    step("GET /api/lookups", lookups)

    def sample():
        with app.app_context():
            from app.db import query_one
            row = query_one("SELECT c.data_year, c.st_case, c.latitude, c.longitude, s.state_code, s.cell_id "
                            "FROM Crash c JOIN CrashSite s ON s.latitude = c.latitude AND s.longitude = c.longitude "
                            "ORDER BY c.fatalities DESC, c.st_case LIMIT 1")
        if not row:
            raise AssertionError("no crash to test with")
        ctx["crash"] = {k: (float(v) if k in ("latitude", "longitude") else v) for k, v in row.items()}
        return f"crash {row['data_year']}/{row['st_case']} in cell {row['cell_id']}"
    if not step("pick a sample crash", sample):
        return
    cr = ctx["crash"]
    box = {"min_lat": cr["latitude"] - 0.3, "max_lat": cr["latitude"] + 0.3,
           "min_lon": cr["longitude"] - 0.3, "max_lon": cr["longitude"] + 0.3}
    step("GET /api/crashes (by state)", lambda: f"{call('GET', '/api/crashes', query_string={'state_code': cr['state_code'], 'limit': 5})['total']:,} crashes")
    step("GET /api/crashes (by map area and conditions)",
         lambda: f"{call('GET', '/api/crashes', query_string={**box, 'light_group': 'dark'})['total']} crashes")
    step("GET /api/crashes/stats", lambda: f"{call('GET', '/api/crashes/stats', query_string=box)['crashes']} crashes")
    step("GET /api/crashes/<year>/<case>",
         lambda: call("GET", f"/api/crashes/{cr['data_year']}/{cr['st_case']}")["crash"]["weather"])
    step("GET /api/cells", lambda: f"{len(call('GET', '/api/cells', query_string={**box, 'condition_id': 1})['cells'])} cells")
    step("GET /api/cells/<cell>", lambda: f"{call('GET', '/api/cells/' + cr['cell_id'])['stats']['crashes']} crashes")
    step("GET /api/reports", lambda: f"{len(call('GET', '/api/reports')['reports'])} visible reports")
    trip = {"origin": {"lat": cr["latitude"], "lon": cr["longitude"]},
            "destination": {"lat": cr["latitude"] + 0.4, "lon": cr["longitude"] + 0.4},
            "conditions": {"weather": "dry", "time_of_day": "afternoon"}}
    step("POST /api/routes/analyze (guest, not saved)",
         lambda: "risk " + ", ".join(f"{o['option_type']} {o['risk_score']}" for o in call("POST", "/api/routes/analyze", json=trip)["options"]))

    if not write:
        return
    rep.section("7. API, write round trip (temporary accounts, deleted at the end)")
    stamp = int(time.time())
    users: list[str] = []
    try:
        def register(tag: str) -> str:
            body = call("POST", "/api/auth/register", 201, json={
                "email": f"smoke-{tag}-{stamp}@example.invalid", "password": "smoke-test-pw", "display_name": f"Smoke {tag}"})
            users.append(body["token"])
            return body["token"]
        a = register("a")
        b = register("b")
        rep.ok("registered two temporary accounts")
        step("PATCH /api/users/me", lambda: call("PATCH", "/api/users/me", token=a, json={"safety_weight": 0.8, "units": "metric"})["user"]["units"])
        loc = {}
        step("POST /api/locations", lambda: loc.update(call("POST", "/api/locations", 201, token=a, json={"label": "Smoke home", "lat": cr["latitude"], "lon": cr["longitude"]})["location"]) or loc["cell_id"])
        step("PUT /api/locations/<id>", lambda: call("PUT", f"/api/locations/{loc['location_id']}", token=a, json={"label": "Smoke house"})["location"]["label"])
        pid = ctx["profiles"][0]["condition_id"] if ctx.get("profiles") else 1
        step("POST /api/subscriptions", lambda: f"baseline {call('POST', '/api/subscriptions', 201, token=a, json={'location_id': loc['location_id'], 'condition_id': pid, 'alert_threshold': 10})['subscription']['baseline_score']}")
        rpt = {}
        step("POST /api/reports", lambda: rpt.update(call("POST", "/api/reports", 201, token=a, json={"lat": cr["latitude"], "lon": cr["longitude"], "reason": "Smoke test report"})["report"]) or rpt["cell_id"])
        step("PUT /api/reports/<id>", lambda: call("PUT", f"/api/reports/{rpt['report_id']}", token=a, json={"status": "resolved"})["report"]["status"])
        step("POST /api/reports/<id>/vote", lambda: "confirms " + str(call("POST", f"/api/reports/{rpt['report_id']}/vote", token=b, json={"vote": 1})["report"]["confirms"]))
        route = {}
        step("POST /api/routes/analyze (saved)", lambda: route.update(call("POST", "/api/routes/analyze", token=a, json=trip)) or f"route {route['route_id']}")
        step("PATCH /api/routes/<id> (choose an option; trigger check)", lambda: call("PATCH", f"/api/routes/{route['route_id']}", token=a, json={"chosen_option": "safest"})["route"]["chosen_option"])
        step("GET /api/routes", lambda: f"{len(call('GET', '/api/routes', token=a)['routes'])} saved route(s)")
        if admin:
            def moderate():
                tok = call("POST", "/api/auth/login", json={"email": admin[0], "password": admin[1]})["token"]
                return call("PATCH", f"/api/reports/{rpt['report_id']}/moderate", token=tok, json={"status": "removed"})["report"]["status"]
            step("PATCH /api/reports/<id>/moderate (admin)", moderate)
    finally:
        for tok in users:
            step("DELETE /api/users/me (cascades the test data)", lambda tok=tok: call("DELETE", "/api/users/me", 204, token=tok) or "deleted")
        with app.app_context():
            from app.db import query_one
            left = query_one("SELECT COUNT(*) AS n FROM AppUser WHERE email LIKE %s", (f"smoke-%-{stamp}@example.invalid",))["n"]
        (rep.ok if left == 0 else rep.fail)(f"{left} temporary account(s) left behind")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--write", action="store_true", help="also run a create/update/delete round trip")
    p.add_argument("--env-file", default=os.path.join(os.path.dirname(HERE), ".env"))
    p.add_argument("--admin-email")
    p.add_argument("--admin-password")
    args = p.parse_args()
    load_dotenv(args.env_file)

    rep = Report()
    print(f"Smoke test against {os.environ.get('DB_NAME')} at "
          f"{os.environ.get('DB_UNIX_SOCKET') or os.environ.get('DB_HOST', '127.0.0.1') + ':' + os.environ.get('DB_PORT', '3306')}")
    try:
        conn = connect()
    except pymysql.MySQLError as exc:
        print(f"  FAIL  cannot connect: {exc}")
        return 1
    try:
        state = check_database(conn, rep)
    finally:
        conn.close()
    if state["usable"]:
        admin = (args.admin_email, args.admin_password) if args.admin_email and args.admin_password else None
        check_api(rep, args.write, admin)
    else:
        rep.warn("skipping the API checks until the problems above are fixed")
    print(f"\n{rep.counts['PASS']} passed, {rep.counts['WARN']} warnings, {rep.counts['FAIL']} failed")
    return 1 if rep.counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
