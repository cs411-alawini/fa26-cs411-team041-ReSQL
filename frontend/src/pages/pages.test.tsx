import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, testUser } from '../test/utils';
import { analyzeResponse, makeReport } from '../test/fixtures';

// Leaflet cannot lay out a map in jsdom; the map is covered by the Playwright tests instead.
vi.mock('../components/MapView', () => ({
  default: ({ overlay, onMapClick }: { overlay?: React.ReactNode; onMapClick?: (lat: number, lon: number) => void }) => (
    <div data-testid="map">
      {overlay}
      <button type="button" onClick={() => onMapClick?.(40.5, -88.5)}>fake map click</button>
    </div>
  ),
  pinIcon: () => ({}),
}));

vi.mock('../api/client', async (orig) => {
  const actual = await orig<typeof import('../api/client')>();
  const fn = () => vi.fn();
  return {
    ...actual,
    api: {
      locations: fn(), geocode: fn(), analyzeRoute: fn(), chooseRouteOption: fn(), routeHistory: fn(), deleteRoute: fn(),
      createLocation: fn(), updateLocation: fn(), deleteLocation: fn(), subscriptions: fn(), alerts: fn(), lookups: fn(),
      createSubscription: fn(), updateSubscription: fn(), deleteSubscription: fn(), runAlerts: fn(), reports: fn(),
      createReport: fn(), updateReport: fn(), deleteReport: fn(), vote: fn(), unvote: fn(), moderate: fn(),
      searchCrashes: fn(), crashStats: fn(), crashDetail: fn(), counties: fn(), updateProfile: fn(), deleteAccount: fn(),
    },
  };
});

import { api, ApiError } from '../api/client';
import AnalyzePage from './AnalyzePage';
import ProfilePage from './ProfilePage';
import ReportsPage from './ReportsPage';
import SavedRoutesPage from './SavedRoutesPage';
import SearchPage from './SearchPage';

const m = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

beforeEach(() => {
  Object.values(m).forEach((f) => f.mockReset());
  m.locations.mockResolvedValue({ locations: [] });
  m.lookups.mockResolvedValue({
    weather_conditions: [], light_conditions: [], road_classes: [{ func_sys_code: 1, description: 'Interstate' }],
    condition_profiles: [{ condition_id: 4, weather_group: 'wet', light_group: 'dark', national_est_crashes: 1, national_serious_fatal_pct: 3 }],
    states: [{ state_code: 17, state_name: 'Illinois' }], years: [2024],
  });
  m.chooseRouteOption.mockResolvedValue({});
});

describe('AnalyzePage', () => {
  it('needs both places before analyzing', async () => {
    renderWithProviders(<AnalyzePage />);
    await userEvent.click(screen.getByTestId('analyze-button'));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose both a starting location and a destination.');
    expect(m.analyzeRoute).not.toHaveBeenCalled();
  });

  it('sends the selected conditions and shows the recommended option', async () => {
    m.analyzeRoute.mockResolvedValue(analyzeResponse);
    renderWithProviders(<AnalyzePage />, { user: testUser, route: '/?from=40.1164,-88.2434&to=40.4842,-88.9937' });
    await userEvent.click(screen.getByLabelText('Heavy Rain'));
    await userEvent.selectOptions(screen.getByLabelText(/Time of Day/), 'night');
    await userEvent.selectOptions(screen.getByLabelText(/Season \/ Month/), 'winter');
    await userEvent.click(screen.getByTestId('analyze-button'));

    await waitFor(() => expect(m.analyzeRoute).toHaveBeenCalledOnce());
    const [origin, dest, conditions] = m.analyzeRoute.mock.calls[0];
    expect([origin.lat, origin.lon, dest.lat, dest.lon]).toEqual([40.1164, -88.2434, 40.4842, -88.9937]);
    expect(conditions).toMatchObject({ weather: 'wet', time_of_day: 'night', season: 'winter' });

    expect(await screen.findByTestId('option-balanced')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('risk-level')).toHaveTextContent('Low risk');      // balanced = route 1
    await userEvent.click(screen.getByTestId('option-fastest'));
    expect(screen.getByTestId('risk-level')).toHaveTextContent('High risk');
    expect(m.chooseRouteOption).toHaveBeenCalledWith(42, 'fastest');
  });

  it('fills the start and destination from map clicks and shows API errors', async () => {
    m.analyzeRoute.mockRejectedValue(new ApiError(422, 'no_route', 'No drivable route was found between those points'));
    renderWithProviders(<AnalyzePage />);
    await userEvent.click(screen.getByText('fake map click'));
    await userEvent.click(screen.getByText('fake map click'));
    expect(screen.getByTestId('origin-input')).toHaveValue('40.5000, -88.5000');
    expect(screen.getByTestId('destination-input')).toHaveValue('40.5000, -88.5000');
    await userEvent.click(screen.getByTestId('analyze-button'));
    expect(await screen.findByRole('alert')).toHaveTextContent('No drivable route');
  });
});

