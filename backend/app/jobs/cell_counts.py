"""The scoring job: per-cell crash and fatality counts under each condition profile.

Crashes whose weather or lighting is unknown have no profile and are not attributed (Stage 2,
section 2.5). database/loader/load_data.py runs the same statement after loading data.
"""
from __future__ import annotations

from ..db import execute, transaction

REFRESH_SQL = """
INSERT INTO CellRiskScore (cell_id, condition_id, crash_count, fatality_count, computed_at)
SELECT s.cell_id, p.condition_id, COUNT(*), SUM(c.fatalities), NOW()
FROM Crash c
JOIN CrashSite s ON s.latitude = c.latitude AND s.longitude = c.longitude
JOIN WeatherCondition w ON w.weather_code = c.weather_code
JOIN LightCondition l ON l.light_code = c.light_code
JOIN ConditionProfile p ON p.weather_group = w.weather_group AND p.light_group = l.light_group
GROUP BY s.cell_id, p.condition_id
"""


def refresh() -> int:
    with transaction():
        execute("DELETE FROM CellRiskScore")
        _, n = execute(REFRESH_SQL)
    return n
