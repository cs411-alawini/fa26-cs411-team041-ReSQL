import { expect, test } from '@playwright/test';
import { pickPlace, registerViaApi, signIn } from './helpers';

test.describe('search & lookup', () => {
  test('search crashes by state and conditions, then open one', async ({ page }) => {
    await page.goto('/search');
    await page.getByLabel('State / county').check();
    await page.getByLabel('State', { exact: true }).selectOption({ label: 'Illinois' });
    await page.getByLabel('Light').selectOption('dark');
    await page.getByTestId('search-button').click();

    const total = page.getByTestId('result-total');
    await expect(total).toHaveText(/^[1-9][\d,]*$/);
    const rows = page.locator('.data-table tbody tr');
    expect(await rows.count()).toBeGreaterThan(0);
    await expect(rows.first()).toContainText('Illinois');
    await expect(rows.first()).toContainText(/Dark/);

    await rows.first().click();
    const drawer = page.getByRole('dialog');
    await expect(drawer).toContainText('Weather station that day');
    await expect(drawer).toContainText('Reported weather');
    await drawer.getByRole('button', { name: 'Close' }).click();
    await expect(drawer).toHaveCount(0);

    // narrow to one county
    await page.getByLabel('County', { exact: true }).selectOption({ label: 'Champaign' });
    await page.getByTestId('search-button').click();
    await expect(rows.first()).toContainText('Champaign, Illinois');
  });

  test('search the current map view', async ({ page }) => {
    await page.goto('/search');            // the map opens on Champaign-Urbana
    await page.getByTestId('search-button').click();
    await expect(page.getByTestId('result-total')).toHaveText(/^[1-9][\d,]*$/);
    expect(await page.locator('.leaflet-overlay-pane path').count()).toBeGreaterThan(0);
  });
});

test.describe('profile and preferences', () => {
  test('units preference changes how distances are shown', async ({ page, request }) => {
    const user = await registerViaApi(request, 'Metric Fan');
    await signIn(page, user);
    await page.goto('/profile');
    await page.getByLabel('Kilometres').check();
    await page.getByRole('button', { name: 'Save preferences' }).click();
    await expect(page.getByRole('status')).toHaveText('Preferences saved.');

    await page.getByRole('link', { name: 'Analyze', exact: true }).click();
    await pickPlace(page, 'origin-input', 'Champaign', 'Champaign, IL');
    await pickPlace(page, 'destination-input', 'Peoria', 'Peoria, IL');
    await page.getByTestId('analyze-button').click();
    await expect(page.getByTestId('route-distance')).toHaveText(/\d+ km/);
  });

  test('change password, then delete the account', async ({ page, request }) => {
    const user = await registerViaApi(request, 'Short Lived');
    await signIn(page, user);
    await page.goto('/profile');
    await page.getByLabel('Current password').fill(user.password);
    await page.getByLabel('New password').fill('newpassword456');
    await page.getByRole('button', { name: 'Change password' }).click();
    await expect(page.getByRole('status')).toHaveText('Password changed.');
    const relogin = await request.post('/api/auth/login', { data: { email: user.user.email, password: 'newpassword456' } });
    expect(relogin.status()).toBe(200);

    await page.getByRole('button', { name: 'Delete account' }).click();
    await page.getByRole('button', { name: 'Yes, delete my account' }).click();
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('button', { name: /Profile/ })).toBeVisible();
    const gone = await request.post('/api/auth/login', { data: { email: user.user.email, password: 'newpassword456' } });
    expect(gone.status()).toBe(401);
  });

  test('dark mode is remembered across reloads', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Switch to dark mode' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByRole('button', { name: 'Switch to light mode' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });
});
