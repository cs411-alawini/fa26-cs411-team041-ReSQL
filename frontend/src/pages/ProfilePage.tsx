import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserRound } from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function ProfilePage() {
  const { user } = useAuth();
  return <div className="page-narrow">{user ? <Preferences /> : <AuthForms />}</div>;
}

function AuthForms() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === 'login') await login(email, password);
      else await register(email, password, name);
      navigate('/');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel auth-panel" aria-labelledby="auth-title">
      <h1 id="auth-title" className="panel-title"><UserRound size={22} aria-hidden /> {mode === 'login' ? 'Sign in' : 'Create an account'}</h1>
      <div className="tabs compact" role="tablist">
        <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'active' : ''}
                onClick={() => setMode('login')}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'active' : ''}
                onClick={() => setMode('register')}>Create account</button>
      </div>
      <form onSubmit={submit} className="stack">
        {mode === 'register' && (
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
          </div>
        )}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" required minLength={8} value={password}
                 onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
        </div>
        <button type="submit" className="primary-button" disabled={busy}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        {error && <p className="error-text" role="alert">{error}</p>}
      </form>
    </section>
  );
}

function Preferences() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState(user!.display_name);
  const [weight, setWeight] = useState(user!.safety_weight);
  const [units, setUnits] = useState(user!.units);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.updateProfile({ display_name: name, safety_weight: weight, units });
      setUser(r.user);
      setError(null);
      setMessage('Preferences saved.');
    } catch (err) { setError((err as Error).message); setMessage(null); }
  };

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.updateProfile({ password: next, current_password: current });
      setCurrent(''); setNext(''); setError(null); setMessage('Password changed.');
    } catch (err) { setError((err as Error).message); setMessage(null); }
  };

  const deleteAccount = async () => {
    try { await api.deleteAccount(); logout(); navigate('/'); }
    catch (err) { setError((err as Error).message); }
  };

  return (
    <section className="panel" aria-labelledby="profile-title">
      <h1 id="profile-title" className="panel-title"><UserRound size={22} aria-hidden /> Profile &amp; preferences</h1>
      <p className="panel-subtitle">{user!.email}{user!.role === 'admin' && <span className="badge badge-admin">Admin</span>}</p>
      <form onSubmit={save} className="stack">
        <div className="field">
          <label htmlFor="display-name">Display name</label>
          <input id="display-name" required maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="safety-weight">Route preference: {weight <= 0.2 ? 'speed first' : weight >= 0.8 ? 'safety first' : 'balanced'}</label>
          <div className="range-row">
            <span className="muted small">Fastest</span>
            <input id="safety-weight" type="range" min={0} max={1} step={0.05} value={weight}
                   onChange={(e) => setWeight(Number(e.target.value))} />
            <span className="muted small">Safest</span>
          </div>
        </div>
        <fieldset className="field radio-group inline">
          <legend>Units</legend>
          <label className="radio"><input type="radio" name="units" checked={units === 'imperial'} onChange={() => setUnits('imperial')} /> <span>Miles</span></label>
          <label className="radio"><input type="radio" name="units" checked={units === 'metric'} onChange={() => setUnits('metric')} /> <span>Kilometres</span></label>
        </fieldset>
        <button type="submit" className="primary-button">Save preferences</button>
      </form>

      <hr />
      <form onSubmit={changePassword} className="stack">
        <h2 className="panel-title small">Change password</h2>
        <div className="field">
          <label htmlFor="current-password">Current password</label>
          <input id="current-password" type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
        </div>
        <div className="field">
          <label htmlFor="new-password">New password</label>
          <input id="new-password" type="password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
        </div>
        <button type="submit" className="secondary-button">Change password</button>
      </form>
      {message && <p className="success-text" role="status">{message}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}

      <hr />
      <div className="button-row">
        <button type="button" className="secondary-button" onClick={() => { logout(); navigate('/'); }}>Sign out</button>
        {confirmDelete ? (
          <>
            <span>This deletes your saved places, reports and history.</span>
            <button type="button" className="danger-button" onClick={deleteAccount}>Yes, delete my account</button>
            <button type="button" className="secondary-button" onClick={() => setConfirmDelete(false)}>Keep it</button>
          </>
        ) : (
          <button type="button" className="danger-button" onClick={() => setConfirmDelete(true)}>Delete account</button>
        )}
      </div>
    </section>
  );
}
