"""Synthetic CNC shop-floor data generator (nothing here comes from a real company). Usage: python3 generate.py <output_dir>"""
import csv, json, math, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

random.seed(20261020)
TZ = ZoneInfo("Europe/Warsaw")
OUT = Path(sys.argv[1])
START = datetime(2026, 9, 20, 0, 0, tzinfo=TZ)   # 30 pełnych dni: 20.09–19.10.2026
END = datetime(2026, 10, 20, 0, 0, tzinfo=TZ)
HEARTBEAT = 30  # s: a row is written on every state change and then every 30 s

COMPANIES = [(1, "Company A"), (2, "Company B")]
SITES = [("plant-1", "Plant 1", 1), ("plant-2", "Plant 2", 2), ("plant-3", "Plant 3", 2)]
# id, plant, name, type, max rpm, switched off at night?, programs {name: cycle time s}, fault rate (alarms/day), crew quality
MACHINES = [
    ("cnc-1", "plant-1", "Lathe 1", "lathe", 4000, True,  {"O1001": 95, "O1002": 140, "O1010": 60}, 0.6, 0.85),
    ("cnc-2", "plant-1", "Lathe 2", "lathe", 6000, True,  {"O2001": 210, "O2002": 320}, 0.4, 0.80),
    ("cnc-3", "plant-1", "Mill 1", "mill", 8100, False, {"O3001": 540, "O3002": 900, "O3005": 420}, 1.0, 0.70),
    ("cnc-4", "plant-2", "Mill 2", "mill", 12000, False, {"O4001": 380, "O4002": 610}, 0.8, 0.75),
    ("cnc-5", "plant-2", "Lathe 3", "lathe", 4500, True, {"O5001": 75, "O5002": 110}, 1.5, 0.65),
    ("cnc-6", "plant-3", "Lathe 4", "lathe", 3500, True, {"O6001": 180, "O6002": 260, "O6003": 150}, 0.5, 0.90),
]
ALARMS = [
    ("FAULT", "108", "SERVO OVERLOAD"), ("FAULT", "414", "SERVO ALARM: X AXIS EXCESS ERROR"),
    ("FAULT", "1011", "TOOL CHANGER FAULT"), ("FAULT", "160", "LOW VOLTAGE"),
    ("FAULT", "185", "LOW LUBE OIL"), ("FAULT", "9118", "DOOR OPEN DURING CYCLE"),
]
WARNINGS = [("WARNING", "W100", "TOOL LIFE T05 90%"), ("WARNING", "W210", "COOLANT LOW")]

def local(day, h, m=0, s=0):
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=TZ)

def jitter(a, b):
    return timedelta(seconds=random.uniform(a, b))

# ---- przerwy w łączności: komputer w hali nie działa (wtedy brak wierszy dla wszystkich maszyn hali) ----
def outages(site):
    out, n = [], {"plant-1": 2, "plant-2": 6, "plant-3": 3}[site]
    for _ in range(n):
        t0 = START + timedelta(seconds=random.uniform(0, (END - START).total_seconds()))
        out.append((t0, t0 + timedelta(minutes=random.choice([3, 8, 15, 40, 90, 240]))))
    if site == "plant-3":  # ktoś wyłączył komputer w piątek po pracy, włączony w poniedziałek
        out.append((local(datetime(2026, 10, 2), 15, 10), local(datetime(2026, 10, 5), 6, 20)))
    return sorted(out)

def in_outage(ts, outs):
    return any(a <= ts < b for a, b in outs)

