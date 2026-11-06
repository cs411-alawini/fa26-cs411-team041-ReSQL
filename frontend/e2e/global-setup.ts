import { execFileSync } from 'node:child_process';
import { backendEnv, E2E } from '../playwright.config';
import { ADMIN } from './helpers';

/**
 * Reload the local e2e database with the Illinois demo data, then make sure the admin account exists.
 * With E2E_SEED=0 the data is left as it is (for example a local copy of the Cloud SQL export) and
 * only the admin account is added.
 */
export default function globalSetup() {
  const env = { ...process.env, ...backendEnv };
  const flask = (...args: string[]) =>
    execFileSync(E2E.python, ['-m', 'flask', '--app', 'wsgi', ...args], { cwd: E2E.backendDir, env, stdio: 'pipe' }).toString();
  if (process.env.E2E_SEED !== '0') {
    // init-db refuses to run against anything but a local MySQL host.
    console.log(flask('init-db', '--drop', '--demo').trim());
  }
  console.log(flask('create-admin', '--email', ADMIN.email, '--password', ADMIN.password, '--name', 'E2E Admin').trim());
}
