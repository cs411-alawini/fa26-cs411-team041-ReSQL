"""Turn the Route Analyzer's condition inputs into a ConditionProfile."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import query_one
from ..errors import ApiError
from .crash_stats import TIME_OF_DAY, months_for
from .weather import current_conditions

WEATHER_CHOICES = ("auto", "dry", "wet", "snow_ice", "low_visibility")
TIME_CHOICES = ("now", *TIME_OF_DAY)
WEATHER_LABELS = {"dry": "Clear", "wet": "Rain", "snow_ice": "Snow or ice", "low_visibility": "Fog / low visibility"}


def profile_id(weather_group: str, light_group: str) -> int:
    row = query_one("SELECT condition_id FROM ConditionProfile WHERE weather_group = %s AND light_group = %s",
                    (weather_group, light_group))
    if row is None:
        raise ApiError(500, "ConditionProfile is missing a row for this condition", code="missing_profile")
    return int(row["condition_id"])


def resolve(conditions: dict[str, Any] | None, lat: float, lon: float) -> dict:
    conditions = conditions or {}
    weather = conditions.get("weather", "auto") or "auto"
    time_of_day = conditions.get("time_of_day", "now") or "now"
    if weather not in WEATHER_CHOICES:
        raise ApiError(400, f"conditions.weather must be one of: {', '.join(WEATHER_CHOICES)}")
    if time_of_day not in TIME_CHOICES:
        raise ApiError(400, f"conditions.time_of_day must be one of: {', '.join(TIME_CHOICES)}")
    months = months_for(conditions.get("month"), conditions.get("season"))

    live = None
    if weather == "auto":
        live = current_conditions(lat, lon)
        weather_group = live["weather_group"]
        description = live["description"]
    else:
        weather_group = weather
        description = WEATHER_LABELS[weather]

    if time_of_day == "now":
        hour = conditions.get("hour")
        if hour is None:
            hour = datetime.now().hour
        try:
            hour = int(hour)
        except (TypeError, ValueError):
            raise ApiError(400, "conditions.hour must be 0-23")
        if not 0 <= hour <= 23:
            raise ApiError(400, "conditions.hour must be 0-23")
        light_group = live["light_group"] if live else ("day" if 6 <= hour < 18 else "dark")
        hours = None
    else:
        hours = TIME_OF_DAY[time_of_day]
        light_group = "day" if time_of_day in ("morning", "afternoon") else "dark"

    return {
        "weather_group": weather_group,
        "light_group": light_group,
        "condition_id": profile_id(weather_group, light_group),
        "description": description,
        "temperature_c": live["temperature_c"] if live else None,
        "source": live["source"] if live else "selected",
        "time_of_day": time_of_day,
        "hours": list(hours) if hours else None,
        "months": list(months) if months else None,
    }
