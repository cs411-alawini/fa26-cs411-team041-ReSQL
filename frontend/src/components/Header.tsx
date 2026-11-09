import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useNavigate } from 'react-router-dom';
import { BarChart3, Bookmark, Car, ChevronDown, Moon, Route, Search, Sun } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { useTheme } from '../theme/ThemeContext';

const NAV = [
  { to: '/search', label: 'Search', icon: Search },
  { to: '/', label: 'Analyze', icon: Route, end: true },
  { to: '/saved', label: 'Saved Routes', icon: Bookmark },
  { to: '/reports', label: 'Reports', icon: BarChart3 },
];

export default function Header() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const initials = user?.display_name.split(/\s+/).map((p) => p[0]).join('').slice(0, 2).toUpperCase();

  return (
    <header className="app-header">
      <Link to="/" className="brand" aria-label="Traffic Safety Risk Analyzer home">
        <Car className="brand-icon" aria-hidden />
        <span>
          <span className="brand-title">Traffic Safety <span className="brand-accent">Risk Analyzer</span></span>
          <span className="brand-tagline">Safer Roads. Brighter Journeys.</span>
        </span>
      </Link>

      <nav className="main-nav" aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Icon size={18} aria-hidden />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="header-actions">
        <div className="profile-menu" ref={menuRef}>
          <button type="button" className="profile-button" aria-haspopup="menu" aria-expanded={open}
                  onClick={() => (user ? setOpen((o) => !o) : navigate('/profile'))}>
            <span className="avatar" aria-hidden>{initials ?? ''}</span>
            <span className="profile-label">{user ? user.display_name : 'Profile'}</span>
            <ChevronDown size={16} aria-hidden />
          </button>
          {open && user && (
            <div className="dropdown" role="menu">
              <div className="dropdown-head">
                <strong>{user.display_name}</strong>
                <span>{user.email}</span>
                {user.role === 'admin' && <span className="badge badge-admin">Admin</span>}
              </div>
              <Link role="menuitem" to="/profile" onClick={() => setOpen(false)}>Profile &amp; preferences</Link>
              <button role="menuitem" type="button" onClick={() => { setOpen(false); logout(); navigate('/'); }}>
                Sign out
              </button>
            </div>
          )}
        </div>
        <button type="button" className="icon-button theme-toggle" onClick={toggle}
                aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}>
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
      </div>
    </header>
  );
}
