import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const ADMIN = { email: 'admin@e2e.test', password: 'adminpass123' };

let counter = 0;
export function uniqueEmail(prefix = 'user'): string {
  counter += 1;
  return `${prefix}.${Date.now()}.${counter}@e2e.test`;
}

export interface TestUser {
  token: string;
  user: { user_id: number; email: string; display_name: string; role: string };
  password: string;
}

export async function registerViaApi(request: APIRequestContext, name = 'Test User', prefix = 'user'): Promise<TestUser> {
  const password = 'password123';
  const res = await request.post('/api/auth/register', { data: { email: uniqueEmail(prefix), password, display_name: name } });
  expect(res.status(), await res.text()).toBe(201);
  return { ...(await res.json()), password };
}

export async function loginViaApi(request: APIRequestContext, email: string, password: string): Promise<TestUser> {
  const res = await request.post('/api/auth/login', { data: { email, password } });
  expect(res.status(), await res.text()).toBe(200);
  return { ...(await res.json()), password };
}

/** Start the browser session already signed in as this user. */
export async function signIn(page: Page, user: TestUser): Promise<void> {
  await page.addInitScript((token) => window.localStorage.setItem('tsra.token', token), user.token);
}

export function authHeaders(user: TestUser) {
  return { Authorization: `Bearer ${user.token}` };
}

/** Type into a PlaceInput and pick a suggestion (the backend runs the offline geocoder in e2e). */
export async function pickPlace(page: Page, testId: string, query: string, label: string): Promise<void> {
  await page.getByTestId(testId).fill(query);
  await page.getByRole('option').getByRole('button', { name: label, exact: true }).click();
  await expect(page.getByTestId(testId)).toHaveValue(label);
}
