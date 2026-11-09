import { expect, test } from '@playwright/test';
import { ADMIN, loginViaApi, pickPlace, registerViaApi, signIn } from './helpers';

test.describe('community reports', () => {
  test('post, vote, moderate and remove a report', async ({ browser, request }) => {
    const author = await registerViaApi(request, 'Report Author');
    const voter = await registerViaApi(request, 'Report Voter');
    const admin = await loginViaApi(request, ADMIN.email, ADMIN.password);
    const reason = `Black ice on the overpass ${Date.now()}`;

    // the author posts and edits a report
    const authorPage = await (await browser.newContext()).newPage();
    await signIn(authorPage, author);
    await authorPage.goto('/reports');
    await pickPlace(authorPage, 'report-place', '40.11, -88.21', '40.11000, -88.21000');
    await authorPage.getByLabel('What happened?').fill(reason);
    await authorPage.getByTestId('submit-report').click();
    const mine = authorPage.getByTestId('report-item').filter({ hasText: reason });
    await expect(mine).toContainText('counts toward risk');
    await expect(mine.getByRole('button', { name: /Confirm/ })).toHaveCount(0);   // cannot vote on your own
    await mine.getByRole('button', { name: /Edit/ }).click();
    await authorPage.getByLabel('Edit report').fill(`${reason} (cleared lane 2)`);
    await authorPage.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(authorPage.getByTestId('report-item').filter({ hasText: 'cleared lane 2' })).toBeVisible();

    // another user flags it, then confirms it instead
    const voterPage = await (await browser.newContext()).newPage();
    await signIn(voterPage, voter);
    await voterPage.goto('/reports');
    const card = voterPage.getByTestId('report-item').filter({ hasText: reason });
    await card.getByRole('button', { name: /Flag/ }).click();
    await expect(card).toContainText('1 flag');
    await expect(card).not.toContainText('counts toward risk');
    await card.getByRole('button', { name: /Confirm/ }).click();
    await expect(card).toContainText('1 confirm, 0 flags · counts toward risk');

    // an admin removes it; it disappears for everyone else
    const adminPage = await (await browser.newContext()).newPage();
    await signIn(adminPage, admin);
    await adminPage.goto('/reports');
    const adminCard = adminPage.getByTestId('report-item').filter({ hasText: reason });
    const moderate = adminCard.getByRole('combobox', { name: /Moderate report/ });
    await moderate.selectOption('removed');
    await expect(adminCard.locator('.badge')).toHaveText('removed');

    await voterPage.reload();
    await expect(voterPage.getByTestId('report-item').filter({ hasText: reason })).toHaveCount(0);
    await authorPage.reload();
    const removed = authorPage.getByTestId('report-item').filter({ hasText: reason });
    await expect(removed.locator('.badge')).toHaveText('removed');
    await expect(removed.getByRole('button', { name: /Edit/ })).toHaveCount(0);

    // the admin deletes it outright
    await adminCard.getByRole('button', { name: /Delete report/ }).click();
    await expect(adminPage.getByTestId('report-item').filter({ hasText: reason })).toHaveCount(0);
  });

  test('guests can read reports but not post', async ({ page }) => {
    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Report a crash or hazard' })).toBeVisible();
    await expect(page.getByTestId('submit-report')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible();
  });
});
