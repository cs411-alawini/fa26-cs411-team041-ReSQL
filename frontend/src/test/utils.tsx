import type { ReactElement } from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { AuthContext, type AuthState } from '../auth/AuthContext';
import { ThemeProvider } from '../theme/ThemeContext';
import type { User } from '../api/types';

export const testUser: User = {
  user_id: 7,
  email: 'vinay@example.com',
  display_name: 'Vinay Ravuru',
  role: 'user',
  safety_weight: 0.5,
  units: 'imperial',
  created_at: '2026-11-01T10:00:00Z',
};

export function renderWithProviders(ui: ReactElement, { user = null as User | null, route = '/', auth = {} as Partial<AuthState> } = {}) {
  const value: AuthState = {
    user,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    setUser: vi.fn(),
    ...auth,
  };
  const result = render(
    <ThemeProvider>
      <AuthContext.Provider value={value}>
        <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          {ui}
        </MemoryRouter>
      </AuthContext.Provider>
    </ThemeProvider>,
  );
  return { ...result, auth: value };
}
