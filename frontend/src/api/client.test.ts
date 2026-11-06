import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, getToken, request, setToken, setUnauthorizedHandler } from './client';

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => (body === undefined ? Promise.reject(new Error('no body')) : Promise.resolve(body)),
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

describe('api client', () => {
  beforeEach(() => setToken(null));
  afterEach(() => { vi.unstubAllGlobals(); setUnauthorizedHandler(null); });

  it('sends JSON and the bearer token', async () => {
    const fetchMock = mockFetch(200, { user: { user_id: 1 } });
    setToken('abc');
    await api.updateProfile({ units: 'metric' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/users/me');
    expect(init.method).toBe('PATCH');
    expect(init.headers.Authorization).toBe('Bearer abc');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ units: 'metric' });
  });

  it('builds query strings and skips empty values', async () => {
    const fetchMock = mockFetch(200, { crashes: [], total: 0 });
    await api.searchCrashes({ state_code: 17, weather_group: '', month: null, limit: 50 });
    expect(fetchMock.mock.calls[0][0]).toBe('/api/crashes?state_code=17&limit=50');
  });

  it('turns error bodies into ApiError', async () => {
    mockFetch(409, { error: { code: 'email_taken', message: 'An account with that email already exists' } });
    await expect(api.register('a@b.c', 'password123', 'A')).rejects.toMatchObject({
      status: 409, code: 'email_taken', message: 'An account with that email already exists',
    });
  });

  it('handles 204 and network failures', async () => {
    mockFetch(204);
    await expect(api.deleteLocation(3)).resolves.toBeUndefined();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(request('GET', '/health')).rejects.toMatchObject({ name: 'ApiError', code: 'network' });
  });

  it('calls the unauthorized handler when a stored token is rejected', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setToken('expired');
    mockFetch(401, { error: { code: 'token_expired', message: 'expired' } });
    await expect(api.me()).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledOnce();
  });

  it('does not log out on a wrong password', async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setToken('still-valid');
    mockFetch(401, { error: { code: 'bad_credentials', message: 'Incorrect email or password' } });
    await expect(api.login('a@b.c', 'nope')).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });

  it('persists the token in localStorage', () => {
    setToken('xyz');
    expect(localStorage.getItem('tsra.token')).toBe('xyz');
    expect(getToken()).toBe('xyz');
    setToken(null);
    expect(localStorage.getItem('tsra.token')).toBeNull();
  });

  it('serialises the route analysis request', async () => {
    const fetchMock = mockFetch(200, {});
    await api.analyzeRoute({ label: 'A', lat: 40.1, lon: -88.2 }, { label: 'B', lat: 41.8, lon: -87.6 },
      { weather: 'wet', time_of_day: 'night', season: 'winter' }, 0.7);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      origin: { lat: 40.1, lon: -88.2 }, destination: { lat: 41.8, lon: -87.6 },
      conditions: { weather: 'wet', time_of_day: 'night', season: 'winter' }, safety_weight: 0.7,
    });
  });
});
