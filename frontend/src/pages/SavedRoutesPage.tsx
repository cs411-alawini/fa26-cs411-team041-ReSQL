import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Bookmark, MapPin, Pencil, Trash2 } from 'lucide-react';
import { Marker } from 'react-leaflet';
import { api } from '../api/client';
import type { Alert, ConditionProfile, Place, RouteHistoryItem, SavedLocation, Subscription } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import MapView, { pinIcon } from '../components/MapView';
import PlaceInput from '../components/PlaceInput';
import SignInPrompt from '../components/SignInPrompt';
import { conditionLabel, formatDateTime, formatDuration, formatScore, riskColor, riskLabel, shortCoords } from '../utils/format';

type Tab = 'history' | 'locations' | 'alerts';

export default function SavedRoutesPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>('history');
  if (!user) return <SignInPrompt what="see your saved routes and places" />;
  return (
    <div className="page-narrow">
      <div className="tabs" role="tablist" aria-label="Saved items">
        {([['history', 'Route history'], ['locations', 'Saved locations'], ['alerts', 'Alerts & subscriptions']] as [Tab, string][])
          .map(([t, label]) => (
            <button key={t} role="tab" type="button" aria-selected={tab === t} className={tab === t ? 'active' : ''}
                    onClick={() => setTab(t)}>{label}</button>
          ))}
      </div>
      {tab === 'history' && <RouteHistory />}
      {tab === 'locations' && <Locations />}
      {tab === 'alerts' && <Alerts isAdmin={user.role === 'admin'} />}
    </div>
  );
}

