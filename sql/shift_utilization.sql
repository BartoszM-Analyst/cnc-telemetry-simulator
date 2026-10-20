-- Share of time each machine spends cutting (execution_state = 'ACTIVE') during planned shifts.
-- Shift windows come from shift_schedules, converted to each plant's local time.
-- Each reading lasts until the next one, capped at 60 s, so gateway outages are not counted as production.
WITH samples AS (
  SELECT machine_id, recorded_at, execution_state,
         least(extract(epoch FROM lead(recorded_at) OVER w - recorded_at), 60) AS seconds
    FROM machine_telemetry
  WINDOW w AS (PARTITION BY machine_id ORDER BY recorded_at)
)
SELECT m.name,
       round(100 * sum(s.seconds) FILTER (WHERE s.execution_state = 'ACTIVE') / sum(s.seconds)) AS cutting_pct
  FROM samples s
  JOIN machines m USING (machine_id)
  JOIN plants p USING (plant_id)
  JOIN shift_schedules sh
    ON sh.organization_id = p.organization_id
   AND sh.weekday = extract(isodow FROM s.recorded_at AT TIME ZONE p.timezone)
   AND (s.recorded_at AT TIME ZONE p.timezone)::time >= sh.starts_at
   AND (s.recorded_at AT TIME ZONE p.timezone)::time <  sh.ends_at
 GROUP BY m.machine_id, m.name
 ORDER BY m.machine_id;
