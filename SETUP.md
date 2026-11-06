# Traffic Safety Risk Analyzer: running the app

React (Vite + TypeScript) frontend, Flask API, MySQL 8 (Google Cloud SQL in production).

```
backend/    Flask API (app/), tests (tests/), scripts/smoke_test.py, requirements*.txt
frontend/   React app (src/), unit tests (*.test.ts[x]), browser tests (e2e/)
database/   schema.sql, triggers.sql, views.sql, seed_lookups.sql, demo_seed.sql, loader/load_data.py
```

## 1. Backend

Needs Python 3.10 or newer (tested on 3.10.8 and 3.13).

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

Edit `backend/.env` with the database settings (next section), then:

```powershell
flask --app wsgi run              # API on http://127.0.0.1:5000
```

Check it with http://127.0.0.1:5000/api/health.

### Connecting to Cloud SQL

1. Install and log in to the Google Cloud CLI (`gcloud auth application-default login`).
2. Download the Cloud SQL Auth Proxy and start it with your instance connection name:
   `cloud-sql-proxy <PROJECT>:<REGION>:<INSTANCE>`
   It listens on 127.0.0.1:3306.
3. In `backend/.env` set `DB_HOST=127.0.0.1`, `DB_PORT=3306`, and `DB_USER`, `DB_PASSWORD`, `DB_NAME` for your Cloud SQL database.

The app only reads and writes rows; it never creates or drops tables in Cloud SQL.

### Smoke test (run this first against Cloud SQL)

With the proxy running and `backend/.env` pointing at Cloud SQL:

```powershell
cd backend
python scripts/smoke_test.py            # read-only: checks tables, columns, view, triggers, lookups, data, and calls the API
python scripts/smoke_test.py --write    # also creates two throwaway accounts, uses every write endpoint, then deletes them
python scripts/smoke_test.py --write --admin-email you@illinois.edu --admin-password "..."   # adds a moderation check
```

Each check prints PASS, WARN or FAIL, and the script exits with 1 if anything failed. The read-only run changes nothing. The `--write` run cleans up after itself through the delete rules, and its last line confirms that no test account was left behind.

WARN lines for the six triggers mean the database doesn't have them. The app still works, because it never writes rows that break those rules and it checks the chosen-route rule itself. To add them, run `database/triggers.sql` against the database; it adds triggers only and leaves the tables alone.

### Useful commands

```powershell
flask --app wsgi create-admin --email you@illinois.edu --password "a-long-password"
flask --app wsgi run-alerts            # the subscription alert job (schedule it, e.g. hourly)
flask --app wsgi refresh-cell-counts   # recompute CellRiskScore after loading new crash data
```

## 2. Frontend

Needs Node.js 18 or newer to run the app and the unit tests (tested on 18.12.0 and 22). The browser tests (`npm run test:e2e`) need Node.js 20 or newer, because Playwright does not start on 18.

```powershell
cd frontend
npm install
npm run dev                       # http://localhost:5173, forwards /api to the Flask API
```

The map uses Esri's tiles, which need no key: a colourful street map in light mode and a dark gray map in dark mode. For CARTO's Voyager style (closest to the original mockup) and Dark Matter, get a free key at https://carto.com/basemaps/apikey (non-commercial use is free; CARTO has required a key since 25 September 2026), put `VITE_CARTO_KEY=...` in `frontend/.env`, then restart `npm run dev`.

`npm run build` writes `frontend/dist`. To serve it from Flask as one app, set `FRONTEND_DIST=../frontend/dist` in `backend/.env`.

## 3. Tests

**Backend (pytest).** The tests need a local, empty MySQL 8 database whose name ends in `_test`; they drop and recreate every table in it. Never point them at Cloud SQL.

```powershell
# once, in a local MySQL: CREATE DATABASE resql_test;
$env:TEST_DB_USER="root"; $env:TEST_DB_PASSWORD="..."   # macOS/Linux: export TEST_DB_USER=root ...
cd backend
pytest
```

