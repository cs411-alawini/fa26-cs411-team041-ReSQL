import type { RiskLevel, WeatherGroup } from '../api/types';

export const RISK_COLORS: Record<RiskLevel, string> = {
  low: '#22a447',
  moderate: '#f5c518',
  high: '#f28c28',
  very_high: '#e5383b',
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  very_high: 'Very High',
};

export const WEATHER_LABELS: Record<string, string> = {
  dry: 'Clear / dry',
  wet: 'Rain',
  snow_ice: 'Snow or ice',
  low_visibility: 'Fog / low visibility',
  unknown: 'Unknown',
};

export const LIGHT_LABELS: Record<string, string> = { day: 'Daylight', dark: 'Dark', unknown: 'Unknown' };

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function riskColor(level: RiskLevel | null | undefined): string {
  return level ? RISK_COLORS[level] : '#94a3b8';
}

export function riskLabel(level: RiskLevel | null | undefined): string {
  return level ? RISK_LABELS[level] : 'Unknown';
}

export function conditionLabel(weather: WeatherGroup | string, light: string): string {
  return `${WEATHER_LABELS[weather] ?? weather} · ${LIGHT_LABELS[light] ?? light}`;
}

export function formatDuration(seconds: number): string {
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function formatDistance(meters: number, units: 'metric' | 'imperial' = 'imperial'): string {
  if (units === 'metric') {
    const km = meters / 1000;
    return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
  }
  const mi = meters / 1609.344;
  return `${mi < 10 ? mi.toFixed(1) : Math.round(mi)} mi`;
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? '—' : Math.round(score).toString();
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

export function formatHour(hour: number): string {
  if (hour === 99) return 'Unknown time';
  const suffix = hour < 12 ? 'AM' : 'PM';
  return `${hour % 12 === 0 ? 12 : hour % 12} ${suffix}`;
}

export function shortCoords(lat: number, lon: number): string {
  return `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
}

/**
 * Place names as stored in the data, shown in title case when they are all capitals
 * (the Cloud SQL County table keeps FARS's "CHAMPAIGN"; a local load has "Champaign").
 * Names that already have lower-case letters are shown unchanged.
 */
export function placeName(name: string): string {
  if (!name || /[a-z]/.test(name)) return name;
  return name
    .toLowerCase()
    .replace(/(^|[\s\-./'(])([a-z])/g, (_, sep: string, ch: string) => sep + ch.toUpperCase())
    .replace(/\bMc([a-z])/g, (_, ch: string) => `Mc${ch.toUpperCase()}`);
}
