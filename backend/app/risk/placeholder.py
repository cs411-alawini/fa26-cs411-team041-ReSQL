"""Placeholder risk model.

Until the team's ML model is ready, scores come from the CellRiskCurrent view defined in the
Stage 2 design (doc/stage2_database_design-p2.md, section 4.3; database/views.sql). No new
scoring logic lives here: this class only reads that view.
"""
from __future__ import annotations

from ..db import placeholders, query
from .base import CellScore, RiskModel

_CHUNK = 500


class Stage2ViewRiskModel(RiskModel):
    name = "stage2_view"
    is_placeholder = True

    def score_cells(self, cell_ids: list[str], condition_id: int) -> dict[str, CellScore]:
        unique = list(dict.fromkeys(cell_ids))
        out: dict[str, CellScore] = {}
        for i in range(0, len(unique), _CHUNK):
            chunk = unique[i:i + _CHUNK]
            rows = query(
                "SELECT cell_id, crash_count, fatality_count, recent_reports, risk_score "
                f"FROM CellRiskCurrent WHERE condition_id = %s AND cell_id IN ({placeholders(len(chunk))})",
                (condition_id, *chunk),
            )
            for r in rows:
                out[r["cell_id"]] = CellScore(
                    cell_id=r["cell_id"],
                    score=float(r["risk_score"] or 0),
                    crash_count=int(r["crash_count"]),
                    fatality_count=int(r["fatality_count"]),
                    recent_reports=int(r["recent_reports"]),
                )
        return out
