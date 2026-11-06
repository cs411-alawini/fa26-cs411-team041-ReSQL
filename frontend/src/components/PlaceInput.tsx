import { useEffect, useId, useRef, useState } from 'react';
import { MapPin, X } from 'lucide-react';
import { api } from '../api/client';
import type { Place, SavedLocation } from '../api/types';

interface Props {
  label: string;
  placeholder: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  savedLocations?: SavedLocation[];
  testId?: string;
}

/** Text box with place search (server-side geocoding) and the user's saved locations as shortcuts. */
export default function PlaceInput({ label, placeholder, value, onChange, savedLocations = [], testId }: Props) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? '');
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setText(value?.label ?? ''); }, [value]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  useEffect(() => {
    const q = text.trim();
    if (!open || q.length < 2 || q === value?.label) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError(null);
      api.geocode(q)
        .then((r) => { if (!cancelled) setResults(r.results); })
        .catch((e: Error) => { if (!cancelled) setError(e.message); })
        .finally(() => { if (!cancelled) setBusy(false); });
    }, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [text, open, value?.label]);

  const saved = savedLocations
    .filter((l) => !text.trim() || l.label.toLowerCase().includes(text.trim().toLowerCase()))
    .map((l) => ({ label: l.label, lat: l.latitude, lon: l.longitude, source: 'saved' }));

  const choose = (p: Place) => {
    onChange(p);
    setText(p.label);
    setOpen(false);
  };

  return (
    <div className="field" ref={boxRef}>
      <label htmlFor={id}>{label}</label>
      <div className="input-with-icons">
        <MapPin className="input-icon" size={18} aria-hidden />
        <input id={id} data-testid={testId} value={text} placeholder={placeholder} autoComplete="off"
               role="combobox" aria-expanded={open} aria-controls={`${id}-list`}
               onFocus={() => setOpen(true)}
               onChange={(e) => { setText(e.target.value); setOpen(true); if (value) onChange(null); }}
               onKeyDown={(e) => {
                 if (e.key === 'Enter' && results[0]) { e.preventDefault(); choose(results[0]); }
                 if (e.key === 'Escape') setOpen(false);
               }} />
        {text && (
          <button type="button" className="input-clear" aria-label={`Clear ${label.toLowerCase()}`}
                  onClick={() => { setText(''); onChange(null); setResults([]); }}>
            <X size={16} />
          </button>
        )}
      </div>
      {open && (saved.length > 0 || results.length > 0 || busy || error) && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {saved.map((p) => (
            <li key={`s-${p.label}-${p.lat}`} role="option" aria-selected={false}>
              <button type="button" onClick={() => choose(p)}>
                <span className="badge">Saved</span> {p.label}
              </button>
            </li>
          ))}
          {results.map((p) => (
            <li key={`r-${p.label}-${p.lat}-${p.lon}`} role="option" aria-selected={false}>
              <button type="button" onClick={() => choose(p)}>{p.label}</button>
            </li>
          ))}
          {busy && <li className="muted">Searching…</li>}
          {error && <li className="error-text">{error}</li>}
        </ul>
      )}
    </div>
  );
}
