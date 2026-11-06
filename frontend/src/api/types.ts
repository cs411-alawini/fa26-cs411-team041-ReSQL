// Shapes returned by the Flask API (backend/app/api).

export type WeatherGroup = 'dry' | 'wet' | 'snow_ice' | 'low_visibility';
export type LightGroup = 'day' | 'dark';
export type RiskLevel = 'low' | 'moderate' | 'high' | 'very_high';
export type OptionType = 'fastest' | 'safest' | 'balanced';
export type TimeOfDay = 'now' | 'morning' | 'afternoon' | 'evening' | 'night';
export type Season = 'winter' | 'spring' | 'summer' | 'fall';

export interface User {
  user_id: number;
  email: string;
  display_name: string;
  role: 'user' | 'admin';
  safety_weight: number;
  units: 'metric' | 'imperial';
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface Place {
  label: string;
  lat: number;
  lon: number;
  source?: string;
}

export interface Lookups {
  weather_conditions: { weather_code: number; description: string; weather_group: string }[];
  light_conditions: { light_code: number; description: string; light_group: string }[];
  road_classes: { func_sys_code: number; description: string }[];
  condition_profiles: ConditionProfile[];
  states: { state_code: number; state_name: string }[];
  years: number[];
}

export interface ConditionProfile {
  condition_id: number;
  weather_group: WeatherGroup;
  light_group: LightGroup;
  national_est_crashes: number;
  national_serious_fatal_pct: number;
}

export interface RouteConditionsInput {
  weather: 'auto' | WeatherGroup;
  time_of_day: TimeOfDay;
  hour?: number;
  month?: number | null;
  season?: Season | null;
}

export interface ResolvedConditions {
  weather_group: WeatherGroup;
  light_group: LightGroup;
  condition_id: number;
  description: string;
  temperature_c: number | null;
  source: string;
  time_of_day: TimeOfDay;
  hours: [number, number] | null;
  months: number[] | null;
}

export interface RouteCell {
  cell_id: string;
  km: number;
  score: number;
  level: RiskLevel | null;
  crash_count: number;
  fatality_count: number;
  recent_reports: number;
}

export interface RiskFactor {
  key: 'weather' | 'time' | 'road' | 'vehicle';
  label: string;
  percent: number | null;
}

export interface MonthCount { month: number; crashes: number }
export interface HourCount { hour: number; crashes: number }

export interface StationWeather {
  crashes_with_station: number;
  on_wet_days: number;
  on_snow_days: number;
  avg_temp_max_c: number | null;
}

export interface CorridorStats {
  crashes: number;
  fatalities: number;
  factors: RiskFactor[];
  by_month: MonthCount[];
  by_hour: HourCount[];
  station_weather?: StationWeather;
}

export interface AnalyzedRoute {
  index: number;
  summary: string;
  distance_m: number;
  duration_s: number;
  geometry: [number, number][];
  risk_score: number;
  risk_level: RiskLevel | null;
  cells: RouteCell[];
  stats?: CorridorStats;
}

export interface RouteOptionSummary {
  option_type: OptionType;
  route_index: number;
  distance_m: number;
  duration_s: number;
  risk_score: number;
  risk_level: RiskLevel | null;
}

export interface RiskModelInfo {
  name: string;
  placeholder: boolean;
}

export interface AnalyzeResponse {
  route_id: number | null;
  provider: string;
  provider_fallback: boolean;
  risk_model: RiskModelInfo;
  safety_weight: number;
  conditions: ResolvedConditions;
  routes: AnalyzedRoute[];
  options: RouteOptionSummary[];
  recommended: OptionType;
}

export interface RouteHistoryItem {
  route_id: number;
  origin_lat: number;
  origin_lon: number;
  dest_lat: number;
  dest_lon: number;
  chosen_option: OptionType | null;
  requested_at: string;
  options: { option_type: OptionType; travel_time_s: number; risk_score: number; risk_level: RiskLevel | null }[];
}

export interface SavedLocation {
  location_id: number;
  label: string;
  latitude: number;
  longitude: number;
  created_at: string;
  subscriptions: number;
  cell_id: string;
}

export interface Report {
  report_id: number;
  user_id: number;
  author: string;
  latitude: number;
  longitude: number;
  reason: string;
  status: 'active' | 'resolved' | 'removed';
  reported_at: string;
  reviewed_by: number | null;
  reviewed_at: string | null;
  cell_id: string | null;
  confirms: number;
  flags: number;
  my_vote: 1 | -1 | null;
  counts_toward_risk: boolean;
}

export interface Subscription {
  subscription_id: number;
  location_id: number;
  location_label: string;
  latitude: number;
  longitude: number;
  condition_id: number;
  weather_group: WeatherGroup;
  light_group: LightGroup;
  alert_threshold: number;
  baseline_score: number;
  is_active: boolean;
  created_at: string;
  last_alert_at: string | null;
  cell_id: string;
  current_score: number;
  current_level: RiskLevel | null;
}

export interface Alert {
  alert_id: number;
  subscription_id: number;
  risk_score_at_send: number;
  sent_at: string;
  location_label: string;
  weather_group: WeatherGroup;
  light_group: LightGroup;
  risk_level: RiskLevel | null;
}

export interface CrashRow {
  data_year: number;
  st_case: number;
  latitude: number;
  longitude: number;
  crash_date: string;
  crash_hour: number;
  crash_minute: number;
  fatalities: number;
  persons_involved: number;
  vehicles_involved: number;
  weather: string;
  weather_group: string;
  light: string;
  light_group: string;
  road_class: string;
  cell_id: string;
  state_name: string;
  county_name: string;
}

export interface CrashSearchResponse {
  crashes: CrashRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface GroupCount { crashes: number; fatalities: number }

export interface CrashStats {
  crashes: number;
  fatalities: number;
  by_weather_group: (GroupCount & { weather_group: string })[];
  by_light_group: (GroupCount & { light_group: string })[];
  by_road_class: (GroupCount & { road_class: string })[];
  by_month: MonthCount[];
  by_hour: HourCount[];
  station_weather: StationWeather;
}

export interface CrashDetail {
  crash: CrashRow & { weather_station_id: string | null; rural_urban: number; county_code: number; state_code: number };
  station_weather: {
    station_id: string;
    station_name: string;
    latitude: number;
    longitude: number;
    precipitation_mm: number | null;
    snowfall_mm: number | null;
    snow_depth_mm: number | null;
    temp_max_c: number | null;
    temp_min_c: number | null;
    avg_wind_ms: number | null;
  } | null;
  vehicles: { veh_no: number; body_type: number; model_year: number; speeding_related: number; deaths_in_vehicle: number }[];
  people: { veh_no: number; per_no: number; person_type: number; injury_severity: number; age: number; restraint_use: number }[];
}
