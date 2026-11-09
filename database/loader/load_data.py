"""Load NHTSA FARS crashes and NOAA GHCN-Daily weather into the ReSQL schema.

This follows doc/stage2_database_design-p2.md:
  * crashes with unknown coordinates are dropped (section 6.6)
  * each crash is matched to the nearest station within 50 km that has a
    non-null precipitation reading on the crash date (section 2.4)
  * GHCN units are converted, -9999 becomes NULL, quality-flagged values are NULL
  * CellRiskScore holds crash and fatality counts per (cell, condition)
  * ConditionProfile national figures can be recomputed from CRSS (--crss-dir)

Typical local use (see database/README.md):
  python database/loader/load_data.py \
      --fars-dir data/FARS2024NationalCSV \
      --ghcn-file data/ghcnd_2024.csv.gz \
      --stations-file data/ghcnd-stations.txt \
      --crss-dir data/CRSS2024CSV --states 17 --replace

Connection settings come from the same environment variables as the backend
(DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import time
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal

import numpy as np
import pandas as pd
import pymysql

EARTH_RADIUS_KM = 6371.0
MAX_STATION_DISTANCE_KM = 50.0
GHCN_ELEMENTS = {
    # element: (column, divisor)
    "PRCP": ("precipitation_mm", 10.0),
    "SNOW": ("snowfall_mm", 1.0),
    "SNWD": ("snow_depth_mm", 1.0),
    "TMAX": ("temp_max_c", 10.0),
    "TMIN": ("temp_min_c", 10.0),
    "AWND": ("avg_wind_ms", 10.0),
}
WEATHER_GROUPS = {1: "dry", 2: "wet", 3: "snow_ice", 4: "snow_ice", 5: "low_visibility",
                  6: "dry", 7: "low_visibility", 10: "dry", 11: "snow_ice", 12: "snow_ice"}
LIGHT_GROUPS = {1: "day", 2: "dark", 3: "dark", 4: "day", 5: "day", 6: "dark"}
DATA_TABLES_IN_DELETE_ORDER = [
    "CellRiskScore", "Person", "Vehicle", "Crash", "DailyWeather", "WeatherStation",
    "CrashSite", "County", "State",
]


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def cell_for(lat: str, lon: str) -> tuple[str, Decimal, Decimal]:
    """Grid formula from section 2.2, using exact decimal arithmetic."""
    lat_d = (Decimal(lat) * 10).to_integral_value(rounding=ROUND_FLOOR)
    lon_d = (Decimal(lon) * 10).to_integral_value(rounding=ROUND_FLOOR)
    return f"{int(lat_d)}_{int(lon_d)}", lat_d / 10, lon_d / 10


def open_text(path: str):
    with open(path, "rb") as fh:
        magic = fh.read(2)
    return gzip.open(path, "rt") if magic == b"\x1f\x8b" else open(path, "rt")


def connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "resql"),
        charset="utf8mb4",
        autocommit=False,
    )


def insert_many(cur, table: str, columns: list[str], rows: list[tuple], batch: int = 2000) -> None:
    if not rows:
        return
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})"
    for i in range(0, len(rows), batch):
        cur.executemany(sql, [tuple(nz(v) for v in row) for row in rows[i:i + batch]])


# ---------------------------------------------------------------------------
# FARS
# ---------------------------------------------------------------------------
def read_fars(fars_dir: str, states: set[int] | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    acc = pd.read_csv(os.path.join(fars_dir, "accident.csv"), encoding="latin1", low_memory=False,
                      dtype={"LATITUDE": str, "LONGITUD": str})
    total = len(acc)
    lat = pd.to_numeric(acc.LATITUDE, errors="coerce")
    lon = pd.to_numeric(acc.LONGITUD, errors="coerce")
    valid = lat.between(-90, 90) & lon.between(-180, 180) & ~lat.isin([77.7777, 88.8888, 99.9999])
    acc = acc[valid].copy()
    log(f"FARS accident.csv: {total} crashes, {total - len(acc)} dropped for unknown coordinates")
    if states:
        acc = acc[acc.STATE.isin(states)].copy()
        log(f"state filter {sorted(states)}: {len(acc)} crashes kept")
    veh = pd.read_csv(os.path.join(fars_dir, "vehicle.csv"), encoding="latin1", low_memory=False,
                      usecols=["ST_CASE", "VEH_NO", "BODY_TYP", "MOD_YEAR", "SPEEDREL", "DEATHS"])
    per = pd.read_csv(os.path.join(fars_dir, "person.csv"), encoding="latin1", low_memory=False,
                      usecols=["ST_CASE", "VEH_NO", "PER_NO", "PER_TYP", "INJ_SEV", "AGE", "REST_USE"])
    keep = set(acc.ST_CASE)
    veh = veh[veh.ST_CASE.isin(keep)]
    per = per[per.ST_CASE.isin(keep)]
    return acc, veh, per


# ---------------------------------------------------------------------------
# GHCN-Daily
# ---------------------------------------------------------------------------
def read_stations(path: str) -> pd.DataFrame:
    colspecs = [(0, 11), (12, 20), (21, 30), (41, 71)]
    st = pd.read_fwf(path, colspecs=colspecs, header=None, names=["station_id", "lat", "lon", "name"],
                     dtype=str, encoding="latin1")
    st = st[st.station_id.str.startswith("US")].copy()
    st["lat"] = st.lat.astype(float)
    st["lon"] = st.lon.astype(float)
    st["name"] = st.name.fillna("").str.strip().str.slice(0, 40)
    return st.reset_index(drop=True)


def ghcn_chunks(path: str, chunksize: int = 3_000_000):
    names = ["ID", "DATE", "ELEMENT", "VALUE", "MFLAG", "QFLAG", "SFLAG", "OBSTIME"]
    with open_text(path) as fh:
        for chunk in pd.read_csv(fh, header=None, names=names, usecols=[0, 1, 2, 3, 5],
                                 dtype={"ID": str, "DATE": np.int32, "ELEMENT": str, "VALUE": np.int32,
                                        "QFLAG": str}, chunksize=chunksize):
            chunk = chunk[chunk.ID.str.startswith("US") & chunk.QFLAG.isna() & (chunk.VALUE != -9999)]
            yield chunk


def match_stations(acc: pd.DataFrame, stations: pd.DataFrame, ghcn_file: str) -> pd.Series:
    """Nearest station within 50 km with a precipitation reading on the crash date."""
    from sklearn.neighbors import BallTree

    station_index = pd.CategoricalDtype(categories=stations.station_id.tolist())
    crash_dates = set((acc.YEAR * 10000 + acc.MONTH * 100 + acc.DAY).astype(np.int32))
    sid_parts, date_parts = [], []
    log("pass 1 over GHCN: stations with precipitation per day")
    for chunk in ghcn_chunks(ghcn_file):
        prcp = chunk[(chunk.ELEMENT == "PRCP") & chunk.DATE.isin(crash_dates)]
        codes = prcp.ID.astype(station_index).cat.codes.to_numpy()
        ok = codes >= 0
        sid_parts.append(codes[ok].astype(np.int32))
        date_parts.append(prcp.DATE.to_numpy()[ok])
    sids = np.concatenate(sid_parts)
    dates = np.concatenate(date_parts)
    log(f"  {len(sids):,} station-days with precipitation")

    coords = np.radians(stations[["lat", "lon"]].to_numpy())
    acc_dates = (acc.YEAR * 10000 + acc.MONTH * 100 + acc.DAY).astype(np.int32).to_numpy()
    acc_coords = np.radians(np.column_stack([acc.LATITUDE.astype(float), acc.LONGITUD.astype(float)]))
    result = np.full(len(acc), None, dtype=object)
    order = np.argsort(dates, kind="stable")
    sids, dates = sids[order], dates[order]
    bounds = np.searchsorted(dates, np.unique(acc_dates))
    for d, start in zip(np.unique(acc_dates), bounds):
        end = np.searchsorted(dates, d, side="right")
        day_sids = np.unique(sids[start:end])
        if len(day_sids) == 0:
            continue
        tree = BallTree(coords[day_sids], metric="haversine")
        mask = acc_dates == d
        dist, idx = tree.query(acc_coords[mask], k=1)
        km = dist[:, 0] * EARTH_RADIUS_KM
        matched = np.where(km <= MAX_STATION_DISTANCE_KM,
                           stations.station_id.to_numpy()[day_sids[idx[:, 0]]], None)
        result[mask] = matched
    out = pd.Series(result, index=acc.index)
    log(f"  {out.notna().mean():.1%} of crashes matched to a station within {MAX_STATION_DISTANCE_KM:.0f} km")
    return out


def read_daily_weather(ghcn_file: str, keys: set[tuple[str, int]]) -> pd.DataFrame:
    log("pass 2 over GHCN: daily readings for matched station-days")
    wanted_ids = {k[0] for k in keys}
    key_index = pd.MultiIndex.from_tuples(sorted(keys), names=["ID", "DATE"])
    parts = []
    for chunk in ghcn_chunks(ghcn_file):
        chunk = chunk[chunk.ELEMENT.isin(GHCN_ELEMENTS) & chunk.ID.isin(wanted_ids)]
        mi = pd.MultiIndex.from_arrays([chunk.ID, chunk.DATE])
        parts.append(chunk[mi.isin(key_index)])
    long = pd.concat(parts)
    wide = long.pivot_table(index=["ID", "DATE"], columns="ELEMENT", values="VALUE", aggfunc="first")
    for element, (column, divisor) in GHCN_ELEMENTS.items():
        wide[column] = wide[element] / divisor if element in wide else np.nan
    wide = wide[[c for c, _ in GHCN_ELEMENTS.values()]].reset_index()
    log(f"  {len(wide):,} station-day rows")
    return wide


# ---------------------------------------------------------------------------
# CRSS national baselines
# ---------------------------------------------------------------------------
def crss_profiles(crss_dir: str) -> pd.DataFrame:
    c = pd.read_csv(os.path.join(crss_dir, "accident.csv"), encoding="latin1", low_memory=False,
                    usecols=["WEATHR_IM", "LGTCON_IM", "MAXSEV_IM", "WEIGHT"])
    c["weather_group"] = c.WEATHR_IM.map(WEATHER_GROUPS)
    c["light_group"] = c.LGTCON_IM.map(LIGHT_GROUPS)
    c["serious"] = c.MAXSEV_IM.isin([3, 4])
    c = c.dropna(subset=["weather_group", "light_group"])
    g = c.groupby(["weather_group", "light_group"])
    est = g.WEIGHT.sum()
    pct = g.apply(lambda d: 100 * (d.WEIGHT * d.serious).sum() / d.WEIGHT.sum(), include_groups=False)
    return pd.DataFrame({"est": est.round().astype(int), "pct": pct.round(2)}).reset_index()


# ---------------------------------------------------------------------------
def nz(v):
    """NaN and missing values become SQL NULL; numpy scalars become Python numbers."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v.item() if hasattr(v, "item") else v


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fars-dir", required=True)
    p.add_argument("--ghcn-file", required=True, help="GHCN-Daily yearly file (csv or csv.gz) for the FARS year")
    p.add_argument("--stations-file", required=True)
    p.add_argument("--crss-dir", help="CRSS directory; recomputes ConditionProfile national figures")
    p.add_argument("--states", help="comma-separated FARS state codes to load, e.g. 17 for Illinois")
    p.add_argument("--replace", action="store_true",
                   help="delete existing crash and weather data first (local databases only)")
    p.add_argument("--allow-remote", action="store_true", help="permit --replace on a non-local host")
    args = p.parse_args()

    host = os.environ.get("DB_HOST", "127.0.0.1")
    if args.replace and host not in ("127.0.0.1", "localhost") and not args.allow_remote:
        print("Refusing --replace on a non-local database. Add --allow-remote if you really mean it.")
        return 2

    started = time.time()
    states = {int(s) for s in args.states.split(",")} if args.states else None
    acc, veh, per = read_fars(args.fars_dir, states)
    stations = read_stations(args.stations_file)
    acc["station_id"] = match_stations(acc, stations, args.ghcn_file)
    acc["obs_date"] = (acc.YEAR * 10000 + acc.MONTH * 100 + acc.DAY).astype(np.int32)
    keys = {(s, int(d)) for s, d in zip(acc.station_id, acc.obs_date) if isinstance(s, str)}
    daily = read_daily_weather(args.ghcn_file, keys)
    # A crash can only reference a station-day that survived the quality rules with precipitation.
    have = set(zip(daily.ID, daily.DATE))
    dropped_matches = sum(1 for k in keys if k not in have)
    acc["station_id"] = [s if isinstance(s, str) and (s, d) in have else None
                         for s, d in zip(acc.station_id, acc.obs_date)]
    if dropped_matches:
        log(f"  {dropped_matches} matches without a stored reading were cleared")

    conn = connect()
    cur = conn.cursor()
    try:
        if args.replace:
            log("deleting existing data")
            for table in DATA_TABLES_IN_DELETE_ORDER:
                cur.execute(f"DELETE FROM {table}")
            cur.execute("DELETE FROM GridCell WHERE cell_id NOT IN (SELECT cell_id FROM ReportCell)")

        if args.crss_dir:
            prof = crss_profiles(args.crss_dir)
            for r in prof.itertuples():
                cur.execute("UPDATE ConditionProfile SET national_est_crashes=%s, national_serious_fatal_pct=%s "
                            "WHERE weather_group=%s AND light_group=%s",
                            (int(r.est), float(r.pct), r.weather_group, r.light_group))
            log("ConditionProfile national figures updated from CRSS")

        states_rows = acc[["STATE", "STATENAME"]].drop_duplicates("STATE")
        insert_many(cur, "State", ["state_code", "state_name"],
                    [(int(r.STATE), r.STATENAME) for r in states_rows.itertuples()])
        counties = acc[["STATE", "COUNTY", "COUNTYNAME"]].drop_duplicates(["STATE", "COUNTY"])
        insert_many(cur, "County", ["state_code", "county_code", "county_name"],
                    [(int(r.STATE), int(r.COUNTY),
                      str(r.COUNTYNAME).rsplit(" (", 1)[0].title()[:60]) for r in counties.itertuples()])

        sites = acc.drop_duplicates(["LATITUDE", "LONGITUD"])
        cells, site_rows = {}, []
        for r in sites.itertuples():
            cell_id, min_lat, min_lon = cell_for(r.LATITUDE, r.LONGITUD)
            cells[cell_id] = (cell_id, min_lat, min_lon)
            site_rows.append((r.LATITUDE, r.LONGITUD, int(r.STATE), int(r.COUNTY), cell_id))
        cur.execute("SELECT cell_id FROM GridCell")
        existing = {row[0] for row in cur.fetchall()}
        insert_many(cur, "GridCell", ["cell_id", "min_latitude", "min_longitude"],
                    [v for k, v in cells.items() if k not in existing])
        insert_many(cur, "CrashSite", ["latitude", "longitude", "state_code", "county_code", "cell_id"], site_rows)
        log(f"{len(site_rows):,} crash sites in {len(cells):,} grid cells")

        used = stations[stations.station_id.isin({k[0] for k in have})]
        insert_many(cur, "WeatherStation", ["station_id", "station_name", "latitude", "longitude"],
                    [(r.station_id, r.name or r.station_id, round(r.lat, 4), round(r.lon, 4)) for r in used.itertuples()])
        insert_many(cur, "DailyWeather",
                    ["station_id", "obs_date", "precipitation_mm", "snowfall_mm", "snow_depth_mm",
                     "temp_max_c", "temp_min_c", "avg_wind_ms"],
                    [(r.ID, date(r.DATE // 10000, r.DATE // 100 % 100, r.DATE % 100),
                      nz(r.precipitation_mm), nz(r.snowfall_mm), nz(r.snow_depth_mm),
                      nz(r.temp_max_c), nz(r.temp_min_c), nz(r.avg_wind_ms)) for r in daily.itertuples()])
        log(f"{len(used):,} weather stations, {len(daily):,} daily readings")

        crash_rows = [(int(r.YEAR), int(r.ST_CASE), r.LATITUDE, r.LONGITUD, date(int(r.YEAR), int(r.MONTH), int(r.DAY)),
                       int(r.HOUR), int(r.MINUTE), int(r.WEATHER), int(r.LGT_COND), int(r.FUNC_SYS),
                       r.station_id, int(r.RUR_URB), int(r.FATALS), int(r.PERSONS), int(r.VE_TOTAL))
                      for r in acc.itertuples()]
        insert_many(cur, "Crash", ["data_year", "st_case", "latitude", "longitude", "crash_date", "crash_hour",
                                   "crash_minute", "weather_code", "light_code", "func_sys_code",
                                   "weather_station_id", "rural_urban", "fatalities", "persons_involved",
                                   "vehicles_involved"], crash_rows)
        year_of = dict(zip(acc.ST_CASE, acc.YEAR))
        insert_many(cur, "Vehicle", ["data_year", "st_case", "veh_no", "body_type", "model_year",
                                     "speeding_related", "deaths_in_vehicle"],
                    [(int(year_of[r.ST_CASE]), int(r.ST_CASE), int(r.VEH_NO), int(r.BODY_TYP), int(r.MOD_YEAR),
                      int(r.SPEEDREL), int(r.DEATHS)) for r in veh.itertuples()])
        vehicles = set(zip(veh.ST_CASE, veh.VEH_NO))
        ok = [(v == 0) or ((c, v) in vehicles) for c, v in zip(per.ST_CASE, per.VEH_NO)]
        if not all(ok):
            log(f"  {len(ok) - sum(ok)} person rows skipped: their vehicle is not in vehicle.csv")
        per = per[ok]
        insert_many(cur, "Person", ["data_year", "st_case", "veh_no", "per_no", "person_type",
                                    "injury_severity", "age", "restraint_use"],
                    [(int(year_of[r.ST_CASE]), int(r.ST_CASE), int(r.VEH_NO), int(r.PER_NO), int(r.PER_TYP),
                      int(r.INJ_SEV), int(r.AGE), int(r.REST_USE)) for r in per.itertuples()])
        log(f"{len(crash_rows):,} crashes, {len(veh):,} vehicles, {len(per):,} people")

        refresh_cell_counts(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    log(f"done in {time.time() - started:.0f}s")
    return 0


REFRESH_SQL = """
INSERT INTO CellRiskScore (cell_id, condition_id, crash_count, fatality_count, computed_at)
SELECT s.cell_id, p.condition_id, COUNT(*), SUM(c.fatalities), NOW()
FROM Crash c
JOIN CrashSite s ON s.latitude = c.latitude AND s.longitude = c.longitude
JOIN WeatherCondition w ON w.weather_code = c.weather_code
JOIN LightCondition l ON l.light_code = c.light_code
JOIN ConditionProfile p ON p.weather_group = w.weather_group AND p.light_group = l.light_group
GROUP BY s.cell_id, p.condition_id
"""


def refresh_cell_counts(cur) -> None:
    """The scoring job: per-cell crash and fatality counts under each condition profile."""
    cur.execute("DELETE FROM CellRiskScore")
    cur.execute(REFRESH_SQL)
    log(f"CellRiskScore refreshed: {cur.rowcount:,} rows")


if __name__ == "__main__":
    sys.exit(main())
