import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

// End-to-end tests: a real browser drives the real React app, Flask API and a LOCAL MySQL database.
// The database named by E2E_DB_NAME (default resql_e2e) is dropped and reloaded with the Illinois
// demo data before the run, unless E2E_SEED=0. Never point these settings at Cloud SQL.
// The backend's Python: E2E_PYTHON if set, else backend/.venv (as in SETUP.md), else the one on PATH.
const backendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'backend');
const venvPython = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');
const python = process.env.E2E_PYTHON
  ? path.resolve(process.env.E2E_PYTHON)
  : existsSync(venvPython) ? venvPython : (process.platform === 'win32' ? 'python' : 'python3');
const API_PORT = Number(process.env.E2E_API_PORT ?? 5055);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5174);

export const dbEnv = {
  DB_HOST: process.env.E2E_DB_HOST ?? '127.0.0.1',
  DB_PORT: process.env.E2E_DB_PORT ?? '3306',
  DB_USER: process.env.E2E_DB_USER ?? 'resql',
  DB_PASSWORD: process.env.E2E_DB_PASSWORD ?? '',
  DB_NAME: process.env.E2E_DB_NAME ?? 'resql_e2e',
};

export const backendEnv = {
  ...dbEnv,
  JWT_SECRET: 'e2e-secret',
  // Offline providers keep the tests deterministic and independent of external services.
  ROUTING_PROVIDER: 'offline',
  GEOCODER: 'offline',
  WEATHER_PROVIDER: 'offline',
  CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
};

export const E2E = { python, backendDir, API_PORT, WEB_PORT };

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1536, height: 1024 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1536, height: 1024 } } }],
  webServer: [
    {
      command: `"${python}" -m flask --app wsgi run --port ${API_PORT}`,   // quoted: the repo path may contain spaces
      cwd: backendDir,
      env: backendEnv,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      env: { VITE_API_PROXY: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