describe('SavedRoutesPage', () => {
  it('asks signed-out visitors to sign in', () => {
    renderWithProviders(<SavedRoutesPage />);
    expect(screen.getByRole('link', { name: /Sign in or create an account/ })).toHaveAttribute('href', '/profile');
  });

  it('lists route history and deletes a route', async () => {
    m.routeHistory.mockResolvedValue({ routes: [{
      route_id: 5, origin_lat: 40.1, origin_lon: -88.2, dest_lat: 41.8, dest_lon: -87.6, chosen_option: 'safest',
      requested_at: '2026-11-04T20:00:00Z',
      options: [{ option_type: 'safest', travel_time_s: 9000, risk_score: 12, risk_level: 'low' }],
    }] });
    m.deleteRoute.mockResolvedValue(undefined);
    renderWithProviders(<SavedRoutesPage />, { user: testUser });
    const item = await screen.findByTestId('history-item');
    expect(within(item).getByText(/chosen/)).toBeInTheDocument();
    expect(within(item).getByRole('link', { name: 'Open in Analyze' })).toHaveAttribute('href', '/?from=40.1,-88.2&to=41.8,-87.6');
    await userEvent.click(within(item).getByRole('button', { name: 'Delete route 5' }));
    expect(m.deleteRoute).toHaveBeenCalledWith(5);
  });

  it('adds, renames and deletes saved locations', async () => {
    m.routeHistory.mockResolvedValue({ routes: [] });
    const home = { location_id: 3, label: 'Home', latitude: 40.5, longitude: -88.5, created_at: '', subscriptions: 0, cell_id: '405_-885' };
    m.locations.mockResolvedValueOnce({ locations: [] }).mockResolvedValue({ locations: [home] });
    m.createLocation.mockResolvedValue({ location: home });
    m.updateLocation.mockResolvedValue({ location: { ...home, label: 'House' } });
    m.deleteLocation.mockResolvedValue(undefined);
    renderWithProviders(<SavedRoutesPage />, { user: testUser });
    await userEvent.click(screen.getByRole('tab', { name: 'Saved locations' }));
    await userEvent.click(screen.getByText('fake map click'));
    await userEvent.type(screen.getByLabelText('Name'), 'Home');
    await userEvent.click(screen.getByRole('button', { name: 'Save location' }));
    expect(m.createLocation).toHaveBeenCalledWith('Home', 40.5, -88.5);
    await userEvent.click(await screen.findByRole('button', { name: 'Rename Home' }));
    const input = screen.getByLabelText('New name');
    await userEvent.clear(input);
    await userEvent.type(input, 'House');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(m.updateLocation).toHaveBeenCalledWith(3, { label: 'House' });
    await userEvent.click(screen.getByRole('button', { name: 'Delete Home' }));
    expect(m.deleteLocation).toHaveBeenCalledWith(3);
  });

  it('creates a subscription and lets admins run the alert job', async () => {
    m.routeHistory.mockResolvedValue({ routes: [] });
    m.locations.mockResolvedValue({ locations: [{ location_id: 3, label: 'Home', latitude: 40.5, longitude: -88.5, created_at: '', subscriptions: 0, cell_id: '405_-885' }] });
    m.subscriptions.mockResolvedValue({ subscriptions: [] });
    m.alerts.mockResolvedValue({ alerts: [] });
    m.createSubscription.mockResolvedValue({});
    m.runAlerts.mockResolvedValue({ checked: 2, alerts_created: 1 });
    renderWithProviders(<SavedRoutesPage />, { user: { ...testUser, role: 'admin' } });
    await userEvent.click(screen.getByRole('tab', { name: 'Alerts & subscriptions' }));
    await userEvent.selectOptions(await screen.findByLabelText('Location'), '3');
    await userEvent.selectOptions(screen.getByLabelText('Condition'), '4');
    await userEvent.click(screen.getByRole('button', { name: 'Subscribe' }));
    expect(m.createSubscription).toHaveBeenCalledWith(3, 4, 10);
    await userEvent.click(screen.getByRole('button', { name: 'Run alert job now' }));
    expect(await screen.findByText('Checked 2 subscriptions, sent 1 alerts.')).toBeInTheDocument();
  });
});

