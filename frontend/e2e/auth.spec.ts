import { expect, test } from '@playwright/test';
import { uniqueEmail } from './helpers';

test.describe('accounts', () => {
  test('create an account, sign out, and sign back in', async ({ page }) => {
    const email = uniqueEmail('signup');
    await page.goto('/profile');
    await page.getByRole('tab', { name: 'Create account' }).click();
    await page.getByLabel('Name').fill('Sree Vinay');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page).toHaveURL('/');
    const profileButton = page.getByRole('button', { name: /Sree Vinay/ });
    await expect(profileButton).toBeVisible();

    await profileButton.click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await expect(page.getByRole('button', { name: /Profile/ })).toBeVisible();

    await page.goto('/profile');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('button', { name: /Sree Vinay/ })).toBeVisible();

    // the session survives a reload
    await page.reload();
    await expect(page.getByRole('button', { name: /Sree Vinay/ })).toBeVisible();
  });

  test('wrong password and duplicate email are explained', async ({ page, request }) => {
    const email = uniqueEmail('dup');
    await request.post('/api/auth/register', { data: { email, password: 'password123', display_name: 'First' } });

    await page.goto('/profile');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill('not-the-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toHaveText('Incorrect email or password');

    await page.getByRole('tab', { name: 'Create account' }).click();
    await page.getByLabel('Name').fill('Second');
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: 'Create account' }).click();
    await expect(page.getByRole('alert')).toHaveText('An account with that email already exists');
  });

  test('signed-out visitors are asked to sign in for personal pages', async ({ page }) => {
    await page.goto('/saved');
    await expect(page.getByRole('heading', { name: /Sign in to see your saved routes/ })).toBeVisible();
    await page.getByRole('link', { name: /Sign in or create an account/ }).click();
    await expect(page).toHaveURL('/profile');
  });
});
