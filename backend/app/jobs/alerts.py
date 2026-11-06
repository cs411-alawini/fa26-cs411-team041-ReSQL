"""The alert job (Stage 2, section 2.6).

For each active subscription it compares the location's current risk score against the last
score the user was told about (latest alert, else the baseline) and sends an alert when the
change reaches the subscription's threshold.
"""
from __future__ import annotations

from ..db import execute, query, transaction
from ..geo import cell_for
from ..risk import get_risk_model

SQL = """
SELECT s.subscription_id, s.condition_id, s.alert_threshold, s.baseline_score, l.latitude, l.longitude,
       (SELECT a.risk_score_at_send FROM Alert a WHERE a.subscription_id = s.subscription_id
        ORDER BY a.sent_at DESC, a.alert_id DESC LIMIT 1) AS last_sent
FROM Subscription s
JOIN SavedLocation l ON l.location_id = s.location_id
WHERE s.is_active = TRUE
"""


def run_alert_job() -> dict:
    model = get_risk_model()
    subs = query(SQL)
    created = []
    with transaction():
        for s in subs:
            cell_id = cell_for(s["latitude"], s["longitude"])[0]
            current = model.score_cell(cell_id, s["condition_id"]).score
            previous = float(s["last_sent"] if s["last_sent"] is not None else s["baseline_score"])
            if abs(current - previous) >= float(s["alert_threshold"]):
                alert_id, _ = execute("INSERT INTO Alert (subscription_id, risk_score_at_send) VALUES (%s, %s)",
                                      (s["subscription_id"], round(current, 2)))
                created.append({"alert_id": alert_id, "subscription_id": s["subscription_id"],
                                "previous": previous, "current": round(current, 2)})
    return {"checked": len(subs), "alerts_created": len(created), "alerts": created}
