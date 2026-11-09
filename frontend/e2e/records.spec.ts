import { expect, test } from '@playwright/test';
import { ADMIN, authHeaders, loginViaApi, pickPlace, registerViaApi, signIn } from './helpers';

test.describe('saved locations, subscriptions and alerts', () => {
  test('save, rename and reuse a location, then subscribe to it', async ({ page, request }) => {
    const user = await registerViaApi(request, 'Location Keeper');
    await signIn(page, user);
    await page.goto('/saved');
    await page.getByRole('tab', { name: 'Saved locations' }).click();

    await pickPlace(page, 'location-place', 'Urbana', 'Urbana, IL');
    await page.getByLabel('Name').fill('Home');
    await page.getByRole('button', { name: 'Save location' }).click();
    const item = page.getByTestId('location-item');
    await expect(item).toHaveCount(1);
    await expect(item).toContainText('Home');

    await item.getByRole('button', { name: 'Rename Home' }).click();
    await page.getByLabel('New name').fill('House');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByTestId('location-item')).toContainText('House');

    // the saved place is offered as a shortcut on the Analyze page
    await page.getByRole('link', { name: 'Analyze', exact: true }).click();
    await page.getByTestId('origin-input').click();
    await expect(page.getByRole('option').filter({ hasText: 'House' })).toBeVisible();

    await page.getByRole('link', { name: 'Saved Routes' }).click();
    await page.getByRole('tab', { name: 'Alerts & subscriptions' }).click();
    await page.getByLabel('Location').selectOption({ label: 'House' });
    await page.getByLabel('Condition').selectOption({ label: 'Rain · Dark' });
    await page.getByLabel(/Alert when the score changes/).fill('15');
    await page.getByRole('button', { name: 'Subscribe' }).click();
    const sub = page.getByTestId('subscription-item');
    await expect(sub).toHaveCount(1);
    await expect(sub).toContainText('Rain · Dark · alert at ±15');

    await sub.getByRole('button', { name: 'Pause' }).click();
    await expect(sub.getByRole('button', { name: 'Resume' })).toBeVisible();

    // duplicate subscriptions are rejected with an explanation
    await page.getByLabel('Location').selectOption({ label: 'House' });
    await page.getByLabel('Condition').selectOption({ label: 'Rain · Dark' });
    await page.getByRole('button', { name: 'Subscribe' }).click();
    await expect(page.getByRole('alert')).toHaveText('You already watch this location under that condition');

    await sub.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByTestId('subscription-item')).toHaveCount(0);
  });

  test('a burst of reports raises a watched location and the admin alert job notifies the owner', async ({ page, request }) => {
    const owner = await registerViaApi(request, 'Watcher');
    const reporter = await registerViaApi(request, 'Reporter');
    // A cell in open water on Lake Michigan, so it has no crash history and its baseline score is 0.
    // A different cell each run, so the test also works on a database that is not reloaded (E2E_SEED=0).
    const lat = 42.505 + Math.floor(Math.random() * 10) / 10;
    const lon = -87.395 + Math.floor(Math.random() * 6) / 10;
    try {
      const loc = await request.post('/api/locations', { headers: authHeaders(owner), data: { label: 'Lakefront', lat, lon } });
      const { location } = await loc.json();
      const profiles = (await (await request.get('/api/lookups')).json()).condition_profiles as { condition_id: number; weather_group: string; light_group: string }[];
      const wetDay = profiles.find((p) => p.weather_group === 'wet' && p.light_group === 'day')!;
      const subRes = await request.post('/api/subscriptions', { headers: authHeaders(owner),
        data: { location_id: location.location_id, condition_id: wetDay.condition_id, alert_threshold: 10 } });
      expect((await subRes.json()).subscription.baseline_score).toBe(0);
      for (let i = 0; i < 3; i += 1) {
        const r = await request.post('/api/reports', { headers: authHeaders(reporter),
          data: { lat: lat - 0.004 + i / 1000, lon: lon - 0.004, reason: `Flooded lane ${i + 1}` } });
        expect(r.status()).toBe(201);
      }

      const admin = await loginViaApi(request, ADMIN.email, ADMIN.password);
      await signIn(page, admin);
      await page.goto('/saved');
      await page.getByRole('tab', { name: 'Alerts & subscriptions' }).click();
      await page.getByRole('button', { name: 'Run alert job now' }).click();
      await expect(page.getByText(/Checked \d+ subscriptions, sent [1-9]\d* alerts\./)).toBeVisible();

      const alerts = await (await request.get('/api/alerts', { headers: authHeaders(owner) })).json();
      expect(alerts.alerts).toHaveLength(1);
      expect(alerts.alerts[0].location_label).toBe('Lakefront');
      expect(alerts.alerts[0].risk_score_at_send).toBeGreaterThan(10);
    } finally {
      // deleting the accounts removes their reports, location, subscription and alerts
      for (const user of [reporter, owner]) await request.delete('/api/users/me', { headers: authHeaders(user) });
    }
  });
});
