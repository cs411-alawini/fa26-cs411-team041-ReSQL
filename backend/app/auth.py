"""Password hashing, JWT tokens and the decorators that protect endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable

import jwt
from flask import current_app, g, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import query_one
from .errors import ApiError

USER_COLUMNS = "user_id, email, display_name, role, safety_weight, units, created_at"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def create_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["user_id"]),
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=current_app.config["JWT_TTL_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _user_from_request() -> dict | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer "):].strip()
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "Your session has expired. Please sign in again.", code="token_expired")
    except jwt.InvalidTokenError:
        raise ApiError(401, "Invalid authentication token", code="invalid_token")
    user = query_one(f"SELECT {USER_COLUMNS} FROM AppUser WHERE user_id = %s", (int(payload["sub"]),))
    if user is None:
        raise ApiError(401, "This account no longer exists", code="invalid_token")
    return user


def login_required(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        if g.user is None:
            raise ApiError(401, "Please sign in to do that")
        return fn(*args, **kwargs)
    return wrapper


def optional_auth(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        g.user = _user_from_request()
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn: Callable) -> Callable:
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user["role"] != "admin":
            raise ApiError(403, "Only admins can do that")
        return fn(*args, **kwargs)
    return wrapper


def current_user() -> dict | None:
    return g.get("user")
