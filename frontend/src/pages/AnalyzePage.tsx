import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Marker, Polyline, Rectangle, Tooltip } from 'react-leaflet';
import { ArrowUpDown, CalendarDays, Clock, Cloud, Route as RouteIcon, Search, SlidersHorizontal } from 'lucide-react';
import { api } from '../api/client';
import type { AnalyzeResponse, OptionType, Place, RouteConditionsInput, SavedLocation, Season, TimeOfDay } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import MapView, { pinIcon, type LatLon } from '../components/MapView';
import PlaceInput from '../components/PlaceInput';
import RiskOverTime from '../components/RiskOverTime';
import RiskSummary from '../components/RiskSummary';
import { formatDuration, formatScore, MONTHS, riskColor, shortCoords } from '../utils/format';

const WEATHER_OPTIONS: { value: RouteConditionsInput['weather']; label: string }[] = [
  { value: 'auto', label: 'Current (Auto)' },
  { value: 'dry', label: 'Clear' },
  { value: 'wet', label: 'Heavy Rain' },
  { value: 'snow_ice', label: 'Snow' },
  { value: 'low_visibility', label: 'Fog' },
];
const TIME_OPTIONS: { value: TimeOfDay; label: string }[] = [
  { value: 'now', label: 'Now' },
  { value: 'morning', label: 'Morning (6 AM – 12 PM)' },
  { value: 'afternoon', label: 'Afternoon (12 – 5 PM)' },
  { value: 'evening', label: 'Evening (5 – 9 PM)' },
  { value: 'night', label: 'Night (9 PM – 6 AM)' },
];
const OPTION_LABELS: Record<OptionType, string> = { fastest: 'Fastest', balanced: 'Balanced', safest: 'Safest' };

function parsePoint(raw: string | null, label: string): Place | null {
  if (!raw) return null;
  const [lat, lon] = raw.split(',').map(Number);
  return Number.isFinite(lat) && Number.isFinite(lon) ? { label: label || shortCoords(lat, lon), lat, lon } : null;
}

