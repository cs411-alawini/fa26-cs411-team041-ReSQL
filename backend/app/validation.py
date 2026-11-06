"""Small input-validation helpers shared by the endpoints."""
from __future__ import annotations

import re
from typing import Any

from flask import request

from .errors import ApiError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WEATHER_GROUPS = ("dry", "wet", "snow_ice", "low_visibility")
LIGHT_GROUPS = ("day", "dark")


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return data


def require(data: dict, *fields: str) -> None:
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing:
        raise ApiError(400, f"Missing required field(s): {', '.join(missing)}", fields=missing)


def as_float(value: Any, name: str, lo: float | None = None, hi: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a number")
    if number != number or (lo is not None and number < lo) or (hi is not None and number > hi):
        raise ApiError(400, f"{name} must be between {lo} and {hi}")
    return number


def as_int(value: Any, name: str, lo: int | None = None, hi: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a whole number")
    if (lo is not None and number < lo) or (hi is not None and number > hi):
        raise ApiError(400, f"{name} must be between {lo} and {hi}")
    return number


def as_text(value: Any, name: str, max_len: int, min_len: int = 1) -> str:
    if not isinstance(value, str):
        raise ApiError(400, f"{name} must be text")
    text = value.strip()
    if len(text) < min_len:
        raise ApiError(400, f"{name} cannot be empty")
    if len(text) > max_len:
        raise ApiError(400, f"{name} must be at most {max_len} characters")
    return text


def latitude(value: Any, name: str = "latitude") -> float:
    return round(as_float(value, name, -90, 90), 6)


def longitude(value: Any, name: str = "longitude") -> float:
    return round(as_float(value, name, -180, 180), 6)


def point(data: Any, name: str) -> tuple[float, float]:
    if not isinstance(data, dict):
        raise ApiError(400, f"{name} must be an object with lat and lon")
    return latitude(data.get("lat"), f"{name}.lat"), longitude(data.get("lon"), f"{name}.lon")


def one_of(value: Any, name: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ApiError(400, f"{name} must be one of: {', '.join(allowed)}")
    return value


def arg_float(name: str, lo: float | None = None, hi: float | None = None) -> float | None:
    raw = request.args.get(name)
    return None if raw in (None, "") else as_float(raw, name, lo, hi)


def arg_int(name: str, lo: int | None = None, hi: int | None = None, default: int | None = None) -> int | None:
    raw = request.args.get(name)
    return default if raw in (None, "") else as_int(raw, name, lo, hi)


def arg_choice(name: str, allowed: tuple[str, ...]) -> str | None:
    raw = request.args.get(name)
    return None if raw in (None, "") else one_of(raw, name, allowed)


def bbox_args(required: bool = False) -> tuple[float, float, float, float] | None:
    """min_lat, min_lon, max_lat, max_lon from the query string."""
    values = [request.args.get(k) for k in ("min_lat", "min_lon", "max_lat", "max_lon")]
    if all(v in (None, "") for v in values):
        if required:
            raise ApiError(400, "min_lat, min_lon, max_lat and max_lon are required")
        return None
    min_lat = as_float(values[0], "min_lat", -90, 90)
    min_lon = as_float(values[1], "min_lon", -180, 180)
    max_lat = as_float(values[2], "max_lat", -90, 90)
    max_lon = as_float(values[3], "max_lon", -180, 180)
    if min_lat > max_lat or min_lon > max_lon:
        raise ApiError(400, "The bounding box minimums must not exceed its maximums")
    return min_lat, min_lon, max_lat, max_lon
