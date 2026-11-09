"""Settings, read from environment variables (and backend/.env when present)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


@dataclass
class Config:
    # Database. For Cloud SQL, run the Cloud SQL Auth Proxy and point DB_HOST at 127.0.0.1,
    # or set DB_UNIX_SOCKET=/cloudsql/<project>:<region>:<instance> on Cloud Run.
    DB_HOST: str = field(default_factory=lambda: os.environ.get("DB_HOST", "127.0.0.1"))
    DB_PORT: int = field(default_factory=lambda: int(os.environ.get("DB_PORT", "3306")))
    DB_USER: str = field(default_factory=lambda: os.environ.get("DB_USER", "resql"))
    DB_PASSWORD: str = field(default_factory=lambda: os.environ.get("DB_PASSWORD", ""))
    DB_NAME: str = field(default_factory=lambda: os.environ.get("DB_NAME", "resql"))
    DB_UNIX_SOCKET: str | None = field(default_factory=lambda: os.environ.get("DB_UNIX_SOCKET") or None)
    DB_SSL_CA: str | None = field(default_factory=lambda: os.environ.get("DB_SSL_CA") or None)

    # Auth
    JWT_SECRET: str = field(default_factory=lambda: os.environ.get("JWT_SECRET", "dev-only-change-me"))
    JWT_TTL_HOURS: int = field(default_factory=lambda: int(os.environ.get("JWT_TTL_HOURS", "168")))

    # External services. "offline" providers need no network and are used by the tests.
    ROUTING_PROVIDER: str = field(default_factory=lambda: os.environ.get("ROUTING_PROVIDER", "osrm"))
    OSRM_URL: str = field(default_factory=lambda: os.environ.get("OSRM_URL", "https://router.project-osrm.org"))
    GEOCODER: str = field(default_factory=lambda: os.environ.get("GEOCODER", "nominatim"))
    NOMINATIM_URL: str = field(default_factory=lambda: os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org"))
    WEATHER_PROVIDER: str = field(default_factory=lambda: os.environ.get("WEATHER_PROVIDER", "open-meteo"))
    OPEN_METEO_URL: str = field(default_factory=lambda: os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com"))
    HTTP_USER_AGENT: str = field(default_factory=lambda: os.environ.get(
        "HTTP_USER_AGENT", "TrafficSafetyRiskAnalyzer/1.0 (CS411 team041 ReSQL)"))
    HTTP_TIMEOUT_S: float = field(default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT_S", "8")))
    # When an online provider fails, fall back to the offline one instead of returning an error.
    PROVIDER_FALLBACK: bool = field(default_factory=lambda: _bool("PROVIDER_FALLBACK", True))

    # Risk scoring. "stage2_view" reads the CellRiskCurrent view; replace with the ML model later.
    RISK_MODEL: str = field(default_factory=lambda: os.environ.get("RISK_MODEL", "stage2_view"))

    CORS_ORIGINS: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:5173"))
    # Serve the built frontend (frontend/dist) from Flask, for single-server deployments.
    FRONTEND_DIST: str | None = field(default_factory=lambda: os.environ.get("FRONTEND_DIST") or None)

    TESTING: bool = False

    def to_flask(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
