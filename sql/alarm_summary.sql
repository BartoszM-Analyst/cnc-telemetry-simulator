-- Alarm episodes per machine: count, total duration of faults and the most frequent alarm.
SELECT m.name,
       p.name AS plant,
       count(*) FILTER (WHERE a.severity = 'FAULT')   AS faults,
       count(*) FILTER (WHERE a.severity = 'WARNING') AS warnings,
       round(coalesce(sum(extract(epoch FROM a.cleared_at - a.raised_at)) FILTER (WHERE a.severity = 'FAULT'), 0) / 3600, 1) AS fault_hours,
       mode() WITHIN GROUP (ORDER BY a.message) AS most_common_alarm
  FROM machines m
  JOIN plants p USING (plant_id)
  LEFT JOIN alarm_events a USING (machine_id)
 GROUP BY m.machine_id, m.name, p.name
 ORDER BY m.machine_id;
