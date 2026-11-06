import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import { ThemeProvider } from './theme/ThemeContext';
import Header from './components/Header';
import AnalyzePage from './pages/AnalyzePage';
import SearchPage from './pages/SearchPage';
import SavedRoutesPage from './pages/SavedRoutesPage';
import ReportsPage from './pages/ReportsPage';
import ProfilePage from './pages/ProfilePage';

export function AppRoutes() {
  return (
    <div className="app">
      <Header />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<AnalyzePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/saved" element={<SavedRoutesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
