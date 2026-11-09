"""Database-level rules from Stage 2 section 6: triggers, CHECK constraints, cascades, the risk view."""
from __future__ import annotations

import pymysql
import pytest

from tests.helpers import execute, scalar


def _user(db, email: str, role: str = "user") -> int:
    execute(db, "INSERT INTO AppUser (email, password_hash, display_name, role) VALUES (%s, 'x', 'T', %s)", (email, role))
    return scalar(db, "SELECT user_id FROM AppUser WHERE email = %s", (email,))


def _signal(db, sql: str, args=None) -> str:
    with pytest.raises(pymysql.err.OperationalError) as exc:
        execute(db, sql, args)
    db.rollback()
    return exc.value.args[1]


def test_only_admins_can_review_reports(db):
    author, plain = _user(db, "a@x.com"), _user(db, "p@x.com")
    execute(db, "INSERT INTO CrashReport (user_id, latitude, longitude, reason) VALUES (%s, 40.1, -88.2, 'x')", (author,))
    rid = scalar(db, "SELECT MAX(report_id) FROM CrashReport")
    msg = _signal(db, "UPDATE CrashReport SET reviewed_by = %s, reviewed_at = NOW() WHERE report_id = %s", (plain, rid))
    assert "admin" in msg


def test_removing_a_report_needs_reviewer(db):
    author, admin = _user(db, "a@x.com"), _user(db, "admin@x.com", "admin")
    execute(db, "INSERT INTO CrashReport (user_id, latitude, longitude, reason) VALUES (%s, 40.1, -88.2, 'x')", (author,))
    rid = scalar(db, "SELECT MAX(report_id) FROM CrashReport")
    assert "reviewed_by" in _signal(db, "UPDATE CrashReport SET status = 'removed' WHERE report_id = %s", (rid,))
    execute(db, "UPDATE CrashReport SET status = 'removed', reviewed_by = %s, reviewed_at = NOW() WHERE report_id = %s",
            (admin, rid))
    assert scalar(db, "SELECT status FROM CrashReport WHERE report_id = %s", (rid,)) == "removed"


def test_person_vehicle_must_exist(db):
    msg = _signal(db, "INSERT INTO Person VALUES (2024, 170001, 7, 1, 1, 4, 30, 3)")
    assert "vehicle" in msg
    execute(db, "INSERT INTO Person VALUES (2024, 170001, 0, 2, 5, 0, 40, 0)")   # non-motorist is fine
    execute(db, "DELETE FROM Person WHERE data_year = 2024 AND st_case = 170001 AND veh_no = 0 AND per_no = 2")


def test_chosen_route_option_must_have_been_offered(db):
    uid = _user(db, "r@x.com")
    execute(db, "INSERT INTO RouteRequest (user_id, origin_lat, origin_lon, dest_lat, dest_lon) VALUES (%s, 40, -88, 41, -87)", (uid,))
    rid = scalar(db, "SELECT MAX(route_id) FROM RouteRequest")
    assert "offered" in _signal(db, "UPDATE RouteRequest SET chosen_option = 'safest' WHERE route_id = %s", (rid,))
    execute(db, "INSERT INTO RouteOption VALUES (%s, 'safest', 600, 12.5)", (rid,))
    execute(db, "UPDATE RouteRequest SET chosen_option = 'safest' WHERE route_id = %s", (rid,))
    assert "NULL" in _signal(db, "INSERT INTO RouteRequest (user_id, origin_lat, origin_lon, dest_lat, dest_lon, "
                                 "chosen_option) VALUES (%s, 40, -88, 41, -87, 'fastest')", (uid,))


@pytest.mark.parametrize("sql", [
    "INSERT INTO AppUser (email, password_hash, display_name, role) VALUES ('z@x.com', 'x', 'Z', 'superuser')",
    "INSERT INTO AppUser (email, password_hash, display_name, units) VALUES ('z@x.com', 'x', 'Z', 'parsecs')",
    "INSERT INTO ConditionProfile VALUES (9, 'unknown', 'day', 1, 1.0)",
    "INSERT INTO SavedLocation (user_id, label, latitude, longitude) SELECT MIN(user_id), 'x', 95, 0 FROM AppUser",
])
def test_check_constraints(db, sql):
    _user(db, "c@x.com")
    with pytest.raises(pymysql.err.OperationalError) as exc:
        execute(db, sql)
    db.rollback()
    assert exc.value.args[0] == 3819          # ER_CHECK_CONSTRAINT_VIOLATED


def test_crash_date_must_match_data_year(db):
    with pytest.raises(pymysql.err.OperationalError):
        execute(db, "INSERT INTO Crash VALUES (2023, 1, '40.11060000', '-88.20730000', '2024-05-01', 1, 1, 1, 1, 1, "
                    "NULL, 1, 1, 1, 1)")
    db.rollback()


def test_unique_subscription_per_location_and_condition(db):
    uid = _user(db, "s@x.com")
    execute(db, "INSERT INTO SavedLocation (user_id, label, latitude, longitude) VALUES (%s, 'h', 40.1, -88.2)", (uid,))
    lid = scalar(db, "SELECT MAX(location_id) FROM SavedLocation")
    execute(db, "INSERT INTO Subscription (location_id, condition_id, alert_threshold, baseline_score) VALUES (%s, 1, 5, 0)", (lid,))
    with pytest.raises(pymysql.err.IntegrityError):
        execute(db, "INSERT INTO Subscription (location_id, condition_id, alert_threshold, baseline_score) VALUES (%s, 1, 9, 0)", (lid,))
    db.rollback()


def test_view_scores_crash_cells_and_report_only_cells(db):
    wet_dark = scalar(db, "SELECT risk_score FROM CellRiskCurrent WHERE cell_id = '401_-883' AND condition_id = 4")
    assert 0 < float(wet_dark) <= 100
    assert scalar(db, "SELECT COUNT(*) FROM CellRiskCurrent WHERE cell_id = '350_-1001'") == 0
    uid = _user(db, "v@x.com")
    execute(db, "INSERT INTO GridCell VALUES ('350_-1001', 35.0, -100.1)")
    execute(db, "INSERT INTO CrashReport (user_id, latitude, longitude, reason) VALUES (%s, 35.0001, -100.0001, 'x')", (uid,))
    execute(db, "INSERT INTO ReportCell VALUES ((SELECT MAX(report_id) FROM CrashReport), '350_-1001')")
    # one counting report: 100 * (1 - exp(-0.5 / 2)) = 22.12 for every condition
    assert float(scalar(db, "SELECT risk_score FROM CellRiskCurrent WHERE cell_id = '350_-1001' AND condition_id = 1")) == 22.12
    assert scalar(db, "SELECT COUNT(*) FROM CellRiskCurrent WHERE cell_id = '350_-1001'") == 8