# ---- symulacja: lista segmentów (początek, stan) – stan trwa do początku następnego segmentu ----
class Sim:
    def __init__(self, m):
        (self.id, self.site, self.name, self.kind, self.max_rpm, self.off_at_night,
         self.programs, self.alarm_rate, self.crew) = m
        self.seg = []
        self.parts = random.randint(1000, 30000)
        self.program = random.choice(list(self.programs))
        self.f_ovr = 100

    def add(self, t, **state):
        if self.seg and self.seg[-1][0] >= t:
            t = self.seg[-1][0] + timedelta(seconds=1)
        self.seg.append((t, state))
        return t

    def base(self, execution, mode="AUTOMATIC", alarms=None, running=False):
        return dict(available=True, execution=execution, mode=mode, estop="ARMED", program=self.program,
                    part_count=self.parts, spindle_override=100, feed_override=self.f_ovr, rapid_override=100,
                    alarms=alarms or [], running=running)

    def off(self, t):
        return self.add(t, available=False, alarms=[], error="connection")

    def idle(self, t, mode="MANUAL", execution="STOPPED"):
        return self.add(t, **self.base(execution, mode))

    def work(self, t, until):
        """Cykle produkcyjne od t do until z losowymi zdarzeniami."""
        ct = self.programs[self.program]
        while t < until:
            r = random.random()
            per_cycle_alarm = self.alarm_rate * ct / (7 * 3600)
            if r < per_cycle_alarm:  # alarm: przerwanie, potem operator kasuje i stoi
                sev, code, msg = random.choice(ALARMS)
                t = self.add(t, **self.base("INTERRUPTED", alarms=[{"severity": sev, "code": code, "message": msg, "type": "SYSTEM"}]))
                t += timedelta(minutes=random.choice([1, 2, 4, 8, 15, 30, 60]))
                t = self.idle(t, mode="MANUAL")
                t += jitter(60, 600)
                continue
            if r < per_cycle_alarm + 0.01:  # brak materiału / operator gdzie indziej
                t = self.idle(t, mode="AUTOMATIC", execution="READY")
                t += timedelta(minutes=random.uniform(10, 70))
                continue
            if r < per_cycle_alarm + 0.025:  # zmiana programu (przezbrojenie)
                t = self.idle(t, mode="MANUAL")
                t += timedelta(minutes=random.uniform(20, 75))
                self.program = random.choice([p for p in self.programs if p != self.program] or [self.program])
                ct = self.programs[self.program]
                continue
            if random.random() < 0.04 * (1.6 - self.crew):  # pomiar detalu, wymiana narzędzia, operator przy innej maszynie
                t = self.idle(t, mode=random.choice(["MANUAL", "AUTOMATIC"]), execution=random.choice(["STOPPED", "READY"]))
                t += timedelta(minutes=random.uniform(2, 25))
                continue
            if random.random() < 0.05:
                self.f_ovr = random.choice([80, 90, 100, 100, 100, 110, 120])
            # cykl
            cyc = ct * random.uniform(0.97, 1.08) * (100 / max(self.f_ovr, 50)) ** 0.5  # korekta posuwu skraca/wydłuża cykl
            t = self.add(t, **self.base("ACTIVE", running=True))
            if random.random() < 0.03:  # wstrzymanie posuwu w trakcie cyklu
                t += timedelta(seconds=cyc * random.uniform(0.2, 0.8))
                t = self.add(t, **self.base("FEED_HOLD"))
                t += jitter(10, 180)
                t = self.add(t, **self.base("ACTIVE", running=True))
                t += timedelta(seconds=cyc * 0.3)
            else:
                t += timedelta(seconds=cyc)
            if random.random() < 0.02:
                w = random.choice(WARNINGS)
                t = self.add(t, **self.base("ACTIVE", alarms=[{"severity": w[0], "code": w[1], "message": w[2], "type": "SYSTEM"}], running=True))
                t += jitter(5, 30)
            self.parts += 1
            t = self.add(t, **self.base("READY"))  # wymiana detalu
            t += jitter(15, 25 + 120 * (1 - self.crew))
        return t

    def day(self, day):
        dow = day.isoweekday()
        workday = dow <= 5 and random.random() > 0.03          # czasem cały dzień postoju (np. serwis, brak zleceń)
        saturday = dow == 6 and self.id in ("cnc-3", "cnc-4") and random.random() < 0.35
        if self.id == "cnc-1" and dow == 1:
            self.parts = 0  # operator zeruje licznik w poniedziałek
        if not (workday or saturday):
            return
        on = local(day, 5, 40) + jitter(0, 1500)
        if self.off_at_night:
            self.idle(on)
        t = local(day, 6, 0) + jitter(180, 300 + 1200 * (1 - self.crew))  # rozgrzewka, kawa, start
        self.idle(local(day, 5, 59) + jitter(0, 50), mode="MANUAL")
        if saturday:
            t = self.work(t, local(day, 11, 30) + jitter(0, 1800))
        else:
            t = self.work(t, local(day, 9, 55) + jitter(0, 600))
            t = self.idle(t, mode="AUTOMATIC", execution="READY")       # przerwa śniadaniowa
            t += timedelta(minutes=random.uniform(15, 25))
            overtime = random.random() < 0.12
            end = local(day, 15, 30) if overtime else local(day, 13, 40) + jitter(0, 900)
            t = self.work(t, end)
        t = self.idle(t, mode="MANUAL")
        if self.off_at_night:
            self.off(t + jitter(300, 1800))

    def run(self):
        if self.off_at_night:
            self.off(START)
        else:
            self.idle(START)
        d = START
        while d < END:
            self.day(d)
            d += timedelta(days=1)
        self.seg = [s for s in self.seg if s[0] < END]

