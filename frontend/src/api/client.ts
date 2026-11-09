// Fetch wrapper for the Flask API. Every backend error arrives as {"error": {"code", "message"}}.
import type {
  Alert, AnalyzeResponse, AuthResponse, CrashDetail, CrashSearchResponse, CrashStats, Lookups, Place,
  Report, ResolvedConditions, RouteConditionsInput, RouteHistoryItem, SavedLocation, Subscription, User,
} from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';
const TOKEN_KEY = 'tsra.token';

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

let token: string | null = readToken();
let onUnauthorized: (() => void) | null = null;

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(value: string | null): void {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: keep the token in memory only */
  }
}

export function getToken(): string | null {
  return token;
}

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn;
}

type Query = Record<string, string | number | boolean | null | undefined>;

function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${withQuery(path, query)}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'network', 'Cannot reach the server. Check that the backend is running.');
  }
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | null)?.error;
    if (res.status === 401 && token && err?.code !== 'bad_credentials') onUnauthorized?.();
    throw new ApiError(res.status, err?.code ?? 'error', err?.message ?? `Request failed (${res.status})`);
  }
  return data as T;
}

export const api = {
  // accounts
  register: (email: string, password: string, display_name: string) =>
    request<AuthResponse>('POST', '/auth/register', { email, password, display_name }),
  login: (email: string, password: string) => request<AuthResponse>('POST', '/auth/login', { email, password }),
  me: () => request<{ user: User }>('GET', '/auth/me'),
  updateProfile: (changes: Partial<Pick<User, 'display_name' | 'safety_weight' | 'units'>> & {
    password?: string; current_password?: string;
  }) => request<{ user: User }>('PATCH', '/users/me', changes),
  deleteAccount: () => request<void>('DELETE', '/users/me'),

  // reference data and helpers
  health: () => request<{ status: string; risk_model: { name: string; placeholder: boolean } }>('GET', '/health'),
  lookups: () => request<Lookups>('GET', '/lookups'),
  counties: (stateCode: number) =>
    request<{ counties: { county_code: number; county_name: string }[] }>('GET', `/states/${stateCode}/counties`),
  geocode: (q: string) => request<{ results: Place[]; source: string }>('GET', '/geocode', undefined, { q }),
  currentConditions: (lat: number, lon: number) =>
    request<ResolvedConditions>('GET', '/conditions/current', undefined, { lat, lon }),

  // route analysis
  analyzeRoute: (origin: Place, destination: Place, conditions: RouteConditionsInput, safety_weight?: number) =>
    request<AnalyzeResponse>('POST', '/routes/analyze', {
      origin: { lat: origin.lat, lon: origin.lon }, destination: { lat: destination.lat, lon: destination.lon },
      conditions, ...(safety_weight === undefined ? {} : { safety_weight }),
    }),
  routeHistory: () => request<{ routes: RouteHistoryItem[] }>('GET', '/routes'),
  chooseRouteOption: (routeId: number, chosen_option: string | null) =>
    request<{ route: RouteHistoryItem }>('PATCH', `/routes/${routeId}`, { chosen_option }),
  deleteRoute: (routeId: number) => request<void>('DELETE', `/routes/${routeId}`),

  // search & lookup
  searchCrashes: (query: Query) => request<CrashSearchResponse>('GET', '/crashes', undefined, query),
  crashStats: (query: Query) => request<CrashStats>('GET', '/crashes/stats', undefined, query),
  crashDetail: (year: number, stCase: number) => request<CrashDetail>('GET', `/crashes/${year}/${stCase}`),

  // saved locations
  locations: () => request<{ locations: SavedLocation[] }>('GET', '/locations'),
  createLocation: (label: string, lat: number, lon: number) =>
    request<{ location: SavedLocation }>('POST', '/locations', { label, lat, lon }),
  updateLocation: (id: number, changes: { label?: string; lat?: number; lon?: number }) =>
    request<{ location: SavedLocation }>('PUT', `/locations/${id}`, changes),
  deleteLocation: (id: number) => request<void>('DELETE', `/locations/${id}`),

  // community reports
  reports: (query?: Query) => request<{ reports: Report[] }>('GET', '/reports', undefined, query),
  createReport: (lat: number, lon: number, reason: string) =>
    request<{ report: Report }>('POST', '/reports', { lat, lon, reason }),
  updateReport: (id: number, changes: { reason?: string; status?: 'active' | 'resolved'; lat?: number; lon?: number }) =>
    request<{ report: Report }>('PUT', `/reports/${id}`, changes),
  deleteReport: (id: number) => request<void>('DELETE', `/reports/${id}`),
  vote: (id: number, vote: 1 | -1) => request<{ report: Report }>('POST', `/reports/${id}/vote`, { vote }),
  unvote: (id: number) => request<{ report: Report }>('DELETE', `/reports/${id}/vote`),
  moderate: (id: number, status: 'active' | 'resolved' | 'removed') =>
    request<{ report: Report }>('PATCH', `/reports/${id}/moderate`, { status }),

  // subscriptions and alerts
  subscriptions: () => request<{ subscriptions: Subscription[] }>('GET', '/subscriptions'),
  createSubscription: (location_id: number, condition_id: number, alert_threshold: number) =>
    request<{ subscription: Subscription }>('POST', '/subscriptions', { location_id, condition_id, alert_threshold }),
  updateSubscription: (id: number, changes: { alert_threshold?: number; is_active?: boolean }) =>
    request<{ subscription: Subscription }>('PATCH', `/subscriptions/${id}`, changes),
  deleteSubscription: (id: number) => request<void>('DELETE', `/subscriptions/${id}`),
  alerts: () => request<{ alerts: Alert[] }>('GET', '/alerts'),
  runAlerts: () => request<{ checked: number; alerts_created: number }>('POST', '/alerts/run'),
};
