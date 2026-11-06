import type { AnalyzeResponse, Report } from '../api/types';

const geometry: [number, number][] = [[40.1164, -88.2434], [40.3, -88.6], [40.4842, -88.9937]];

export const analyzeResponse: AnalyzeResponse = {
  route_id: 42,
  provider: 'osrm',
  provider_fallback: false,
  risk_model: { name: 'stage2_view', placeholder: true },
  safety_weight: 0.5,
  conditions: {
    weather_group: 'wet', light_group: 'dark', condition_id: 4, description: 'Rain', temperature_c: null,
    source: 'selected', time_of_day: 'night', hours: [21, 5], months: [12, 1, 2],
  },
  routes: [
    {
      index: 0, summary: 'I-74', distance_m: 80467, duration_s: 3300, geometry, risk_score: 62.4, risk_level: 'high',
      cells: [{ cell_id: '401_-883', km: 3.2, score: 76.9, level: 'very_high', crash_count: 2, fatality_count: 3, recent_reports: 0 }],
      stats: {
        crashes: 12, fatalities: 14,
        factors: [
          { key: 'weather', label: 'Crashes in rainy weather', percent: 25 },
          { key: 'time', label: 'Crashes at this time of day', percent: 50 },
          { key: 'road', label: 'On Interstate roads', percent: 40 },
          { key: 'vehicle', label: 'Vehicles speeding-related', percent: 30 },
        ],
        by_month: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, crashes: i % 3 })),
        by_hour: Array.from({ length: 24 }, (_, h) => ({ hour: h, crashes: h % 2 })),
      },
    },
    {
      index: 1, summary: 'US-150', distance_m: 88000, duration_s: 4200, geometry, risk_score: 20.1, risk_level: 'low',
      cells: [],
      stats: {
        crashes: 3, fatalities: 3,
        factors: [
          { key: 'weather', label: 'Crashes in rainy weather', percent: 0 },
          { key: 'time', label: 'Crashes at this time of day', percent: 33.3 },
          { key: 'road', label: 'On Minor Arterial roads', percent: 66.7 },
          { key: 'vehicle', label: 'Vehicles speeding-related', percent: null },
        ],
        by_month: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, crashes: 0 })),
        by_hour: Array.from({ length: 24 }, (_, h) => ({ hour: h, crashes: 0 })),
      },
    },
  ],
  options: [
    { option_type: 'fastest', route_index: 0, distance_m: 80467, duration_s: 3300, risk_score: 62.4, risk_level: 'high' },
    { option_type: 'safest', route_index: 1, distance_m: 88000, duration_s: 4200, risk_score: 20.1, risk_level: 'low' },
    { option_type: 'balanced', route_index: 1, distance_m: 88000, duration_s: 4200, risk_score: 20.1, risk_level: 'low' },
  ],
  recommended: 'balanced',
};

export function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    report_id: 1, user_id: 99, author: 'Adhi', latitude: 40.11, longitude: -88.21, reason: 'Black ice',
    status: 'active', reported_at: '2026-11-04T21:58:00Z', reviewed_by: null, reviewed_at: null, cell_id: '401_-883',
    confirms: 1, flags: 0, my_vote: null, counts_toward_risk: true, ...overrides,
  };
}
