import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Marker, Popup } from 'react-leaflet';
import { AlertTriangle, Check, Flag, Pencil, ThumbsUp, Trash2 } from 'lucide-react';
import { api } from '../api/client';
import type { Place, Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import MapView, { pinIcon } from '../components/MapView';
import PlaceInput from '../components/PlaceInput';
import { formatDateTime, shortCoords } from '../utils/format';

export default function ReportsPage() {
  const { user } = useAuth();
  const [reports, setReports] = useState<Report[]>([]);
  const [filter, setFilter] = useState<'all' | 'active' | 'mine'>('all');
  const [place, setPlace] = useState<Place | null>(null);
  const [reason, setReason] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [editReason, setEditReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    const q = filter === 'mine' ? { mine: 1 } : filter === 'active' ? { status: 'active' } : undefined;
    api.reports(q).then((r) => setReports(r.reports)).catch((e) => setError(e.message));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    try { await fn(); setError(null); load(); } catch (e) { setError((e as Error).message); }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!place) { setError('Choose where it happened: search a place or click the map.'); return; }
    act(async () => { await api.createReport(place.lat, place.lon, reason); setReason(''); setPlace(null); });
  };

  return (
    <div className="page-grid reports-layout">
      <section className="panel" aria-labelledby="report-form-title">
        <h1 id="report-form-title" className="panel-title"><AlertTriangle size={22} aria-hidden /> Report a crash or hazard</h1>
        <p className="panel-subtitle">Recent reports raise the risk score of their area for 30 days, unless the community flags them.</p>
        {user ? (
          <form onSubmit={submit} className="stack">
            <PlaceInput label="Where" placeholder="Search a place, or click the map" value={place} onChange={setPlace} testId="report-place" />
            <div className="field">
              <label htmlFor="report-reason">What happened?</label>
              <textarea id="report-reason" required maxLength={255} rows={3} value={reason}
                        placeholder="e.g. Black ice on the I-74 overpass" onChange={(e) => setReason(e.target.value)} />
              <span className="muted small">{reason.length}/255</span>
            </div>
            <button type="submit" className="primary-button" data-testid="submit-report">Submit report</button>
          </form>
        ) : (
          <p className="muted"><Link to="/profile">Sign in</Link> to submit reports and vote on them.</p>
        )}
        {error && <p className="error-text" role="alert">{error}</p>}

        <div className="tabs compact" role="tablist" aria-label="Filter reports">
          {(['all', 'active', ...(user ? ['mine'] : [])] as ('all' | 'active' | 'mine')[]).map((f) => (
            <button key={f} role="tab" type="button" aria-selected={filter === f} className={filter === f ? 'active' : ''}
                    onClick={() => setFilter(f)}>{f === 'all' ? 'All' : f === 'active' ? 'Active' : 'Mine'}</button>
          ))}
        </div>

        <ul className="card-list" aria-label="Reports">
          {reports.length === 0 && <li className="muted">No reports to show.</li>}
          {reports.map((r) => {
            const mine = user?.user_id === r.user_id;
            return (
              <li key={r.report_id} className="card" data-testid="report-item">
                <div className="card-head">
                  <span className={`badge status-${r.status}`}>{r.status}</span>
                  <span className="muted">{r.author} · {formatDateTime(r.reported_at)}</span>
                </div>
                {editing === r.report_id ? (
                  <div className="inline-edit">
                    <input aria-label="Edit report" value={editReason} maxLength={255} onChange={(e) => setEditReason(e.target.value)} />
                    <button type="button" className="primary-button"
                            onClick={() => act(async () => { await api.updateReport(r.report_id, { reason: editReason }); setEditing(null); })}>Save</button>
                    <button type="button" className="secondary-button" onClick={() => setEditing(null)}>Cancel</button>
                  </div>
                ) : <p className="report-reason">{r.reason}</p>}
                <p className="muted small">
                  {shortCoords(r.latitude, r.longitude)} · {r.confirms} confirm{r.confirms === 1 ? '' : 's'}, {r.flags} flag{r.flags === 1 ? '' : 's'}
                  {r.counts_toward_risk ? ' · counts toward risk' : ''}
                </p>
                <div className="card-actions">
                  {user && !mine && r.status !== 'removed' && (
                    <>
                      <button type="button" className={`secondary-button${r.my_vote === 1 ? ' pressed' : ''}`} aria-pressed={r.my_vote === 1}
                              onClick={() => act(() => (r.my_vote === 1 ? api.unvote(r.report_id) : api.vote(r.report_id, 1)))}>
                        <ThumbsUp size={16} /> Confirm
                      </button>
                      <button type="button" className={`secondary-button${r.my_vote === -1 ? ' pressed' : ''}`} aria-pressed={r.my_vote === -1}
                              onClick={() => act(() => (r.my_vote === -1 ? api.unvote(r.report_id) : api.vote(r.report_id, -1)))}>
                        <Flag size={16} /> Flag
                      </button>
                    </>
                  )}
                  {mine && r.status !== 'removed' && (
                    <>
                      <button type="button" className="secondary-button" onClick={() => { setEditing(r.report_id); setEditReason(r.reason); }}>
                        <Pencil size={16} /> Edit
                      </button>
                      {r.status === 'active' && (
                        <button type="button" className="secondary-button"
                                onClick={() => act(() => api.updateReport(r.report_id, { status: 'resolved' }))}>
                          <Check size={16} /> Mark resolved
                        </button>
                      )}
                    </>
                  )}
                  {(mine || user?.role === 'admin') && (
                    <button type="button" className="danger-button" onClick={() => act(() => api.deleteReport(r.report_id))}
                            aria-label={`Delete report ${r.report_id}`}><Trash2 size={16} /> Delete</button>
                  )}
                  {user?.role === 'admin' && (
                    <select aria-label={`Moderate report ${r.report_id}`} value={r.status}
                            onChange={(e) => act(() => api.moderate(r.report_id, e.target.value as Report['status']))}>
                      <option value="active">Active</option>
                      <option value="resolved">Resolved</option>
                      <option value="removed">Removed</option>
                    </select>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="map-area" aria-label="Reports map">
        <MapView legend={false} fit={reports.length ? reports.map((r) => [r.latitude, r.longitude]) : null}
                 onMapClick={(lat, lon) => setPlace({ label: shortCoords(lat, lon), lat, lon })}>
          {reports.map((r) => (
            <Marker key={r.report_id} position={[r.latitude, r.longitude]} icon={pinIcon('report', '!')}>
              <Popup>{r.reason}</Popup>
            </Marker>
          ))}
          {place && <Marker position={[place.lat, place.lon]} icon={pinIcon('start', '+')} />}
        </MapView>
      </section>
    </div>
  );
}
