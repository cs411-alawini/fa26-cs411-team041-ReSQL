import { CarFront, Clock, Cloud, CloudFog, CloudRain, CloudSnow, Info, Moon, Route as RouteIcon, ShieldCheck, Sun, TrafficCone } from 'lucide-react';
import type { AnalyzedRoute, AnalyzeResponse, RiskFactor } from '../api/types';
import { formatDistance, formatDuration, formatScore, LIGHT_LABELS, riskColor, riskLabel } from '../utils/format';

interface Props {
  result: AnalyzeResponse | null;
  route: AnalyzedRoute | null;
  units: 'metric' | 'imperial';
  originLabel?: string;
  destinationLabel?: string;
}

const WEATHER_ICONS = { dry: Cloud, wet: CloudRain, snow_ice: CloudSnow, low_visibility: CloudFog } as const;
const FACTOR_ICONS: Record<RiskFactor['key'], typeof Cloud> = { weather: Cloud, time: Clock, road: TrafficCone, vehicle: CarFront };

function Donut({ score, color }: { score: number | null; color: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <svg className="donut" viewBox="0 0 140 140" role="img" aria-label={score === null ? 'No score yet' : `Risk score ${Math.round(score)} out of 100`}>
      <circle cx="70" cy="70" r={r} className="donut-track" />
      {pct > 0 && (
        <circle cx="70" cy="70" r={r} className="donut-value" stroke={color} strokeDasharray={`${pct * c} ${c}`}
                transform="rotate(-90 70 70)" />
      )}
      <text x="70" y="68" textAnchor="middle" className="donut-number">{formatScore(score)}</text>
      <text x="70" y="90" textAnchor="middle" className="donut-caption">{score === null ? 'no route yet' : 'of 100'}</text>
    </svg>
  );
}

export default function RiskSummary({ result, route, units, originLabel, destinationLabel }: Props) {
  const cond = result?.conditions;
  const color = riskColor(route?.risk_level);
  const WeatherIcon = cond ? WEATHER_ICONS[cond.weather_group] : Cloud;
  const LightIcon = cond?.light_group === 'day' ? Sun : Moon;
  const roadFactor = route?.stats?.factors.find((f) => f.key === 'road');
  const topRoad = roadFactor?.label.startsWith('On ') ? roadFactor.label.replace(/^On | roads$/g, '') : '—';

  return (
    <section className="panel risk-summary" aria-labelledby="risk-summary-title">
      <h2 id="risk-summary-title" className="panel-title"><ShieldCheck size={22} aria-hidden /> Risk Summary</h2>
      {route ? (
        <p className="panel-subtitle">
          {originLabel && destinationLabel ? <>{originLabel} → {destinationLabel}<br /></> : null}
          <span style={{ color }} className="risk-level-text" data-testid="risk-level">{riskLabel(route.risk_level)} risk</span>
          {' '}· {route.stats?.crashes ?? 0} fatal crashes recorded along this route
        </p>
      ) : (
        <p className="panel-subtitle">Choose a start and destination, then analyze the route to see its risk.</p>
      )}

      <div className="donut-wrap">
        <Donut score={route ? route.risk_score : null} color={color} />
        {result?.risk_model.placeholder && (
          <span className="badge badge-info" title="Scores come from the Stage 2 CellRiskCurrent view until the ML model is ready.">
            <Info size={12} aria-hidden /> Placeholder model
          </span>
        )}
      </div>

      <div className="conditions-box">
        <h3>Current conditions</h3>
        <div className="conditions-row">
          <span><WeatherIcon size={20} aria-hidden /> {cond ? cond.description : '—'}</span>
          <span><LightIcon size={20} aria-hidden /> {cond ? LIGHT_LABELS[cond.light_group] : '—'}</span>
          <span><TrafficCone size={20} aria-hidden /> {route ? topRoad : '—'}</span>
        </div>
      </div>

      <h3 className="section-title"><span aria-hidden className="bars-icon" />Risk Factors</h3>
      <ul className="factor-list">
        {(route?.stats?.factors ?? defaultFactors).map((f) => {
          const Icon = FACTOR_ICONS[f.key];
          const pct = f.percent ?? 0;
          return (
            <li key={f.key} data-testid={`factor-${f.key}`}>
              <Icon size={18} aria-hidden />
              <span className="factor-label">{f.label}</span>
              <span className="factor-value">{f.percent === null ? '—' : `${Math.round(pct)}%`}</span>
              <span className="factor-bar" aria-hidden><span style={{ width: `${pct}%`, background: barColor(pct) }} /></span>
            </li>
          );
        })}
      </ul>

      <div className="stat-tiles">
        <div className="stat-tile">
          <RouteIcon size={22} aria-hidden />
          <div><span className="stat-value" data-testid="route-distance">{route ? formatDistance(route.distance_m, units) : '—'}</span>
            <span className="stat-label">Distance</span></div>
        </div>
        <div className="stat-tile">
          <Clock size={22} aria-hidden />
          <div><span className="stat-value" data-testid="route-duration">{route ? formatDuration(route.duration_s) : '—'}</span>
            <span className="stat-label">Travel time</span></div>
        </div>
      </div>
    </section>
  );
}

const defaultFactors: RiskFactor[] = [
  { key: 'weather', label: 'Crashes in this weather', percent: null },
  { key: 'time', label: 'Crashes at this time of day', percent: null },
  { key: 'road', label: 'Road type', percent: null },
  { key: 'vehicle', label: 'Vehicles speeding-related', percent: null },
];

function barColor(pct: number): string {
  if (pct >= 60) return '#e5383b';
  if (pct >= 35) return '#f28c28';
  if (pct >= 15) return '#f5c518';
  return '#22a447';
}