describe('ReportsPage', () => {
  it('lets visitors read reports but not post', async () => {
    m.reports.mockResolvedValue({ reports: [makeReport()] });
    renderWithProviders(<ReportsPage />);
    expect(await screen.findByText('Black ice')).toBeInTheDocument();
    expect(screen.queryByTestId('submit-report')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm/ })).not.toBeInTheDocument();
  });

  it('submits a report at the clicked point', async () => {
    m.reports.mockResolvedValue({ reports: [] });
    m.createReport.mockResolvedValue({});
    renderWithProviders(<ReportsPage />, { user: testUser });
    await userEvent.click(screen.getByText('fake map click'));
    await userEvent.type(screen.getByLabelText('What happened?'), 'Debris on the road');
    await userEvent.click(screen.getByTestId('submit-report'));
    expect(m.createReport).toHaveBeenCalledWith(40.5, -88.5, 'Debris on the road');
  });

  it('votes on other people\'s reports and edits your own', async () => {
    m.reports.mockResolvedValue({ reports: [makeReport(), makeReport({ report_id: 2, user_id: testUser.user_id, author: 'Vinay', reason: 'Pothole' })] });
    m.vote.mockResolvedValue({});
    m.updateReport.mockResolvedValue({});
    renderWithProviders(<ReportsPage />, { user: testUser });
    const [theirs, mine] = await screen.findAllByTestId('report-item');
    await userEvent.click(within(theirs).getByRole('button', { name: /Flag/ }));
    expect(m.vote).toHaveBeenCalledWith(1, -1);
    expect(within(theirs).queryByRole('button', { name: /Edit/ })).not.toBeInTheDocument();
    await userEvent.click(within(mine).getByRole('button', { name: /Mark resolved/ }));
    expect(m.updateReport).toHaveBeenCalledWith(2, { status: 'resolved' });
    expect(within(mine).queryByRole('button', { name: /Flag/ })).not.toBeInTheDocument();
  });

  it('gives admins a moderation control', async () => {
    m.reports.mockResolvedValue({ reports: [makeReport()] });
    m.moderate.mockResolvedValue({});
    renderWithProviders(<ReportsPage />, { user: { ...testUser, role: 'admin' } });
    await userEvent.selectOptions(await screen.findByLabelText('Moderate report 1'), 'removed');
    expect(m.moderate).toHaveBeenCalledWith(1, 'removed');
  });
});

