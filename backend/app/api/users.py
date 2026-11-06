"""Accounts: sign-up, sign-in, profile and preferences, account deletion, admin role changes."""
from __future__ import annotations

import pymysql
from flask import Blueprint, g, jsonify

from ..auth import (USER_COLUMNS, admin_required, create_token, hash_password, login_required,
                    verify_password)
from ..db import execute, query_one, transaction
from ..errors import ApiError, not_found
from ..validation import EMAIL_RE, as_float, as_text, json_body, one_of, require

bp = Blueprint("users", __name__)


def _public(user: dict) -> dict:
    return {k: user[k] for k in ("user_id", "email", "display_name", "role", "safety_weight", "units", "created_at")}


@bp.post("/auth/register")
def register():
    data = json_body()
    require(data, "email", "password", "display_name")
    email = as_text(data["email"], "email", 120).lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, "Enter a valid email address")
    password = data["password"]
    if not isinstance(password, str) or len(password) < 8:
        raise ApiError(400, "Password must be at least 8 characters")
    name = as_text(data["display_name"], "display_name", 60)
    try:
        with transaction():
            user_id, _ = execute("INSERT INTO AppUser (email, password_hash, display_name) VALUES (%s, %s, %s)",
                                 (email, hash_password(password), name))
    except pymysql.err.IntegrityError as exc:
        if exc.args and exc.args[0] == 1062:
            raise ApiError(409, "An account with that email already exists", code="email_taken")
        raise
    user = query_one(f"SELECT {USER_COLUMNS} FROM AppUser WHERE user_id = %s", (user_id,))
    return jsonify({"token": create_token(user), "user": _public(user)}), 201


@bp.post("/auth/login")
def login():
    data = json_body()
    require(data, "email", "password")
    email = str(data["email"]).strip().lower()
    row = query_one(f"SELECT {USER_COLUMNS}, password_hash FROM AppUser WHERE email = %s", (email,))
    if row is None or not verify_password(row["password_hash"], str(data["password"])):
        raise ApiError(401, "Incorrect email or password", code="bad_credentials")
    return jsonify({"token": create_token(row), "user": _public(row)})


@bp.get("/auth/me")
@login_required
def me():
    return jsonify({"user": _public(g.user)})


@bp.get("/users/me")
@login_required
def get_profile():
    return jsonify({"user": _public(g.user)})


@bp.patch("/users/me")
@login_required
def update_profile():
    data = json_body()
    sets, params = [], []
    if "display_name" in data:
        sets.append("display_name = %s")
        params.append(as_text(data["display_name"], "display_name", 60))
    if "safety_weight" in data:
        sets.append("safety_weight = %s")
        params.append(round(as_float(data["safety_weight"], "safety_weight", 0, 1), 2))
    if "units" in data:
        sets.append("units = %s")
        params.append(one_of(data["units"], "units", ("metric", "imperial")))
    if "password" in data:
        if not isinstance(data["password"], str) or len(data["password"]) < 8:
            raise ApiError(400, "Password must be at least 8 characters")
        current = data.get("current_password")
        row = query_one("SELECT password_hash FROM AppUser WHERE user_id = %s", (g.user["user_id"],))
        if not isinstance(current, str) or not verify_password(row["password_hash"], current):
            raise ApiError(403, "Current password is incorrect", code="bad_credentials")
        sets.append("password_hash = %s")
        params.append(hash_password(data["password"]))
    if not sets:
        raise ApiError(400, "Nothing to update")
    with transaction():
        execute(f"UPDATE AppUser SET {', '.join(sets)} WHERE user_id = %s", (*params, g.user["user_id"]))
    user = query_one(f"SELECT {USER_COLUMNS} FROM AppUser WHERE user_id = %s", (g.user["user_id"],))
    return jsonify({"user": _public(user)})


@bp.delete("/users/me")
@login_required
def delete_account():
    # Delete rules (Stage 2, section 6.4): locations, subscriptions, alerts, own reports, votes and
    # route history cascade; reports this user reviewed keep the row with reviewed_by set to NULL.
    with transaction():
        execute("DELETE FROM AppUser WHERE user_id = %s", (g.user["user_id"],))
    return "", 204


@bp.patch("/users/<int:user_id>/role")
@admin_required
def set_role(user_id: int):
    role = one_of(json_body().get("role"), "role", ("user", "admin"))
    if user_id == g.user["user_id"] and role != "admin":
        raise ApiError(400, "You cannot remove your own admin role")
    with transaction():
        _, n = execute("UPDATE AppUser SET role = %s WHERE user_id = %s", (role, user_id))
    if n == 0 and query_one("SELECT 1 FROM AppUser WHERE user_id = %s", (user_id,)) is None:
        raise not_found("User")
    user = query_one(f"SELECT {USER_COLUMNS} FROM AppUser WHERE user_id = %s", (user_id,))
    return jsonify({"user": _public(user)})