export default function AnalyzePage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [origin, setOrigin] = useState<Place | null>(() => parsePoint(params.get('from'), params.get('fromLabel') ?? ''));
  const [destination, setDestination] = useState<Place | null>(() => parsePoint(params.get('to'), params.get('toLabel') ?? ''));
  const [weather, setWeather] = useState<RouteConditionsInput['weather']>('auto');
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>('now');
  const [period, setPeriod] = useState<string>('any');
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [selected, setSelected] = useState<OptionType>('balanced');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedLocation[]>([]);

  useEffect(() => {
    if (!user) { setSaved([]); return; }
    api.locations().then((r) => setSaved(r.locations)).catch(() => setSaved([]));
  }, [user]);

  const analyze = async () => {
    if (!origin || !destination) {
      setError('Choose both a starting location and a destination.');
      return;
    }
    setBusy(true);
    setError(null);
    const conditions: RouteConditionsInput = { weather, time_of_day: timeOfDay, hour: new Date().getHours() };
    if (period.startsWith('m')) conditions.month = Number(period.slice(1));
    else if (period !== 'any') conditions.season = period as Season;
    try {
      const r = await api.analyzeRoute(origin, destination, conditions);
      setResult(r);
      setSelected(r.recommended);
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  const chooseOption = (opt: OptionType) => {
    setSelected(opt);
    if (result?.route_id) api.chooseRouteOption(result.route_id, opt).catch(() => {});
  };

  const selectedOption = result?.options.find((o) => o.option_type === selected) ?? null;
  const route = selectedOption ? result!.routes[selectedOption.route_index] : null;
  const fit = useMemo<LatLon[] | null>(() => {
    if (route) return route.geometry;
    const pts = [origin, destination].filter(Boolean) as Place[];
    return pts.length ? pts.map((p) => [p.lat, p.lon] as LatLon) : null;
  }, [route, origin, destination]);

  const onMapClick = (lat: number, lon: number) => {
    const p = { label: shortCoords(lat, lon), lat, lon };
    if (!origin) setOrigin(p);
    else if (!destination) setDestination(p);
  };

  return (
    <div className="analyze-layout">
      <aside className="panel analyzer-panel" aria-labelledby="analyzer-title">
        <h1 id="analyzer-title" className="panel-title"><RouteIcon size={22} aria-hidden /> Route Analyzer</h1>
        <p className="panel-subtitle">Compare the fastest and the safest way to get there, under the conditions you expect.</p>

        <PlaceInput label="Starting Location" placeholder="Enter starting location" value={origin}
                    onChange={setOrigin} savedLocations={saved} testId="origin-input" />
        <div className="swap-row">
          <button type="button" className="icon-button" aria-label="Swap start and destination"
                  onClick={() => { setOrigin(destination); setDestination(origin); }}>
            <ArrowUpDown size={20} />
          </button>
        </div>
        <PlaceInput label="Destination" placeholder="Enter destination" value={destination}
                    onChange={setDestination} savedLocations={saved} testId="destination-input" />
        <p className="hint">Tip: you can also click the map to drop the start, then the destination.</p>

        <button type="button" className="primary-button wide" onClick={analyze} disabled={busy} data-testid="analyze-button">
          <Search size={18} aria-hidden /> {busy ? 'Analyzing…' : 'Analyze route'}
        </button>
        {error && <p className="error-text" role="alert">{error}</p>}

        <hr />
        <h2 className="panel-title small"><SlidersHorizontal size={20} aria-hidden /> Conditions</h2>

        <div className="field">
          <label htmlFor="time-of-day"><Clock size={16} aria-hidden /> Time of Day</label>
          <select id="time-of-day" value={timeOfDay} onChange={(e) => setTimeOfDay(e.target.value as TimeOfDay)}>
            {TIME_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <fieldset className="field radio-group">
          <legend><Cloud size={16} aria-hidden /> Weather Condition</legend>
          {WEATHER_OPTIONS.map((o) => (
            <label key={o.value} className="radio">
              <input type="radio" name="weather" value={o.value} checked={weather === o.value}
                     onChange={() => setWeather(o.value)} />
              <span>{o.label}</span>
            </label>
          ))}
        </fieldset>

        <div className="field">
          <label htmlFor="season"><CalendarDays size={16} aria-hidden /> Season / Month</label>
          <select id="season" value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="any">Any time of year</option>
            <optgroup label="Season">
              <option value="winter">Winter</option>
              <option value="spring">Spring</option>
              <option value="summer">Summer</option>
              <option value="fall">Fall</option>
            </optgroup>
            <optgroup label="Month">
              {MONTHS.map((m, i) => <option key={m} value={`m${i + 1}`}>{m}</option>)}
            </optgroup>
          </select>
        </div>
      </aside>

      <section className="map-area" aria-label="Route map">
        <MapView fit={fit} onMapClick={onMapClick} testId="analyze-map"
                 overlay={result && (
                   <div className="option-switch" role="group" aria-label="Route options">
                     {(['fastest', 'balanced', 'safest'] as OptionType[]).map((t) => {
                       const o = result.options.find((x) => x.option_type === t)!;
                       return (
                         <button key={t} type="button" className={selected === t ? 'active' : ''}
                                 aria-pressed={selected === t} onClick={() => chooseOption(t)} data-testid={`option-${t}`}>
                           <strong>{OPTION_LABELS[t]}</strong>
                           <span>{formatDuration(o.duration_s)}</span>
                           <span className="score-chip" style={{ background: riskColor(o.risk_level) }}>{formatScore(o.risk_score)}</span>
                         </button>
                       );
                     })}
                   </div>
                 )}>
          {result?.routes.map((r) => r !== route && (
            <Polyline key={`alt-${r.index}`} positions={r.geometry}
                      pathOptions={{ color: '#94a3b8', weight: 4, opacity: 0.7, dashArray: '6 8' }} />
          ))}
          {route?.cells.map((c) => {
            const [a, b] = c.cell_id.split('_').map(Number);
            return (
              <Rectangle key={c.cell_id} bounds={[[a / 10, b / 10], [(a + 1) / 10, (b + 1) / 10]]}
                         pathOptions={{ color: riskColor(c.level), weight: 0, fillOpacity: c.score > 0 ? 0.18 : 0.04 }}>
                <Tooltip sticky>{`Cell ${c.cell_id}: score ${formatScore(c.score)} · ${c.crash_count} crashes in this condition`}</Tooltip>
              </Rectangle>
            );
          })}
          {route && <Polyline positions={route.geometry} pathOptions={{ color: riskColor(route.risk_level), weight: 6 }} />}
          {origin && <Marker position={[origin.lat, origin.lon]} icon={pinIcon('start', 'A')} />}
          {destination && <Marker position={[destination.lat, destination.lon]} icon={pinIcon('end', 'B')} />}
        </MapView>
        {result?.provider_fallback && (
          <p className="map-note" role="status">The routing service was unavailable, so these are approximate straight-line routes.</p>
        )}
      </section>

      <div className="summary-area">
        <RiskSummary result={result} route={route} units={user?.units ?? 'imperial'}
                     originLabel={origin?.label} destinationLabel={destination?.label} />
      </div>

      <div className="chart-area">
        <RiskOverTime byMonth={route?.stats?.by_month} byHour={route?.stats?.by_hour}
                      highlightMonths={result?.conditions.months} />
      </div>
    </div>
  );
}
