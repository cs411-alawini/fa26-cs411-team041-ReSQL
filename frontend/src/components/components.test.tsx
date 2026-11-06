import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, testUser } from '../test/utils';
import { analyzeResponse } from '../test/fixtures';

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>();
  return { ...actual, api: { geocode: vi.fn() } };
});

import { api } from '../api/client';
import Header from './Header';
import PlaceInput from './PlaceInput';
import RiskLegend from './RiskLegend';
import RiskOverTime from './RiskOverTime';
import RiskSummary from './RiskSummary';

const geocode = api.geocode as unknown as ReturnType<typeof vi.fn>;

describe('Header', () => {
  it('shows the navigation from the mockup', () => {
    renderWithProviders(<Header />, { route: '/' });
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).getAllByRole('link').map((l) => l.textContent)).toEqual(['Search', 'Analyze', 'Saved Routes', 'Reports']);
    expect(within(nav).getByRole('link', { name: 'Analyze' })).toHaveClass('active');
    expect(screen.getByText('Profile')).toBeInTheDocument();
  });

  it('toggles dark mode', async () => {
    renderWithProviders(<Header />);
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('shows the signed-in user and signs out', async () => {
    const { auth } = renderWithProviders(<Header />, { user: { ...testUser, role: 'admin' } });
    await userEvent.click(screen.getByRole('button', { name: /Vinay Ravuru/ }));
    expect(screen.getByText('Admin')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));
    expect(auth.logout).toHaveBeenCalled();
  });
});

describe('PlaceInput', () => {
  beforeEach(() => geocode.mockReset());

  it('searches places and reports the choice', async () => {
    geocode.mockResolvedValue({ results: [{ label: 'Urbana, IL', lat: 40.11, lon: -88.2 }], source: 'offline' });
    const onChange = vi.fn();
    renderWithProviders(<PlaceInput label="Destination" placeholder="Enter destination" value={null} onChange={onChange} />);
    await userEvent.type(screen.getByPlaceholderText('Enter destination'), 'Urb');
    await userEvent.click(await screen.findByRole('button', { name: 'Urbana, IL' }));
    expect(geocode).toHaveBeenCalledWith('Urb');
    expect(onChange).toHaveBeenLastCalledWith({ label: 'Urbana, IL', lat: 40.11, lon: -88.2 });
  });

  it('offers saved locations and clears', async () => {
    const onChange = vi.fn();
    renderWithProviders(
      <PlaceInput label="Starting Location" placeholder="Start" value={{ label: 'Home', lat: 1, lon: 2 }} onChange={onChange}
                  savedLocations={[{ location_id: 1, label: 'Work', latitude: 40, longitude: -88, created_at: '', subscriptions: 0, cell_id: '400_-880' }]} />,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Clear starting location' }));
    expect(onChange).toHaveBeenCalledWith(null);
    await userEvent.click(screen.getByPlaceholderText('Start'));
    await userEvent.click(screen.getByRole('button', { name: /Work/ }));
    expect(onChange).toHaveBeenLastCalledWith({ label: 'Work', lat: 40, lon: -88, source: 'saved' });
  });

  it('shows geocoding errors', async () => {
    // A plain function rather than vi.fn(): Vitest's spy result tracking reports a rejected
    // promise returned by a spy as unhandled, even though PlaceInput catches it.
    const original = api.geocode;
    (api as { geocode: unknown }).geocode = () => Promise.reject(new Error('Cannot reach the server.'));
    try {
      renderWithProviders(<PlaceInput label="Where" placeholder="Where" value={null} onChange={vi.fn()} />);
      await userEvent.type(screen.getByPlaceholderText('Where'), 'Chicago');
      expect(await screen.findByText('Cannot reach the server.')).toBeInTheDocument();
    } finally {
      (api as { geocode: unknown }).geocode = original;
    }
  });
});

describe('RiskSummary', () => {
  it('shows an empty state before analysis', () => {
    renderWithProviders(<RiskSummary result={null} route={null} units="imperial" />);
    expect(screen.getByText(/analyze the route to see its risk/)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'No score yet' })).toBeInTheDocument();
  });

  it('shows the selected route score, factors and placeholder notice', () => {
    const route = analyzeResponse.routes[0];
    renderWithProviders(<RiskSummary result={analyzeResponse} route={route} units="metric" originLabel="Champaign" destinationLabel="Bloomington" />);
    expect(screen.getByRole('img', { name: 'Risk score 62 out of 100' })).toBeInTheDocument();
    expect(screen.getByTestId('risk-level')).toHaveTextContent('High risk');
    expect(screen.getByText(/12 fatal crashes recorded/)).toBeInTheDocument();
    expect(screen.getByText('Placeholder model')).toBeInTheDocument();
    expect(screen.getByTestId('factor-time')).toHaveTextContent('50%');
    expect(screen.getByText('Interstate')).toBeInTheDocument();
    expect(screen.getByTestId('route-distance')).toHaveTextContent('80 km');
    expect(screen.getByTestId('route-duration')).toHaveTextContent('55 min');
  });
});

describe('RiskOverTime and RiskLegend', () => {
  it('switches between month and hour views', async () => {
    const r = analyzeResponse.routes[0].stats!;
    renderWithProviders(<RiskOverTime byMonth={r.by_month} byHour={r.by_hour} highlightMonths={[12, 1, 2]} />);
    expect(screen.getByText(/by month · selected: Dec, Jan, Feb/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Chart view' }), 'hour');
    await waitFor(() => expect(screen.getByText(/by hour of day/)).toBeInTheDocument());
  });

  it('asks for a route when there is no data', () => {
    renderWithProviders(<RiskOverTime />);
    expect(screen.getByText(/Analyze a route to see when crashes happen/)).toBeInTheDocument();
  });

  it('lists the four risk levels', () => {
    renderWithProviders(<RiskLegend />);
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Low', 'Moderate', 'High', 'Very High']);
  });
});
