-- CellRiskCurrent from doc/stage2_database_design-p2.md section 4.3.
-- The application reads risk scores only through backend/app/risk, so this view can be
-- replaced by the ML model later without touching the API or the frontend.

CREATE OR REPLACE VIEW CellRiskCurrent AS
SELECT g.cell_id, p.condition_id,
       COALESCE(s.crash_count, 0)    AS crash_count,
       COALESCE(s.fatality_count, 0) AS fatality_count,
       COALESCE(r.recent_reports, 0) AS recent_reports,
       ROUND(100 * (1 - EXP(-(
             COALESCE(s.crash_count, 0) / y.years
               * p.national_serious_fatal_pct / b.avg_pct
           + 0.5 * COALESCE(r.recent_reports, 0)) / 2)), 2) AS risk_score
FROM GridCell g
CROSS JOIN ConditionProfile p
CROSS JOIN (SELECT GREATEST(COUNT(DISTINCT data_year), 1) AS years FROM Crash) y
CROSS JOIN (SELECT AVG(national_serious_fatal_pct) AS avg_pct
            FROM ConditionProfile) b
LEFT JOIN CellRiskScore s
       ON s.cell_id = g.cell_id AND s.condition_id = p.condition_id
LEFT JOIN (SELECT rc.cell_id, COUNT(*) AS recent_reports
           FROM ReportCell rc
           JOIN CrashReport cr ON cr.report_id = rc.report_id
           WHERE cr.status <> 'removed'
             AND cr.reported_at >= NOW() - INTERVAL 30 DAY
             AND (SELECT COALESCE(SUM(v.vote), 0) FROM ReportVote v
                  WHERE v.report_id = cr.report_id) >= 0
           GROUP BY rc.cell_id) r
       ON r.cell_id = g.cell_id
WHERE s.cell_id IS NOT NULL OR r.cell_id IS NOT NULL;
