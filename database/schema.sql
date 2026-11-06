-- Traffic Safety Risk Analyzer (team041 ReSQL)
-- MySQL 8.0.16+ schema, translated from doc/stage2_database_design-p2.md (section 5 and section 6).
--
-- This file is used to build LOCAL development and test databases. The production
-- database lives in Google Cloud SQL and is managed by the team; do not run this file
-- against Cloud SQL unless you mean to recreate it.

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- Reference data from FARS
-- ---------------------------------------------------------------------------
CREATE TABLE State (
  state_code   TINYINT      NOT NULL,
  state_name   VARCHAR(40)  NOT NULL,
  PRIMARY KEY (state_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE County (
  state_code   TINYINT      NOT NULL,
  county_code  SMALLINT     NOT NULL,
  county_name  VARCHAR(60)  NOT NULL,
  PRIMARY KEY (state_code, county_code),
  CONSTRAINT fk_county_state FOREIGN KEY (state_code)
    REFERENCES State (state_code) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE WeatherCondition (
  weather_code   TINYINT      NOT NULL,
  description    VARCHAR(60)  NOT NULL,
  weather_group  VARCHAR(20)  NOT NULL,
  PRIMARY KEY (weather_code),
  CONSTRAINT chk_wc_group CHECK (weather_group IN ('dry','wet','snow_ice','low_visibility','unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE LightCondition (
  light_code   TINYINT      NOT NULL,
  description  VARCHAR(60)  NOT NULL,
  light_group  VARCHAR(10)  NOT NULL,
  PRIMARY KEY (light_code),
  CONSTRAINT chk_lc_group CHECK (light_group IN ('day','dark','unknown'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE RoadClass (
  func_sys_code  TINYINT      NOT NULL,
  description    VARCHAR(60)  NOT NULL,
  PRIMARY KEY (func_sys_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Location entities
-- ---------------------------------------------------------------------------
-- cell_id = CONCAT(FLOOR(lat*10), '_', FLOOR(lon*10)); size is a fixed 0.1 degree.
CREATE TABLE GridCell (
  cell_id        VARCHAR(12)   NOT NULL,
  min_latitude   DECIMAL(4,1)  NOT NULL,
  min_longitude  DECIMAL(5,1)  NOT NULL,
  PRIMARY KEY (cell_id),
  CONSTRAINT uq_gridcell_corner UNIQUE (min_latitude, min_longitude)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE WeatherStation (
  station_id    CHAR(11)      NOT NULL,
  station_name  VARCHAR(40)   NOT NULL,
  latitude      DECIMAL(7,4)  NOT NULL,
  longitude     DECIMAL(8,4)  NOT NULL,
  PRIMARY KEY (station_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE DailyWeather (
  station_id        CHAR(11)      NOT NULL,
  obs_date          DATE          NOT NULL,
  precipitation_mm  DECIMAL(6,1)  NULL,
  snowfall_mm       DECIMAL(6,1)  NULL,
  snow_depth_mm     DECIMAL(6,1)  NULL,
  temp_max_c        DECIMAL(4,1)  NULL,
  temp_min_c        DECIMAL(4,1)  NULL,
  avg_wind_ms       DECIMAL(4,1)  NULL,
  PRIMARY KEY (station_id, obs_date),
  CONSTRAINT fk_dw_station FOREIGN KEY (station_id)
    REFERENCES WeatherStation (station_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE CrashSite (
  latitude     DECIMAL(10,8)  NOT NULL,
  longitude    DECIMAL(11,8)  NOT NULL,
  state_code   TINYINT        NOT NULL,
  county_code  SMALLINT       NOT NULL,
  cell_id      VARCHAR(12)    NOT NULL,
  PRIMARY KEY (latitude, longitude),
  CONSTRAINT fk_site_county FOREIGN KEY (state_code, county_code)
    REFERENCES County (state_code, county_code) ON DELETE RESTRICT,
  CONSTRAINT fk_site_cell FOREIGN KEY (cell_id)
    REFERENCES GridCell (cell_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Crash entities (FARS)
-- ---------------------------------------------------------------------------
CREATE TABLE Crash (
  data_year           SMALLINT       NOT NULL,
  st_case             INT            NOT NULL,
  latitude            DECIMAL(10,8)  NOT NULL,
  longitude           DECIMAL(11,8)  NOT NULL,
  crash_date          DATE           NOT NULL,
  crash_hour          TINYINT        NOT NULL,   -- 0-23, 99 = unknown (FARS convention)
  crash_minute        TINYINT        NOT NULL,   -- 0-59, 99 = unknown
  weather_code        TINYINT        NOT NULL,
  light_code          TINYINT        NOT NULL,
  func_sys_code       TINYINT        NOT NULL,
  weather_station_id  CHAR(11)       NULL,
  rural_urban         TINYINT        NOT NULL,
  fatalities          SMALLINT       NOT NULL,
  persons_involved    SMALLINT       NOT NULL,
  vehicles_involved   SMALLINT       NOT NULL,
  PRIMARY KEY (data_year, st_case),
  CONSTRAINT chk_crash_year CHECK (YEAR(crash_date) = data_year),
  CONSTRAINT fk_crash_site FOREIGN KEY (latitude, longitude)
    REFERENCES CrashSite (latitude, longitude) ON DELETE RESTRICT,
  CONSTRAINT fk_crash_weather FOREIGN KEY (weather_code)
    REFERENCES WeatherCondition (weather_code) ON DELETE RESTRICT,
  CONSTRAINT fk_crash_light FOREIGN KEY (light_code)
    REFERENCES LightCondition (light_code) ON DELETE RESTRICT,
  CONSTRAINT fk_crash_road FOREIGN KEY (func_sys_code)
    REFERENCES RoadClass (func_sys_code) ON DELETE RESTRICT,
  CONSTRAINT fk_crash_dailyweather FOREIGN KEY (weather_station_id, crash_date)
    REFERENCES DailyWeather (station_id, obs_date) ON DELETE RESTRICT,
  INDEX idx_crash_date (crash_date),
  INDEX idx_crash_condition (weather_code, light_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Vehicle (
  data_year          SMALLINT  NOT NULL,
  st_case            INT       NOT NULL,
  veh_no             SMALLINT  NOT NULL,
  body_type          SMALLINT  NOT NULL,
  model_year         SMALLINT  NOT NULL,
  speeding_related   TINYINT   NOT NULL,
  deaths_in_vehicle  TINYINT   NOT NULL,
  PRIMARY KEY (data_year, st_case, veh_no),
  CONSTRAINT fk_vehicle_crash FOREIGN KEY (data_year, st_case)
    REFERENCES Crash (data_year, st_case) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Person (
  data_year        SMALLINT  NOT NULL,
  st_case          INT       NOT NULL,
  veh_no           SMALLINT  NOT NULL,   -- 0 = non-motorist (pedestrian, cyclist)
  per_no           SMALLINT  NOT NULL,
  person_type      TINYINT   NOT NULL,
  injury_severity  TINYINT   NOT NULL,
  age              SMALLINT  NOT NULL,
  restraint_use    TINYINT   NOT NULL,
  PRIMARY KEY (data_year, st_case, veh_no, per_no),
  CONSTRAINT fk_person_crash FOREIGN KEY (data_year, st_case)
    REFERENCES Crash (data_year, st_case) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Scoring entities
-- ---------------------------------------------------------------------------
CREATE TABLE ConditionProfile (
  condition_id                TINYINT       NOT NULL,
  weather_group               VARCHAR(20)   NOT NULL,
  light_group                 VARCHAR(10)   NOT NULL,
  national_est_crashes        INT           NOT NULL,
  national_serious_fatal_pct  DECIMAL(5,2)  NOT NULL,
  PRIMARY KEY (condition_id),
  CONSTRAINT uq_profile_groups UNIQUE (weather_group, light_group),
  CONSTRAINT chk_cp_weather CHECK (weather_group IN ('dry','wet','snow_ice','low_visibility')),
  CONSTRAINT chk_cp_light CHECK (light_group IN ('day','dark'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE CellRiskScore (
  cell_id         VARCHAR(12)  NOT NULL,
  condition_id    TINYINT      NOT NULL,
  crash_count     INT          NOT NULL,
  fatality_count  INT          NOT NULL,
  computed_at     DATETIME     NOT NULL,
  PRIMARY KEY (cell_id, condition_id),
  CONSTRAINT fk_crs_cell FOREIGN KEY (cell_id)
    REFERENCES GridCell (cell_id) ON DELETE CASCADE,
  CONSTRAINT fk_crs_condition FOREIGN KEY (condition_id)
    REFERENCES ConditionProfile (condition_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Application entities
-- ---------------------------------------------------------------------------
CREATE TABLE AppUser (
  user_id        INT           NOT NULL AUTO_INCREMENT,
  email          VARCHAR(120)  NOT NULL,
  password_hash  VARCHAR(255)  NOT NULL,
  display_name   VARCHAR(60)   NOT NULL,
  role           VARCHAR(10)   NOT NULL DEFAULT 'user',
  safety_weight  DECIMAL(3,2)  NOT NULL DEFAULT 0.50,
  units          VARCHAR(10)   NOT NULL DEFAULT 'imperial',
  created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  CONSTRAINT uq_user_email UNIQUE (email),
  CONSTRAINT chk_user_role CHECK (role IN ('user','admin')),
  CONSTRAINT chk_user_units CHECK (units IN ('metric','imperial')),
  CONSTRAINT chk_user_weight CHECK (safety_weight BETWEEN 0 AND 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE SavedLocation (
  location_id  INT            NOT NULL AUTO_INCREMENT,
  user_id      INT            NOT NULL,
  label        VARCHAR(60)    NOT NULL,
  latitude     DECIMAL(9,6)   NOT NULL,
  longitude    DECIMAL(10,6)  NOT NULL,
  created_at   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (location_id),
  CONSTRAINT fk_loc_user FOREIGN KEY (user_id)
    REFERENCES AppUser (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_loc_lat CHECK (latitude BETWEEN -90 AND 90),
  CONSTRAINT chk_loc_lon CHECK (longitude BETWEEN -180 AND 180)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE CrashReport (
  report_id    INT            NOT NULL AUTO_INCREMENT,
  user_id      INT            NOT NULL,
  latitude     DECIMAL(9,6)   NOT NULL,
  longitude    DECIMAL(10,6)  NOT NULL,
  reason       VARCHAR(255)   NOT NULL,
  status       VARCHAR(20)    NOT NULL DEFAULT 'active',
  reported_at  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_by  INT            NULL,
  reviewed_at  DATETIME       NULL,
  PRIMARY KEY (report_id),
  CONSTRAINT fk_report_user FOREIGN KEY (user_id)
    REFERENCES AppUser (user_id) ON DELETE CASCADE,
  CONSTRAINT fk_report_reviewer FOREIGN KEY (reviewed_by)
    REFERENCES AppUser (user_id) ON DELETE SET NULL,
  CONSTRAINT chk_report_status CHECK (status IN ('active','resolved','removed')),
  CONSTRAINT chk_report_lat CHECK (latitude BETWEEN -90 AND 90),
  CONSTRAINT chk_report_lon CHECK (longitude BETWEEN -180 AND 180),
  INDEX idx_report_reported_at (reported_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ReportCell (
  report_id  INT          NOT NULL,
  cell_id    VARCHAR(12)  NOT NULL,
  PRIMARY KEY (report_id),
  CONSTRAINT fk_rc_report FOREIGN KEY (report_id)
    REFERENCES CrashReport (report_id) ON DELETE CASCADE,
  CONSTRAINT fk_rc_cell FOREIGN KEY (cell_id)
    REFERENCES GridCell (cell_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE ReportVote (
  report_id  INT       NOT NULL,
  user_id    INT       NOT NULL,
  vote       TINYINT   NOT NULL,
  voted_at   DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (report_id, user_id),
  CONSTRAINT fk_vote_report FOREIGN KEY (report_id)
    REFERENCES CrashReport (report_id) ON DELETE CASCADE,
  CONSTRAINT fk_vote_user FOREIGN KEY (user_id)
    REFERENCES AppUser (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_vote_value CHECK (vote IN (1, -1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE RouteRequest (
  route_id       INT            NOT NULL AUTO_INCREMENT,
  user_id        INT            NOT NULL,
  origin_lat     DECIMAL(9,6)   NOT NULL,
  origin_lon     DECIMAL(10,6)  NOT NULL,
  dest_lat       DECIMAL(9,6)   NOT NULL,
  dest_lon       DECIMAL(10,6)  NOT NULL,
  chosen_option  VARCHAR(10)    NULL,
  requested_at   DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (route_id),
  CONSTRAINT fk_route_user FOREIGN KEY (user_id)
    REFERENCES AppUser (user_id) ON DELETE CASCADE,
  CONSTRAINT chk_route_option CHECK (chosen_option IS NULL OR chosen_option IN ('fastest','safest','balanced')),
  CONSTRAINT chk_route_olat CHECK (origin_lat BETWEEN -90 AND 90),
  CONSTRAINT chk_route_olon CHECK (origin_lon BETWEEN -180 AND 180),
  CONSTRAINT chk_route_dlat CHECK (dest_lat BETWEEN -90 AND 90),
  CONSTRAINT chk_route_dlon CHECK (dest_lon BETWEEN -180 AND 180),
  INDEX idx_route_user_time (user_id, requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE RouteOption (
  route_id       INT           NOT NULL,
  option_type    VARCHAR(10)   NOT NULL,
  travel_time_s  INT           NOT NULL,
  risk_score     DECIMAL(5,2)  NOT NULL,
  PRIMARY KEY (route_id, option_type),
  CONSTRAINT fk_option_route FOREIGN KEY (route_id)
    REFERENCES RouteRequest (route_id) ON DELETE CASCADE,
  CONSTRAINT chk_option_type CHECK (option_type IN ('fastest','safest','balanced')),
  CONSTRAINT chk_option_score CHECK (risk_score BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Subscription (
  subscription_id  INT           NOT NULL AUTO_INCREMENT,
  location_id      INT           NOT NULL,
  condition_id     TINYINT       NOT NULL,
  alert_threshold  DECIMAL(5,2)  NOT NULL,
  baseline_score   DECIMAL(5,2)  NOT NULL,
  is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (subscription_id),
  CONSTRAINT uq_sub_location_condition UNIQUE (location_id, condition_id),
  CONSTRAINT fk_sub_location FOREIGN KEY (location_id)
    REFERENCES SavedLocation (location_id) ON DELETE CASCADE,
  CONSTRAINT fk_sub_condition FOREIGN KEY (condition_id)
    REFERENCES ConditionProfile (condition_id) ON DELETE RESTRICT,
  CONSTRAINT chk_sub_threshold CHECK (alert_threshold > 0),
  CONSTRAINT chk_sub_baseline CHECK (baseline_score BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Alert (
  alert_id            INT           NOT NULL AUTO_INCREMENT,
  subscription_id     INT           NOT NULL,
  risk_score_at_send  DECIMAL(5,2)  NOT NULL,
  sent_at             DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (alert_id),
  CONSTRAINT fk_alert_sub FOREIGN KEY (subscription_id)
    REFERENCES Subscription (subscription_id) ON DELETE CASCADE,
  CONSTRAINT chk_alert_score CHECK (risk_score_at_send BETWEEN 0 AND 100),
  INDEX idx_alert_sub_time (subscription_id, sent_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
