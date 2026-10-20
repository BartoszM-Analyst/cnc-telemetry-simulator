-- Synthetic CNC shop-floor dataset: schema.
-- Plain PostgreSQL 13+. Load with: psql -d <database> -f seed.sql  (drops and recreates the tables).

BEGIN;
DROP TABLE IF EXISTS machine_telemetry, alarm_events, edge_gateways, shift_schedules, nc_programs, machines, plants, organizations CASCADE;

CREATE TABLE organizations (
  organization_id BIGSERIAL PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE
);

CREATE TABLE plants (
  plant_id        BIGSERIAL PRIMARY KEY,
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  plant_code      TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  timezone        TEXT NOT NULL DEFAULT 'Europe/Warsaw'
);

CREATE TABLE machines (
  machine_id      BIGSERIAL PRIMARY KEY,
  plant_id        BIGINT NOT NULL REFERENCES plants (plant_id),
  machine_code    TEXT NOT NULL,
  name            TEXT NOT NULL,
  machine_type    TEXT NOT NULL CHECK (machine_type IN ('lathe', 'mill')),
  max_spindle_rpm INTEGER NOT NULL,
  UNIQUE (plant_id, machine_code)
);

-- ideal cycle time per NC program (used for OEE performance)
CREATE TABLE nc_programs (
  program_id          BIGSERIAL PRIMARY KEY,
  machine_id          BIGINT NOT NULL REFERENCES machines (machine_id),
  program_name        TEXT NOT NULL,
  ideal_cycle_seconds INTEGER NOT NULL CHECK (ideal_cycle_seconds > 0),
  UNIQUE (machine_id, program_name)
);

-- one row per organization and weekday (1 = Monday), local plant time
CREATE TABLE shift_schedules (
  schedule_id     BIGSERIAL PRIMARY KEY,
  organization_id BIGINT NOT NULL REFERENCES organizations (organization_id),
  weekday         SMALLINT NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  starts_at       TIME NOT NULL,
  ends_at         TIME NOT NULL,
  UNIQUE (organization_id, weekday, starts_at)
);

CREATE TABLE edge_gateways (
  plant_id       BIGINT PRIMARY KEY REFERENCES plants (plant_id),
  status         TEXT NOT NULL,
  last_report_at TIMESTAMPTZ NOT NULL
);

-- Readings: a row on every state change and then every 30 s.
-- A gap longer than 60 s without rows means "no data" (gateway offline), not an idle machine.
-- is_available = false: the machine is off or unreachable; the measurement columns are NULL.
CREATE TABLE machine_telemetry (
  machine_id             BIGINT NOT NULL REFERENCES machines (machine_id),
  recorded_at            TIMESTAMPTZ NOT NULL,
  is_available           BOOLEAN NOT NULL,
  execution_state        TEXT CHECK (execution_state IN ('ACTIVE', 'READY', 'STOPPED', 'FEED_HOLD', 'INTERRUPTED')),
  control_mode           TEXT CHECK (control_mode IN ('AUTOMATIC', 'MANUAL')),
  program_id             BIGINT REFERENCES nc_programs (program_id),
  part_counter           INTEGER,
  spindle_rpm            NUMERIC(8, 1),
  spindle_load_pct       NUMERIC(5, 1),
  feedrate               NUMERIC(8, 1),
  feed_override_pct      SMALLINT,
  spindle_override_pct   SMALLINT,
  rapid_override_pct     SMALLINT,
  emergency_stop_active  BOOLEAN,
  PRIMARY KEY (machine_id, recorded_at)
);
CREATE INDEX machine_telemetry_recorded_at_idx ON machine_telemetry (recorded_at);

-- one row per alarm episode
CREATE TABLE alarm_events (
  alarm_id   BIGSERIAL PRIMARY KEY,
  machine_id BIGINT NOT NULL REFERENCES machines (machine_id),
  severity   TEXT NOT NULL CHECK (severity IN ('FAULT', 'WARNING')),
  alarm_code TEXT NOT NULL,
  message    TEXT NOT NULL,
  raised_at  TIMESTAMPTZ NOT NULL,
  cleared_at TIMESTAMPTZ
);
CREATE INDEX alarm_events_machine_raised_idx ON alarm_events (machine_id, raised_at);

COMMIT;
