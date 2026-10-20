"""Builds docs/demo-data.js (one day from sample/) for the browser demo. Run: python3 tools/build_demo_data.py"""
import csv, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAY_START = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)  # 14 Oct 2026 00:00 Europe/Warsaw
EX = {"ACTIVE": 2, "READY": 3, "STOPPED": 4, "FEED_HOLD": 5, "INTERRUPTED": 6}

def read(name):
    with open(ROOT / "sample" / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

plants = {r["plant_id"]: r["name"] for r in read("plants.csv")}
programs = {r["program_id"]: r["program_name"] for r in read("nc_programs.csv")}
machines = read("machines.csv")
episodes = {}
for r in read("alarm_events_2026-10-14.csv"):
    episodes.setdefault(r["machine_id"], []).append((parse(r["raised_at"]), parse(r["cleared_at"]), r))

program_names, alarm_defs, alarm_idx = [], [], {}
out = {m["machine_id"]: {"id": m["machine_id"], "name": m["name"], "site": plants[m["plant_id"]], "t": [], "ex": [],
                          "prog": [], "pc": [], "rpm": [], "load": [], "feed": [], "al": []} for m in machines}

for r in read("machine_telemetry_2026-10-14.csv"):
    o = out[r["machine_id"]]; ts = parse(r["recorded_at"])
    o["t"].append(round((ts - DAY_START).total_seconds(), 1))
    if r["is_available"] != "true":
        o["ex"].append(1); o["prog"].append(-1); o["pc"].append(0)
        o["rpm"].append(0); o["load"].append(0); o["feed"].append(0); o["al"].append("")
        continue
    o["ex"].append(EX[r["execution_state"]] + (10 if r["control_mode"] == "MANUAL" else 0))
    name = programs[r["program_id"]]
    if name not in program_names: program_names.append(name)
    o["prog"].append(program_names.index(name)); o["pc"].append(int(r["part_counter"]))
    o["rpm"].append(round(float(r["spindle_rpm"]))); o["load"].append(round(float(r["spindle_load_pct"]))); o["feed"].append(round(float(r["feedrate"])))
    ids = []
    for a, b, e in episodes.get(r["machine_id"], []):
        if a <= ts < b:
            k = (e["severity"], e["alarm_code"], e["message"])
            if k not in alarm_idx: alarm_idx[k] = len(alarm_defs); alarm_defs.append({"sev": k[0], "code": k[1], "msg": k[2]})
            ids.append(alarm_idx[k])
    o["al"].append(",".join(map(str, ids)))

for o in out.values():
    o["maxrpm"] = max(o["rpm"]) or 1
data = {"date": "2026-10-14", "programs": program_names, "alarms": alarm_defs, "machines": list(out.values())}
p = ROOT / "docs/demo-data.js"
p.write_text("window.DEMO=" + json.dumps(data, separators=(",", ":")) + ";\n", encoding="utf-8")
print(p, p.stat().st_size // 1024, "KB")
