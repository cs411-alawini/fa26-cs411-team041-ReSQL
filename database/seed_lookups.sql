-- Reference rows used by the application. Codes and labels are the ones FARS 2024 publishes.
-- The weather_group and light_group mappings are the team's working groups (Stage 2, section 2.1).

INSERT INTO WeatherCondition (weather_code, description, weather_group) VALUES
  (1,  'Clear',                    'dry'),
  (2,  'Rain',                     'wet'),
  (3,  'Sleet or Hail',            'snow_ice'),
  (4,  'Snow',                     'snow_ice'),
  (5,  'Fog, Smog, Smoke',         'low_visibility'),
  (6,  'Severe Crosswinds',        'dry'),
  (7,  'Blowing Sand, Soil, Dirt', 'low_visibility'),
  (8,  'Other',                    'unknown'),
  (10, 'Cloudy',                   'dry'),
  (11, 'Blowing Snow',             'snow_ice'),
  (12, 'Freezing Rain or Drizzle', 'snow_ice'),
  (98, 'Not Reported',             'unknown'),
  (99, 'Reported as Unknown',      'unknown');

INSERT INTO LightCondition (light_code, description, light_group) VALUES
  (1, 'Daylight',                'day'),
  (2, 'Dark - Not Lighted',      'dark'),
  (3, 'Dark - Lighted',          'dark'),
  (4, 'Dawn',                    'day'),
  (5, 'Dusk',                    'day'),
  (6, 'Dark - Unknown Lighting', 'dark'),
  (7, 'Other',                   'unknown'),
  (8, 'Not Reported',            'unknown'),
  (9, 'Reported as Unknown',     'unknown');

INSERT INTO RoadClass (func_sys_code, description) VALUES
  (1,  'Interstate'),
  (2,  'Other Freeways and Expressways'),
  (3,  'Other Principal Arterial'),
  (4,  'Minor Arterial'),
  (5,  'Major Collector'),
  (6,  'Minor Collector'),
  (7,  'Local'),
  (96, 'Trafficway Not in State Inventory'),
  (98, 'Not Reported'),
  (99, 'Unknown');

-- National baselines computed from CRSS 2024 with its sampling weights:
-- national_est_crashes = SUM(WEIGHT); national_serious_fatal_pct = weighted share with MAXSEV_IM in (3, 4).
-- database/loader/load_data.py recomputes these from the CRSS files.
INSERT INTO ConditionProfile (condition_id, weather_group, light_group, national_est_crashes, national_serious_fatal_pct) VALUES
  (1, 'dry',            'day',  4037111, 2.72),
  (2, 'dry',            'dark', 1419660, 4.65),
  (3, 'wet',            'day',   361403, 2.00),
  (4, 'wet',            'dark',  200890, 3.25),
  (5, 'snow_ice',       'day',    74914, 1.69),
  (6, 'snow_ice',       'dark',   56701, 1.73),
  (7, 'low_visibility', 'day',    12198, 3.09),
  (8, 'low_visibility', 'dark',   14811, 6.28);
