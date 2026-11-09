"""Accounts, authentication, preferences and account deletion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from tests.helpers import execute, scalar


def test_health_and_unknown_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["risk_model"] == {"name": "stage2_view", "placeholder": True}
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"


def test_register_login_and_me(api):
    user = api.register()
    assert user["user"]["role"] == "user" and user["user"]["safety_weight"] == 0.5
    assert user["user"]["units"] == "imperial"
    r = api.client.post("/api/auth/login", json={"email": "VINAY@example.com", "password": "password123"})
    assert r.status_code == 200 and r.get_json()["user"]["email"] == "vinay@example.com"
    me = api.call("GET", "/api/auth/me", user)
    assert me.get_json()["user"]["display_name"] == "Vinay"
    assert "password_hash" not in me.get_json()["user"]


def test_register_validation(api):
    c = api.client
    assert c.post("/api/auth/register", json={"email": "x", "password": "password123", "display_name": "X"}).status_code == 400
    assert c.post("/api/auth/register", json={"email": "x@y.com", "password": "short", "display_name": "X"}).status_code == 400
    assert c.post("/api/auth/register", json={"email": "x@y.com", "password": "password123"}).status_code == 400
    assert c.post("/api/auth/register", data="not json", content_type="text/plain").status_code == 400


def test_duplicate_email(api):
    api.register()
    r = api.client.post("/api/auth/register",
                        json={"email": "vinay@example.com", "password": "password123", "display_name": "Again"})
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "email_taken"


def test_wrong_password(api):
    api.register()
    r = api.client.post("/api/auth/login", json={"email": "vinay@example.com", "password": "nope-nope"})
    assert r.status_code == 401


def test_token_problems(api):
    assert api.client.get("/api/auth/me").status_code == 401
    assert api.client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    user = api.register()
    expired = jwt.encode({"sub": str(user["user"]["user_id"]), "role": "user",
                          "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, "test-secret", algorithm="HS256")
    r = api.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.get_json()["error"]["code"] == "token_expired"


def test_update_preferences(api):
    user = api.register()
    r = api.call("PATCH", "/api/users/me", user, json={"safety_weight": 0.8, "units": "metric", "display_name": "V"})
    assert r.status_code == 200
    updated = r.get_json()["user"]
    assert (updated["safety_weight"], updated["units"], updated["display_name"]) == (0.8, "metric", "V")
    assert api.call("PATCH", "/api/users/me", user, json={"safety_weight": 1.5}).status_code == 400
    assert api.call("PATCH", "/api/users/me", user, json={"units": "furlongs"}).status_code == 400
    assert api.call("PATCH", "/api/users/me", user, json={}).status_code == 400


def test_change_password(api):
    user = api.register()
    r = api.call("PATCH", "/api/users/me", user, json={"password": "newpassword1", "current_password": "wrong-one"})
    assert r.status_code == 403
    r = api.call("PATCH", "/api/users/me", user, json={"password": "newpassword1", "current_password": "password123"})
    assert r.status_code == 200
    assert api.client.post("/api/auth/login", json={"email": "vinay@example.com", "password": "newpassword1"}).status_code == 200


def test_delete_account_follows_delete_rules(api, db):
    admin = api.register("admin@example.com", admin=True)
    user = api.register("user@example.com")
    other = api.register("other@example.com")
    loc = api.call("POST", "/api/locations", user, json={"label": "Home", "lat": 40.11, "lon": -88.21}).get_json()
    api.call("POST", "/api/subscriptions", user,
             json={"location_id": loc["location"]["location_id"], "condition_id": 1, "alert_threshold": 5})
    mine = api.call("POST", "/api/reports", user, json={"lat": 40.11, "lon": -88.21, "reason": "Ice"}).get_json()
    theirs = api.call("POST", "/api/reports", other, json={"lat": 40.12, "lon": -88.22, "reason": "Debris"}).get_json()
    api.call("POST", f"/api/reports/{theirs['report']['report_id']}/vote", user, json={"vote": 1})
    api.call("POST", "/api/routes/analyze", user, json={"origin": {"lat": 40.11, "lon": -88.24},
                                                        "destination": {"lat": 40.2, "lon": -88.2}})
    # the admin reviews a report and then deletes their own account
    api.call("PATCH", f"/api/reports/{theirs['report']['report_id']}/moderate", admin, json={"status": "resolved"})

    assert api.call("DELETE", "/api/users/me", user).status_code == 204
    uid = user["user"]["user_id"]
    for table in ("SavedLocation", "CrashReport", "ReportVote", "RouteRequest"):
        assert scalar(db, f"SELECT COUNT(*) FROM {table} WHERE user_id = %s", (uid,)) == 0
    assert scalar(db, "SELECT COUNT(*) FROM Subscription") == 0
    assert scalar(db, "SELECT COUNT(*) FROM CrashReport WHERE report_id = %s", (mine["report"]["report_id"],)) == 0

    assert api.call("DELETE", "/api/users/me", admin).status_code == 204
    row_reviewer = scalar(db, "SELECT reviewed_by FROM CrashReport WHERE report_id = %s", (theirs["report"]["report_id"],))
    reviewed_at = scalar(db, "SELECT reviewed_at FROM CrashReport WHERE report_id = %s", (theirs["report"]["report_id"],))
    assert row_reviewer is None and reviewed_at is not None   # SET NULL, review time kept
    assert api.call("GET", "/api/auth/me", user).status_code == 401


def test_admin_role_management(api):
    admin = api.register("admin@example.com", admin=True)
    user = api.register("user@example.com")
    uid = user["user"]["user_id"]
    assert api.call("PATCH", f"/api/users/{uid}/role", user, json={"role": "admin"}).status_code == 403
    r = api.call("PATCH", f"/api/users/{uid}/role", admin, json={"role": "admin"})
    assert r.status_code == 200 and r.get_json()["user"]["role"] == "admin"
    assert api.call("PATCH", "/api/users/99999/role", admin, json={"role": "admin"}).status_code == 404
    assert api.call("PATCH", f"/api/users/{admin['user']['user_id']}/role", admin, json={"role": "user"}).status_code == 400
    assert api.call("PATCH", f"/api/users/{uid}/role", admin, json={"role": "boss"}).status_code == 400


def test_database_check_constraint_is_enforced(db):
    import pymysql
    import pytest
    with pytest.raises(pymysql.err.OperationalError):
        execute(db, "INSERT INTO AppUser (email, password_hash, display_name, safety_weight) VALUES ('c@d.e', 'x', 'C', 2)")
    db.rollback()