# ---- turn segments into telemetry rows (on change + every 30 s) ----
def rows_for(sim, outs):
    rows = []
    ms = lambda dt: int(dt.timestamp() * 1000)
    for i, (t0, st) in enumerate(sim.seg):
        t1 = sim.seg[i + 1][0] if i + 1 < len(sim.seg) else END
        t0 = t0.astimezone(timezone.utc)
        # a row at the change itself (ms precision), then right after every :00/:30
        times = [t0]
        k = (ms(t0) // (HEARTBEAT * 1000) + 1) * HEARTBEAT * 1000
        end_ms = ms(t1)
        while k < end_ms:
            times.append(datetime.fromtimestamp((k + random.randint(50, 2900)) / 1000, timezone.utc))
            k += HEARTBEAT * 1000
        running = st.get("running", False)
        for ts in times:
            if ts >= END or in_outage(ts, outs):
                continue
            s = {k2: v for k2, v in st.items() if k2 != "running"}
            if s.get("available"):
                if running:
                    rpm = sim.max_rpm * random.uniform(0.45, 0.8)
                    s["spindle_speed"] = round(rpm, 1)
                    s["spindle_load"] = round(15 + 50 * rpm / sim.max_rpm + random.uniform(0, 12), 1)
                    s["feedrate"] = round((250 if sim.kind == "lathe" else 900) * s["feed_override"] / 100 * random.uniform(0.6, 1.2), 1)
                else:
                    s["spindle_speed"], s["spindle_load"], s["feedrate"] = 0, round(random.uniform(0, 3), 1), 0
            rows.append((ts, s))
    rows.sort(key=lambda r: r[0])
    out, last = [], None
    for ts, s in rows:
        ts = ts.replace(microsecond=ts.microsecond // 1000 * 1000)  # millisecond precision
        if last and ts <= last:
            continue
        out.append((ts, s)); last = ts
    return out

def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# ---- output naming ----
ORG_NAMES = {1: "Company A", 2: "Company B"}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    outs = {s[0]: outages(s[0]) for s in SITES}
    plants = [(i + 1, cid, code, f"Plant {i + 1}", "Europe/Warsaw") for i, (code, _, cid) in enumerate(SITES)]
    plant_id = {code: i + 1 for i, (code, _, _) in enumerate(SITES)}
    organizations = [(cid, ORG_NAMES[cid]) for cid, _ in COMPANIES]

    machines, programs, telemetry, alarms = [], [], [], []
    for n, m in enumerate(MACHINES, start=1):
        sim = Sim(m); sim.run()
        name = m[2]
        machines.append((n, plant_id[sim.site], f"CNC-{n:02d}", name, sim.kind, sim.max_rpm))
        pid = {}
        for prog, ct in m[6].items():
            pid[prog] = len(programs) + 1
            programs.append((pid[prog], n, prog, round(ct * 0.95)))
        for ts, st in rows_for(sim, outs[sim.site]):
            if st.get("available"):
                telemetry.append((n, iso(ts), "true", st["execution"], st["mode"], pid[st["program"]], st["part_count"],
                                  st["spindle_speed"], st["spindle_load"], st["feedrate"], st["feed_override"],
                                  st["spindle_override"], st["rapid_override"], "false"))
            else:
                telemetry.append((n, iso(ts), "false") + ("",) * 11)
        for i, (t0, st) in enumerate(sim.seg):  # one alarm episode per segment that carries an alarm
            if st.get("alarms") and not in_outage(t0, outs[sim.site]) and t0 < END:
                t1 = sim.seg[i + 1][0] if i + 1 < len(sim.seg) else END
                for a in st["alarms"]:
                    alarms.append((n, a["severity"], a["code"], a["message"], iso(t0), iso(min(t1, END))))
    telemetry.sort(key=lambda r: (r[1], r[0]))
    alarms.sort(key=lambda r: (r[4], r[0]))
    alarms = [(i + 1,) + a for i, a in enumerate(alarms)]
    schedules = [(i + 1, cid, wd, "06:00", "14:00") for i, (cid, wd) in enumerate((c, d) for c, _ in COMPANIES for d in range(1, 6))]
    gateways = [(pl[0], "online", iso(END)) for pl in plants]

    tables = {
        "organizations": (["organization_id", "name"], organizations),
        "plants": (["plant_id", "organization_id", "plant_code", "name", "timezone"], plants),
        "machines": (["machine_id", "plant_id", "machine_code", "name", "machine_type", "max_spindle_rpm"], machines),
        "nc_programs": (["program_id", "machine_id", "program_name", "ideal_cycle_seconds"], programs),
        "shift_schedules": (["schedule_id", "organization_id", "weekday", "starts_at", "ends_at"], schedules),
        "edge_gateways": (["plant_id", "status", "last_report_at"], gateways),
        "alarm_events": (["alarm_id", "machine_id", "severity", "alarm_code", "message", "raised_at", "cleared_at"], alarms),
        "machine_telemetry": (["machine_id", "recorded_at", "is_available", "execution_state", "control_mode", "program_id",
                               "part_counter", "spindle_rpm", "spindle_load_pct", "feedrate", "feed_override_pct",
                               "spindle_override_pct", "rapid_override_pct", "emergency_stop_active"], telemetry),
    }
    (OUT / "csv").mkdir(exist_ok=True)
    for name, (cols, data) in tables.items():
        with open(OUT / "csv" / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(data)

    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    def esc(v):
        return "\\N" if v == "" else str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
    with open(OUT / "seed.sql", "w", encoding="utf-8") as f:
        f.write(schema)
        for name, (cols, data) in tables.items():
            f.write(f"\nCOPY {name} ({', '.join(cols)}) FROM stdin;\n")
            for r in data:
                f.write("\t".join(esc(v) for v in r) + "\n")
            f.write("\\.\n")
        for seq, col, tbl in [("organizations_organization_id_seq", "organization_id", "organizations"), ("plants_plant_id_seq", "plant_id", "plants"),
                              ("machines_machine_id_seq", "machine_id", "machines"), ("nc_programs_program_id_seq", "program_id", "nc_programs"),
                              ("shift_schedules_schedule_id_seq", "schedule_id", "shift_schedules"), ("alarm_events_alarm_id_seq", "alarm_id", "alarm_events")]:
            f.write(f"SELECT setval('{seq}', (SELECT max({col}) FROM {tbl}));\n")
        f.write("ANALYZE;\n")
    print(f"telemetry={len(telemetry)} alarms={len(alarms)} machines={len(machines)}")

main()
