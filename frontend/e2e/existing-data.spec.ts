import { expect, test } from '@playwright/test';
import { ADMIN, loginViaApi, pickPlace, signIn } from './helpers';

// These run only against a database that already holds data (E2E_SEED=0), such as a local copy of the
// Cloud SQL export. They check that the app copes with the full crash history and the team's records.
test.describe('existing data', () => {
  test.skip(process.env.E2E_SEED !== '0', 'needs E2E_SEED=0 and a local copy of the real database');

  test('every crash year can be searched, and the totals match the API', async ({ page, request }) => {
    const lookups = await (await request.get('/api/lookups')).json();
    const illinois = lookups.states.find((s: { state_name: string }) => s.state_name === 'Illinois');
    expect(lookups.years.length).toBeGreaterThan(0);

    await page.goto('/search');
    await page.getByLabel('State / county').check();
    await page.getByLabel('State', { exact: true }).selectOption({ label: 'Illinois' });
    for (const year of lookups.years as number[]) {
      const api = await (await request.get('/api/crashes', { params: { state_code: illinois.state_code, year, limit: 1 } })).json();
      await page.getByLabel('Year').selectOption(String(year));
      await page.getByTestId('search-button').click();
      await expect(page.getByTestId('result-total')).toHaveText(api.total.toLocaleString('en-US'));
      await expect(page.locator('.data-table tbody tr').first()).toContainText(String(year));
    }
  });

  test('existing reports are listed and an admin can moderate one', async ({ page, request }) => {
    const admin = await loginViaApi(request, ADMIN.email, ADMIN.password);
    await signIn(page, admin);
    await page.goto('/reports');
    const cards = page.getByTestId('report-item');
    await expect(cards.first()).toBeVisible();
    expect(await cards.count()).toBeGreaterThan(10);

    const card = cards.filter({ has: page.locator('.badge', { hasText: /^active$/ }) }).first();
    const select = card.getByRole('combobox', { name: /Moderate report/ });
    const reportId = Number((await select.getAttribute('aria-label'))!.replace(/\D/g, ''));
    await select.selectOption('removed');
    await expect(page.getByRole('combobox', { name: `Moderate report ${reportId}` })).toHaveValue('removed');

    // guests no longer see it
    const visible = (await (await request.get('/api/reports', { params: { limit: 500 } })).json()).reports as { report_id: number }[];
    expect(visible.some((r) => r.report_id === reportId)).toBe(false);
  });

  test('long multi-state trips are analyzed, and trips over the limit are explained', async ({ page }) => {
    const trip = async (from: string, to: string) => {
      await page.goto('/');
      await pickPlace(page, 'origin-input', from.split(',')[0], from);
      await pickPlace(page, 'destination-input', to.split(',')[0], to);
      await page.getByTestId('analyze-button').click();
    };
    for (const [from, to] of [['Chicago, IL', 'Atlanta, GA'], ['Boston, MA', 'Philadelphia, PA']]) {
      await trip(from, to);
      await expect(page.getByTestId('option-safest')).toBeVisible({ timeout: 30_000 });
      await expect(page.getByRole('img', { name: /Risk score \d+ out of 100/ })).toBeVisible();
      await expect(page.getByTestId('route-distance')).toHaveText(/[\d,]+ mi/);
    }
    await trip('Chicago, IL', 'Los Angeles, CA');
    await expect(page.getByRole('alert')).toHaveText('Trips longer than 1500 km are not supported');
  });
});