If creating the triggers fails with "You do not have the SUPER privilege and binary logging is enabled", run this once in your local MySQL as root: `SET PERSIST log_bin_trust_function_creators = 1;`

**Frontend (Vitest).**

```powershell
cd frontend
npm test
npm run typecheck
```

**End-to-end (Playwright).** These start the real Flask API and the Vite dev server, then drive Chromium through sign-up, analysis, search, saved locations, subscriptions, alerts, reports and moderation (16 tests, plus 3 more on existing data, below). They use a local database called `resql_e2e`, which they wipe and reload with the Illinois demo data on every run, so never point them at Cloud SQL. Routing, place search and weather use the offline providers, so the results do not depend on outside services.

```powershell
# once, in a local MySQL: CREATE DATABASE resql_e2e;
cd frontend
npx playwright install chromium
$env:E2E_DB_USER="root"; $env:E2E_DB_PASSWORD="..."            # macOS/Linux: export E2E_DB_USER=root ...
npm run test:e2e
```

The tests run the API with the Python in `backend/.venv` from section 1 (set `E2E_PYTHON` to use another one). Other settings: `E2E_DB_HOST`, `E2E_DB_PORT`, `E2E_DB_NAME` (default `resql_e2e`). Ports 5055 (API) and 5174 (web) must be free.

**End-to-end on a copy of the Cloud SQL data.** `E2E_SEED=0` skips the reload and runs against whatever is already in the database, and adds 3 more tests that only make sense on real data: every crash year searched with totals checked against the API, an admin moderating one of the team's existing reports, and long multi-state trips (19 tests in all). It must still be a local copy, because the tests add accounts, reports and alerts and remove one existing report.

1. Export the database from Cloud SQL (instance page → **Export** → SQL) and download the `.sql.gz` file.
2. Unzip it (7-Zip, for example). The file creates and fills a database named `resql`, so load it into a local MySQL that has no `resql` database of its own: `mysql -u root -p -e "source C:/path/to/export.sql"`.
3. Cloud SQL's export leaves out triggers. To have the same rules as the design, run `database/triggers.sql` against the copy (the API checks the rules too, so the tests pass either way).
4. `$env:E2E_DB_NAME="resql"; $env:E2E_SEED="0"; npm run test:e2e`

## 4. Local database (optional)

To run everything without Cloud SQL, create a local MySQL 8 database, point `backend/.env` at it, then:

```powershell
cd backend
flask --app wsgi init-db          # creates the tables, triggers, view and lookup rows (local hosts only)
flask --app wsgi init-db --demo   # same, plus the Illinois slice of the real 2024 data (database/demo_seed.sql)
cd ..
python database/loader/load_data.py --fars-dir <FARS2024NationalCSV folder> --ghcn-file <ghcnd_2024.csv> --stations-file <ghcnd-stations.txt> --crss-dir <CRSS2024CSV folder> --replace
```

The loader reads the same `DB_*` environment variables as the backend. `--states 17` loads Illinois only.

`--demo` is the quick way to try the app: 1,085 Illinois crashes with their sites, vehicles, people, nearby stations and weather readings, taken unchanged from the full load. `init-db --drop` empties the database first. Both refuse to run against a non-local host.

## Notes

- **Risk score:** every score goes through `backend/app/risk/`. Today it reads the Stage 2 `CellRiskCurrent` view and is labelled "Placeholder model" in the UI. To switch to the ML model, implement `backend/app/risk/ml.py` and set `RISK_MODEL=ml`.
- **External services:** routes come from OSRM (public demo server by default), place search from OpenStreetMap Nominatim, and current weather from Open-Meteo. If one is unreachable the app falls back to an offline version (straight-line routes, a short city list, "clear" weather). Set `ROUTING_PROVIDER`, `GEOCODER` or `WEATHER_PROVIDER` to `offline` to force it.
- **Map tiles:** CARTO (map) and Esri (satellite), with attribution, as in the mockup.
- **Loader finding:** 423 FARS 2024 person rows refer to vehicles that are not in `vehicle.csv`. The Person trigger would reject them, so the loader skips them and reports the count.