function RouteHistory() {
  const [routes, setRoutes] = useState<RouteHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.routeHistory().then((r) => setRoutes(r.routes)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const remove = async (id: number) => {
    try { await api.deleteRoute(id); load(); } catch (e) { setError((e as Error).message); }
  };

  return (
    <section className="panel" aria-labelledby="history-title">
      <h1 id="history-title" className="panel-title"><Bookmark size={22} aria-hidden /> Route history</h1>
      {error && <p className="error-text" role="alert">{error}</p>}
      {routes?.length === 0 && <p className="muted">No routes yet. Analyze one on the <Link to="/">Analyze</Link> page while signed in.</p>}
      <ul className="card-list">
        {routes?.map((r) => (
          <li key={r.route_id} className="card" data-testid="history-item">
            <div className="card-head">
              <strong>{shortCoords(r.origin_lat, r.origin_lon)} → {shortCoords(r.dest_lat, r.dest_lon)}</strong>
              <span className="muted">{formatDateTime(r.requested_at)}</span>
            </div>
            <div className="option-pills">
              {r.options.map((o) => (
                <span key={o.option_type} className={`option-pill${r.chosen_option === o.option_type ? ' chosen' : ''}`}>
                  <span className="option-name">{o.option_type}</span> · {formatDuration(o.travel_time_s)} ·
                  <span className="score-chip" style={{ background: riskColor(o.risk_level) }}>{formatScore(o.risk_score)}</span>
                  {r.chosen_option === o.option_type && <em> chosen</em>}
                </span>
              ))}
            </div>
            <div className="card-actions">
              <Link className="secondary-button" to={`/?from=${r.origin_lat},${r.origin_lon}&to=${r.dest_lat},${r.dest_lon}`}>
                Open in Analyze
              </Link>
              <button type="button" className="danger-button" onClick={() => remove(r.route_id)}
                      aria-label={`Delete route ${r.route_id}`}><Trash2 size={16} /> Delete</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Locations() {
  const [locations, setLocations] = useState<SavedLocation[]>([]);
  const [place, setPlace] = useState<Place | null>(null);
  const [label, setLabel] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api.locations().then((r) => setLocations(r.locations)).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    if (!place) { setError('Pick a place from the list or click the map.'); return; }
    try {
      await api.createLocation(label.trim() || place.label.slice(0, 60), place.lat, place.lon);
      setPlace(null); setLabel(''); setError(null); load();
    } catch (err) { setError((err as Error).message); }
  };
  const save = async (id: number) => {
    try { await api.updateLocation(id, { label: editLabel }); setEditing(null); load(); }
    catch (err) { setError((err as Error).message); }
  };
  const remove = async (id: number) => {
    try { await api.deleteLocation(id); load(); } catch (err) { setError((err as Error).message); }
  };

  return (
    <div className="two-col">
      <section className="panel" aria-labelledby="locations-title">
        <h1 id="locations-title" className="panel-title"><MapPin size={22} aria-hidden /> Saved locations</h1>
        <form onSubmit={add} className="stack">
          <PlaceInput label="Place" placeholder="Search a place, or click the map" value={place} onChange={setPlace} testId="location-place" />
          <div className="field">
            <label htmlFor="loc-label">Name</label>
            <input id="loc-label" value={label} maxLength={60} placeholder="e.g. Home, Work" onChange={(e) => setLabel(e.target.value)} />
          </div>
          <button type="submit" className="primary-button">Save location</button>
        </form>
        {error && <p className="error-text" role="alert">{error}</p>}
        <ul className="card-list">
          {locations.map((l) => (
            <li key={l.location_id} className="card" data-testid="location-item">
              {editing === l.location_id ? (
                <div className="inline-edit">
                  <input aria-label="New name" value={editLabel} maxLength={60} onChange={(e) => setEditLabel(e.target.value)} />
                  <button type="button" className="primary-button" onClick={() => save(l.location_id)}>Save</button>
                  <button type="button" className="secondary-button" onClick={() => setEditing(null)}>Cancel</button>
                </div>
              ) : (
                <div className="card-head">
                  <strong>{l.label}</strong>
                  <span className="muted">{shortCoords(l.latitude, l.longitude)} · {l.subscriptions} subscription(s)</span>
                </div>
              )}
              <div className="card-actions">
                <button type="button" className="secondary-button" aria-label={`Rename ${l.label}`}
                        onClick={() => { setEditing(l.location_id); setEditLabel(l.label); }}><Pencil size={16} /> Rename</button>
                <button type="button" className="danger-button" aria-label={`Delete ${l.label}`}
                        onClick={() => remove(l.location_id)}><Trash2 size={16} /> Delete</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="map-area small-map" aria-label="Saved locations map">
        <MapView legend={false} fit={locations.length ? locations.map((l) => [l.latitude, l.longitude]) : null}
                 onMapClick={(lat, lon) => setPlace({ label: shortCoords(lat, lon), lat, lon })}>
          {locations.map((l) => <Marker key={l.location_id} position={[l.latitude, l.longitude]} icon={pinIcon('saved', '★')} />)}
          {place && <Marker position={[place.lat, place.lon]} icon={pinIcon('start', '+')} />}
        </MapView>
      </section>
    </div>
  );
}

function Alerts({ isAdmin }: { isAdmin: boolean }) {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [locations, setLocations] = useState<SavedLocation[]>([]);
  const [profiles, setProfiles] = useState<ConditionProfile[]>([]);
  const [form, setForm] = useState({ location_id: '', condition_id: '', alert_threshold: '10' });
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, a, l] = await Promise.all([api.subscriptions(), api.alerts(), api.locations()]);
      setSubs(s.subscriptions); setAlerts(a.alerts); setLocations(l.locations);
    } catch (e) { setError((e as Error).message); }
  }, []);
  useEffect(() => { load(); api.lookups().then((r) => setProfiles(r.condition_profiles)).catch(() => {}); }, [load]);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.createSubscription(Number(form.location_id), Number(form.condition_id), Number(form.alert_threshold));
      setError(null); setMessage('Subscription created.'); load();
    } catch (err) { setError((err as Error).message); }
  };
  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); setError(null); load(); } catch (err) { setError((err as Error).message); }
  };

  return (
    <div className="two-col">
      <section className="panel" aria-labelledby="subs-title">
        <h1 id="subs-title" className="panel-title"><Bell size={22} aria-hidden /> Risk subscriptions</h1>
        <p className="panel-subtitle">Get an alert when a saved location's risk changes by at least the threshold under a condition you care about.</p>
        {locations.length === 0 ? (
          <p className="muted">Save a location first, then subscribe to it here.</p>
        ) : (
          <form onSubmit={add} className="stack">
            <div className="field">
              <label htmlFor="sub-location">Location</label>
              <select id="sub-location" required value={form.location_id} onChange={(e) => setForm({ ...form, location_id: e.target.value })}>
                <option value="">Choose…</option>
                {locations.map((l) => <option key={l.location_id} value={l.location_id}>{l.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sub-condition">Condition</label>
              <select id="sub-condition" required value={form.condition_id} onChange={(e) => setForm({ ...form, condition_id: e.target.value })}>
                <option value="">Choose…</option>
                {profiles.map((p) => <option key={p.condition_id} value={p.condition_id}>{conditionLabel(p.weather_group, p.light_group)}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="sub-threshold">Alert when the score changes by at least</label>
              <input id="sub-threshold" type="number" min={1} max={100} step={1} required value={form.alert_threshold}
                     onChange={(e) => setForm({ ...form, alert_threshold: e.target.value })} />
            </div>
            <button type="submit" className="primary-button">Subscribe</button>
          </form>
        )}
        {message && <p className="success-text" role="status">{message}</p>}
        {error && <p className="error-text" role="alert">{error}</p>}
        <ul className="card-list">
          {subs.map((s) => (
            <li key={s.subscription_id} className="card" data-testid="subscription-item">
              <div className="card-head">
                <strong>{s.location_label}</strong>
                <span className="muted">{conditionLabel(s.weather_group, s.light_group)} · alert at ±{s.alert_threshold}</span>
              </div>
              <p>Now <span className="score-chip" style={{ background: riskColor(s.current_level) }}>{formatScore(s.current_score)}</span>
                {' '}({riskLabel(s.current_level)}), baseline {formatScore(s.baseline_score)}</p>
              <div className="card-actions">
                <button type="button" className="secondary-button"
                        onClick={() => act(() => api.updateSubscription(s.subscription_id, { is_active: !s.is_active }))}>
                  {s.is_active ? 'Pause' : 'Resume'}
                </button>
                <button type="button" className="danger-button" onClick={() => act(() => api.deleteSubscription(s.subscription_id))}>
                  <Trash2 size={16} /> Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="panel" aria-labelledby="alerts-title">
        <h1 id="alerts-title" className="panel-title">Alerts</h1>
        {isAdmin && (
          <button type="button" className="secondary-button" onClick={() => act(async () => {
            const r = await api.runAlerts();
            setMessage(`Checked ${r.checked} subscriptions, sent ${r.alerts_created} alerts.`);
          })}>Run alert job now</button>
        )}
        {alerts.length === 0 ? <p className="muted">No alerts yet.</p> : (
          <ul className="card-list">
            {alerts.map((a) => (
              <li key={a.alert_id} className="card">
                <div className="card-head">
                  <strong>{a.location_label}</strong><span className="muted">{formatDateTime(a.sent_at)}</span>
                </div>
                <p>{conditionLabel(a.weather_group, a.light_group)}: risk is now{' '}
                  <span className="score-chip" style={{ background: riskColor(a.risk_level) }}>{formatScore(a.risk_score_at_send)}</span></p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