describe('SearchPage', () => {
  it('searches by state and opens a crash', async () => {
    m.counties.mockResolvedValue({ counties: [{ county_code: 19, county_name: 'Champaign' }] });
    const crash = { data_year: 2024, st_case: 170001, latitude: 40.1, longitude: -88.2, crash_date: '2024-01-15', crash_hour: 22,
      crash_minute: 30, fatalities: 1, persons_involved: 2, vehicles_involved: 1, weather: 'Rain', weather_group: 'wet',
      light: 'Dark - Not Lighted', light_group: 'dark', road_class: 'Interstate', cell_id: '401_-883', state_name: 'Illinois', county_name: 'Champaign' };
    m.searchCrashes.mockResolvedValue({ crashes: [crash], total: 1, limit: 50, offset: 0 });
    m.crashStats.mockResolvedValue({ crashes: 1, fatalities: 1, by_weather_group: [{ weather_group: 'wet', crashes: 1, fatalities: 1 }],
      by_light_group: [], by_road_class: [], by_month: [], by_hour: [],
      station_weather: { crashes_with_station: 1, on_wet_days: 1, on_snow_days: 0, avg_temp_max_c: 3.3 } });
    m.crashDetail.mockResolvedValue({ crash: { ...crash, weather_station_id: 'USW1', rural_urban: 2, county_code: 19, state_code: 17 },
      station_weather: { station_id: 'USW1', station_name: 'WILLARD AP', latitude: 40, longitude: -88, precipitation_mm: 12.7,
        snowfall_mm: 0, snow_depth_mm: 0, temp_max_c: 3.3, temp_min_c: -1.1, avg_wind_ms: 4.5 }, vehicles: [], people: [] });
    renderWithProviders(<SearchPage />);
    await userEvent.click(screen.getByLabelText('State / county'));
    await userEvent.selectOptions(await screen.findByLabelText('State'), '17');
    await userEvent.selectOptions(screen.getByLabelText('Weather'), 'wet');
    await userEvent.click(screen.getByTestId('search-button'));
    await waitFor(() => expect(m.searchCrashes).toHaveBeenCalled());
    expect(m.searchCrashes.mock.calls[0][0]).toMatchObject({ state_code: '17', weather_group: 'wet', limit: 50, offset: 0 });
    expect(await screen.findByTestId('result-total')).toHaveTextContent('1');
    expect(screen.getByText('100%')).toBeInTheDocument();          // rain at the nearest station
    await userEvent.click(screen.getByRole('cell', { name: 'Interstate' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('WILLARD AP');
  });
});

describe('ProfilePage', () => {
  it('signs in', async () => {
    const login = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<ProfilePage />, { auth: { login } });
    await userEvent.type(screen.getByLabelText('Email'), 'vinay@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(login).toHaveBeenCalledWith('vinay@example.com', 'password123');
  });

  it('shows sign-in errors', async () => {
    const login = vi.fn().mockRejectedValue(new Error('Incorrect email or password'));
    renderWithProviders(<ProfilePage />, { auth: { login } });
    await userEvent.type(screen.getByLabelText('Email'), 'vinay@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpass1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password');
  });

  it('creates an account', async () => {
    const register = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<ProfilePage />, { auth: { register } });
    await userEvent.click(screen.getByRole('tab', { name: 'Create account' }));
    await userEvent.type(screen.getByLabelText('Name'), 'Vinay');
    await userEvent.type(screen.getByLabelText('Email'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(register).toHaveBeenCalledWith('new@example.com', 'password123', 'Vinay');
  });

  it('saves preferences and deletes the account after confirmation', async () => {
    const setUser = vi.fn();
    const logout = vi.fn();
    m.updateProfile.mockResolvedValue({ user: { ...testUser, units: 'metric' } });
    m.deleteAccount.mockResolvedValue(undefined);
    renderWithProviders(<ProfilePage />, { user: testUser, auth: { setUser, logout } });
    await userEvent.click(screen.getByLabelText('Kilometres'));
    await userEvent.click(screen.getByRole('button', { name: 'Save preferences' }));
    expect(m.updateProfile).toHaveBeenCalledWith({ display_name: 'Vinay Ravuru', safety_weight: 0.5, units: 'metric' });
    expect(setUser).toHaveBeenCalled();
    expect(await screen.findByText('Preferences saved.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Delete account' }));
    await userEvent.click(screen.getByRole('button', { name: 'Yes, delete my account' }));
    expect(m.deleteAccount).toHaveBeenCalled();
    await waitFor(() => expect(logout).toHaveBeenCalled());
  });
});
