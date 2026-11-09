import { expect, test } from '@playwright/test';
import { pickPlace, registerViaApi, signIn } from './helpers';

test.describe('route analyzer', () => {
  test('a guest compares the fastest and safest routes under chosen conditions', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Route Analyzer' })).toBeVisible();
    await expect(page.getByText('Route Risk Level')).toBeVisible();

    await pickPlace(page, 'origin-input', 'Champaign', 'Champaign, IL');
    await pickPlace(page, 'destination-input', 'Chicago', 'Chicago, IL');
    await page.getByLabel('Heavy Rain').check();
    await page.getByLabel(/Time of Day/).selectOption('night');
    await page.getByLabel(/Season \/ Month/).selectOption('winter');
    await page.getByTestId('analyze-button').click();

    for (const option of ['fastest', 'balanced', 'safest']) {
      await expect(page.getByTestId(`option-${option}`)).toBeVisible();
    }
    await expect(page.getByTestId('option-balanced')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('img', { name: /Risk score \d+ out of 100/ })).toBeVisible();
    await expect(page.getByText('Placeholder model')).toBeVisible();
    await expect(page.getByTestId('risk-level')).toHaveText(/(Low|Moderate|High|Very High) risk/);
    await expect(page.getByTestId('route-distance')).toHaveText(/\d+ mi/);
    await expect(page.getByTestId('route-duration')).toHaveText(/\d+ (h|min)/);
    await expect(page.getByTestId('factor-weather')).toContainText('Crashes in rainy weather');
    await expect(page.getByText(/Fatal crashes along the route, by month · selected: Dec, Jan, Feb/)).toBeVisible();
    // the chosen route, the two alternatives and the scored grid cells are drawn on the map
    expect(await page.locator('.leaflet-overlay-pane path').count()).toBeGreaterThan(3);

    await page.getByTestId('option-safest').click();
    await expect(page.getByTestId('option-safest')).toHaveAttribute('aria-pressed', 'true');

    await page.getByRole('combobox', { name: 'Chart view' }).selectOption('hour');
    await expect(page.getByText(/by hour of day/)).toBeVisible();
  });

  test('clicking the map sets the start and destination', async ({ page }) => {
    await page.goto('/');
    const map = page.getByTestId('analyze-map').locator('.leaflet-container');
    await map.click({ position: { x: 200, y: 400 } });
    await map.click({ position: { x: 500, y: 200 } });
    await expect(page.getByTestId('origin-input')).toHaveValue(/^-?\d+\.\d{4}, -?\d+\.\d{4}$/);
    await expect(page.getByTestId('destination-input')).toHaveValue(/^-?\d+\.\d{4}, -?\d+\.\d{4}$/);
    await page.getByTestId('analyze-button').click();
    await expect(page.getByTestId('option-fastest')).toBeVisible();
  });

  test('asks for both places before analyzing', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('analyze-button').click();
    await expect(page.getByRole('alert')).toHaveText('Choose both a starting location and a destination.');
  });

  test('a signed-in analysis is saved to route history with the chosen option', async ({ page, request }) => {
    const user = await registerViaApi(request, 'Route Saver');
    await signIn(page, user);
    await page.goto('/');
    await pickPlace(page, 'origin-input', 'Urbana', 'Urbana, IL');
    await pickPlace(page, 'destination-input', 'Bloomington', 'Bloomington, IL');
    await page.getByTestId('analyze-button').click();
    await page.getByTestId('option-fastest').click();
    await expect(page.getByTestId('option-fastest')).toHaveAttribute('aria-pressed', 'true');

    await page.getByRole('link', { name: 'Saved Routes' }).click();
    const item = page.getByTestId('history-item');
    await expect(item).toHaveCount(1);
    await expect(item.getByText('chosen')).toBeVisible();
    await expect(item.locator('.option-pill.chosen')).toContainText('fastest');

    await item.getByRole('link', { name: 'Open in Analyze' }).click();
    await expect(page.getByTestId('origin-input')).toHaveValue('40.1106, -88.2073');
    await expect(page.getByTestId('destination-input')).toHaveValue('40.4842, -88.9937');

    await page.getByRole('link', { name: 'Saved Routes' }).click();
    await page.getByTestId('history-item').getByRole('button', { name: /Delete route/ }).click();
    await expect(page.getByTestId('history-item')).toHaveCount(0);
  });
});
