"""Where the ML risk model plugs in (not implemented yet).

To switch the app over:
  1. Implement score_cells() below. It receives grid cell ids such as "401_-883" and a
     ConditionProfile.condition_id (1-8), and must return a CellScore with a 0-100 score
     for each cell it can score. Cells left out are treated as score 0.
  2. Load the trained model once in __init__ (for example from the path in RISK_MODEL_PATH).
  3. Start the backend with RISK_MODEL=ml.

Useful features already in the database, per cell and condition: CellRiskScore.crash_count and
fatality_count, ConditionProfile national baselines, recent CrashReport counts via ReportCell,
and the joined DailyWeather readings for each crash.
"""
from __future__ import annotations

import os

from .base import CellScore, RiskModel


class MLRiskModel(RiskModel):
    name = "ml"
    is_placeholder = False

    def __init__(self) -> None:
        self.model_path = os.environ.get("RISK_MODEL_PATH")

    def score_cells(self, cell_ids: list[str], condition_id: int) -> dict[str, CellScore]:
        raise NotImplementedError(
            "The ML risk model is not implemented yet. See backend/app/risk/ml.py, "
            "or set RISK_MODEL=stage2_view to use the placeholder."
        )
