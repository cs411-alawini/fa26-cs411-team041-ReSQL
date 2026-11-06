import { useEffect, useMemo, useState } from 'react';
import { CircleMarker, Popup } from 'react-leaflet';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Search, X } from 'lucide-react';
import { api } from '../api/client';
import type { CrashDetail, CrashRow, CrashSearchResponse, CrashStats, Lookups } from '../api/types';
import MapView, { type Bounds } from '../components/MapView';
import { formatDate, formatHour, LIGHT_LABELS, MONTHS, placeName, WEATHER_LABELS } from '../utils/format';

const PAGE = 50;

interface Filters {
  area: 'map' | 'state';
  state_code: string;
  county_code: string;
  weather_group: string;
  light_group: string;
  func_sys_code: string;
  period: string;
  time_of_day: string;
  year: string;
}

const EMPTY: Filters = { area: 'map', state_code: '', county_code: '', weather_group: '', light_group: '',
  func_sys_code: '', period: '', time_of_day: '', year: '' };

export default function SearchPage() {
  const [lookups, setLookups] = useState<Lookups | null>(null);
  const [counties, setCounties] = useState<{ county_code: number; county_name: string }[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [results, setResults] = useState<CrashSearchResponse | null>(null);
  const [stats, setStats] = useState<CrashStats | null>(null);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<CrashDetail | null>(null);

  useEffect(() => { api.lookups().then(setLookups).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    if (!filters.state_code) { setCounties([]); return; }
    api.counties(Number(filters.state_code)).then((r) => setCounties(r.counties)).catch(() => setCounties([]));
  }, [filters.state_code]);

  const query = useMemo(() => {
    const q: Record<string, string | number> = {};
    if (filters.area === 'map' && bounds) Object.assign(q, roundBounds(bounds));
    if (filters.area === 'state' && filters.state_code) {
      q.state_code = filters.state_code;
      if (filters.county_code) q.county_code = filters.county_code;
    }
    for (const k of ['weather_group', 'light_group', 'func_sys_code', 'time_of_day', 'year'] as const) {
      if (filters[k]) q[k] = filters[k];
    }
    if (filters.period.startsWith('m')) q.month = filters.period.slice(1);
    else if (filters.period) q.season = filters.period;
    return q;
  }, [filters, bounds]);

  const run = async (newOffset = 0) => {
    setBusy(true);
    setError(null);
    try {
      const [list, s] = await Promise.all([
        api.searchCrashes({ ...query, limit: PAGE, offset: newOffset }),
        newOffset === 0 ? api.crashStats(query) : Promise.resolve(stats),
      ]);
      setResults(list);
      setStats(s);
      setOffset(newOffset);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof Filters, v: string) => setFilters((f) => ({ ...f, [k]: v, ...(k === 'state_code' ? { county_code: '' } : {}) }));
  const openDetail = (c: CrashRow) => api.crashDetail(c.data_year, c.st_case).then(setDetail).catch((e) => setError(e.message));

  return (
    <div className="page-grid search-layout">
      <aside className="panel filter-panel" aria-labelledby="search-title">
        <h1 id="search-title" className="panel-title"><Search size={22} aria-hidden /> Search crashes</h1>
        <p className="panel-subtitle">Fatal crashes from NHTSA FARS, joined with the NOAA weather station reading for the same day.</p>

        <fieldset className="field radio-group">
          <legend>Area</legend>
          <label className="radio"><input type="radio" name="area" checked={filters.area === 'map'}
                                          onChange={() => set('area', 'map')} /> <span>Current map view</span></label>
          <label className="radio"><input type="radio" name="area" checked={filters.area === 'state'}
                                          onChange={() => set('area', 'state')} /> <span>State / county</span></label>
        </fieldset>
        {filters.area === 'state' && (
          <>
            <Select id="state" label="State" value={filters.state_code} onChange={(v) => set('state_code', v)}
                    options={(lookups?.states ?? []).map((s) => [String(s.state_code), s.state_name])} anyLabel="Choose a state" />
            <Select id="county" label="County" value={filters.county_code} onChange={(v) => set('county_code', v)}
                    options={counties.map((c) => [String(c.county_code), placeName(c.county_name)])} anyLabel="All counties" />
          </>
        )}
        <Select id="weather" label="Weather" value={filters.weather_group} onChange={(v) => set('weather_group', v)}
                options={['dry', 'wet', 'snow_ice', 'low_visibility', 'unknown'].map((g) => [g, WEATHER_LABELS[g]])} />
        <Select id="light" label="Light" value={filters.light_group} onChange={(v) => set('light_group', v)}
                options={['day', 'dark', 'unknown'].map((g) => [g, LIGHT_LABELS[g]])} />
        <Select id="road" label="Road type" value={filters.func_sys_code} onChange={(v) => set('func_sys_code', v)}
                options={(lookups?.road_classes ?? []).map((r) => [String(r.func_sys_code), r.description])} />
        <Select id="tod" label="Time of day" value={filters.time_of_day} onChange={(v) => set('time_of_day', v)}
                options={[['morning', 'Morning'], ['afternoon', 'Afternoon'], ['evening', 'Evening'], ['night', 'Night']]} />
        <Select id="period" label="Season / month" value={filters.period} onChange={(v) => set('period', v)}
                options={[['winter', 'Winter'], ['spring', 'Spring'], ['summer', 'Summer'], ['fall', 'Fall'],
                          ...MONTHS.map((m, i) => [`m${i + 1}`, m] as [string, string])]} />
        <Select id="year" label="Year" value={filters.year} onChange={(v) => set('year', v)}
                options={(lookups?.years ?? []).map((y) => [String(y), String(y)])} />

        <div className="button-row">
          <button type="button" className="primary-button" onClick={() => run(0)} disabled={busy} data-testid="search-button">
            {busy ? 'Searching…' : 'Search'}
          </button>
          <button type="button" className="secondary-button" onClick={() => { setFilters(EMPTY); setResults(null); setStats(null); }}>
            Reset
          </button>
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
      </aside>

      <section className="map-area search-map" aria-label="Crash map">
        <MapView zoom={10} onBoundsChange={setBounds} legend={false} testId="search-map">
          {results?.crashes.map((c) => (
            <CircleMarker key={`${c.data_year}-${c.st_case}`} center={[c.latitude, c.longitude]}
                          radius={4 + Math.min(6, c.fatalities * 2)}
                          pathOptions={{ color: '#b91c1c', fillColor: '#ef4444', fillOpacity: 0.65, weight: 1 }}
                          eventHandlers={{ click: () => openDetail(c) }}>
              <Popup>{formatDate(c.crash_date)} · {c.fatalities} killed · {c.weather}</Popup>
            </CircleMarker>
          ))}
        </MapView>
      </section>

      <section className="panel results-panel" aria-labelledby="results-title">
        <h2 id="results-title" className="panel-title small">Results</h2>
        {!results && <p className="muted">Pan the map to an area (or choose a state) and press Search.</p>}
        {results && stats && (
          <>
            <div className="stat-row">
              <div className="stat-box"><span className="stat-value" data-testid="result-total">{results.total.toLocaleString()}</span><span className="stat-label">fatal crashes</span></div>
              <div className="stat-box"><span className="stat-value">{stats.fatalities.toLocaleString()}</span><span className="stat-label">people killed</span></div>
              <div className="stat-box"><span className="stat-value">{pct(stats.station_weather.on_wet_days, stats.station_weather.crashes_with_station)}</span>
                <span className="stat-label">on days with rain at the nearest station</span></div>
            </div>
            <div className="mini-charts">
              <MiniBar title="By weather" data={stats.by_weather_group.map((g) => ({ name: WEATHER_LABELS[g.weather_group] ?? g.weather_group, crashes: g.crashes }))} />
              <MiniBar title="By light" data={stats.by_light_group.map((g) => ({ name: LIGHT_LABELS[g.light_group] ?? g.light_group, crashes: g.crashes }))} />
              <MiniBar title="By road type" data={stats.by_road_class.slice(0, 6).map((g) => ({ name: g.road_class, crashes: g.crashes }))} />
            </div>
            <table className="data-table">
              <thead><tr><th>Date</th><th>Time</th><th>Place</th><th>Weather</th><th>Light</th><th>Road</th><th>Killed</th></tr></thead>
              <tbody>
                {results.crashes.map((c) => (
                  <tr key={`${c.data_year}-${c.st_case}`} onClick={() => openDetail(c)} tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter') openDetail(c); }}>
                    <td>{formatDate(c.crash_date)}</td><td>{formatHour(c.crash_hour)}</td>
                    <td>{placeName(c.county_name)}, {c.state_name}</td><td>{c.weather}</td><td>{c.light}</td>
                    <td>{c.road_class}</td><td>{c.fatalities}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="pager">
              <button type="button" className="secondary-button" disabled={offset === 0 || busy} onClick={() => run(offset - PAGE)}>Previous</button>
              <span>{results.total ? `${offset + 1}–${Math.min(offset + PAGE, results.total)} of ${results.total}` : 'No crashes match'}</span>
              <button type="button" className="secondary-button" disabled={offset + PAGE >= results.total || busy}
                      onClick={() => run(offset + PAGE)}>Next</button>
            </div>
          </>
        )}
      </section>

      {detail && <CrashDrawer detail={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function roundBounds(b: Bounds) {
  const r = (v: number) => Math.round(v * 10000) / 10000;
  return { min_lat: r(Math.max(-90, b.min_lat)), min_lon: r(Math.max(-180, b.min_lon)),
           max_lat: r(Math.min(90, b.max_lat)), max_lon: r(Math.min(180, b.max_lon)) };
}

function pct(part: number, whole: number): string {
  return whole ? `${Math.round((100 * part) / whole)}%` : '—';
}

function Select({ id, label, value, onChange, options, anyLabel = 'Any' }: {
  id: string; label: string; value: string; onChange: (v: string) => void; options: [string, string][]; anyLabel?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={`f-${id}`}>{label}</label>
      <select id={`f-${id}`} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{anyLabel}</option>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  );
}

function MiniBar({ title, data }: { title: string; data: { name: string; crashes: number }[] }) {
  return (
    <div className="mini-chart">
      <h3>{title}</h3>
      <div style={{ height: 140 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
            <XAxis type="number" hide allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={110} fontSize={11} tickLine={false} axisLine={false} />
            <Tooltip formatter={(v: number) => [`${v} crashes`, '']} />
            <Bar dataKey="crashes" fill="#3b82f6" radius={[0, 4, 4, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CrashDrawer({ detail, onClose }: { detail: CrashDetail; onClose: () => void }) {
  const c = detail.crash;
  const w = detail.station_weather;
  return (
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="crash-title">
      <div className="drawer-head">
        <h2 id="crash-title">Crash {c.st_case} · {formatDate(c.crash_date)}</h2>
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={18} /></button>
      </div>
      <dl className="detail-list">
        <dt>Where</dt><dd>{placeName(c.county_name)}, {c.state_name} (cell {c.cell_id})</dd>
        <dt>When</dt><dd>{formatHour(c.crash_hour)}</dd>
        <dt>Reported weather</dt><dd>{c.weather}</dd>
        <dt>Light</dt><dd>{c.light}</dd>
        <dt>Road</dt><dd>{c.road_class}</dd>
        <dt>Killed</dt><dd>{c.fatalities} of {c.persons_involved} people, {c.vehicles_involved} vehicle(s)</dd>
      </dl>
      <h3>Weather station that day</h3>
      {w ? (
        <dl className="detail-list">
          <dt>Station</dt><dd>{w.station_name} ({w.station_id})</dd>
          <dt>Precipitation</dt><dd>{w.precipitation_mm ?? '—'} mm</dd>
          <dt>Snowfall</dt><dd>{w.snowfall_mm ?? '—'} mm</dd>
          <dt>High / low</dt><dd>{w.temp_max_c ?? '—'} °C / {w.temp_min_c ?? '—'} °C</dd>
          <dt>Wind</dt><dd>{w.avg_wind_ms ?? '—'} m/s</dd>
        </dl>
      ) : <p className="muted">No station within 50 km reported that day.</p>}
      <p className="muted">{detail.vehicles.length} vehicle record(s), {detail.people.length} person record(s) in FARS.</p>
    </div>
  );
}
