"""Risk scoring. Use get_risk_model() everywhere; never query scores directly."""
from __future__ import annotations

from flask import current_app

from .base import CellScore, RiskModel, RouteRisk, risk_level
from .ml import MLRiskModel
from .placeholder import Stage2ViewRiskModel

_MODELS = {
    "stage2_view": Stage2ViewRiskModel,
    "ml": MLRiskModel,
}


def get_risk_model() -> RiskModel:
    name = current_app.config.get("RISK_MODEL", "stage2_view")
    ext = current_app.extensions.setdefault("risk_models", {})
    if name not in ext:
        if name not in _MODELS:
            raise RuntimeError(f"Unknown RISK_MODEL {name!r}; choose one of {sorted(_MODELS)}")
        ext[name] = _MODELS[name]()
    return ext[name]


__all__ = ["CellScore", "RiskModel", "RouteRisk", "get_risk_model", "risk_level"]
