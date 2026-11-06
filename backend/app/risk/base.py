"""The risk-model interface.

Everything in the app that needs a risk score goes through a RiskModel, so swapping the
current placeholder for the ML model means writing one class and setting RISK_MODEL.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

RISK_LEVELS = (  # (upper bound, label) on the 0-100 scale
    (25.0, "low"),
    (50.0, "moderate"),
    (75.0, "high"),
    (100.01, "very_high"),
)


def risk_level(score: float | None) -> str | None:
    if score is None:
        return None
    for bound, label in RISK_LEVELS:
        if score < bound:
            return label
    return "very_high"


@dataclass
class CellScore:
    cell_id: str
    score: float
    crash_count: int = 0
    fatality_count: int = 0
    recent_reports: int = 0

    @property
    def level(self) -> str | None:
        return risk_level(self.score)

    def to_dict(self) -> dict:
        return {**asdict(self), "level": self.level}


@dataclass
class RouteRisk:
    score: float
    cells: list[dict] = field(default_factory=list)  # [{cell_id, km, score, level, crash_count, ...}]

    @property
    def level(self) -> str | None:
        return risk_level(self.score)


class RiskModel(ABC):
    """A model that scores grid cells, 0 (safest) to 100, under one condition profile."""

    name = "base"
    #: True while the score is an interim stand-in for the ML model. Shown in the API and UI.
    is_placeholder = False

    @abstractmethod
    def score_cells(self, cell_ids: list[str], condition_id: int) -> dict[str, CellScore]:
        """Scores for the given cells. Cells with no history may be omitted; they score 0."""

    def score_cell(self, cell_id: str, condition_id: int) -> CellScore:
        return self.score_cells([cell_id], condition_id).get(cell_id) or CellScore(cell_id, 0.0)

    def score_route(self, cells_km: list[tuple[str, float]], condition_id: int) -> RouteRisk:
        """Distance-weighted mean of the scores of the cells a route passes through."""
        scores = self.score_cells([c for c, _ in cells_km], condition_id)
        total_km = sum(km for _, km in cells_km) or 1.0
        weighted = 0.0
        cells = []
        for cell_id, km in cells_km:
            cs = scores.get(cell_id) or CellScore(cell_id, 0.0)
            weighted += cs.score * km
            cells.append({**cs.to_dict(), "km": km})
        return RouteRisk(score=round(weighted / total_km, 2), cells=cells)
