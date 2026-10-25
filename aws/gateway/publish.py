"""Shop-floor edge gateway simulator.

Replays one production day of synthetic CNC telemetry and publishes it to AWS IoT over MQTT,
the same way a data-collection computer on a real shop floor would. Each plant has its own gateway
(its own MQTT client and X.509 certificate) that only publishes data of the machines in its plant.

Usage (from the repository root):
    python aws/gateway/publish.py --dry-run                 # print messages, no AWS needed
    python aws/gateway/publish.py --speed 600               # all gateways, 10 minutes of data per second
    python aws/gateway/publish.py --gateway gw-plant-1 --start 06:00 --minutes 60

Real gateways are not perfect, so by default the replay adds the problems the silver layer has to fix:
  * duplicates   - QoS 1 means "at least once", so a message is occasionally delivered twice
  * late arrival - a message is sometimes sent a few seconds after newer ones (out of order)
Connection gaps (hours without data) are already part of the generated data.
"""
import argparse
import csv
import json
import random
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "sample"
CONFIG = ROOT / "aws" / "certs" / "gateway-config.json"
SCHEMA = "cnc-telemetry/v1"
ID_NAMESPACE = uuid.UUID("6f1c2a52-6c1e-4a7e-9a35-0d2f6d0b8c11")  # fixed, so message ids are reproducible

TELEMETRY_FIELDS = ["execution_state", "control_mode", "program_id", "part_counter", "spindle_rpm",
                    "spindle_load_pct", "feedrate", "feed_override_pct", "spindle_override_pct",
                    "rapid_override_pct", "emergency_stop_active"]
INTS = {"program_id", "part_counter", "feed_override_pct", "spindle_override_pct", "rapid_override_pct"}
FLOATS = {"spindle_rpm", "spindle_load_pct", "feedrate"}


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(ts):
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def value(name, raw):
    if raw == "":
        return None
    if name in INTS:
        return int(raw)
    if name in FLOATS:
        return float(raw)
    if name == "emergency_stop_active":
        return raw == "true"
    return raw


def shifter(sample_day, target_day, tz):
    """Move a timestamp from the sample day to the target day keeping the plant's local clock time
    (a plain UTC offset would be an hour off across a daylight-saving change)."""
    def move(ts):
        local = ts.astimezone(tz)
        moved = datetime.combine(target_day + (local.date() - sample_day), local.time(), tz)
        return moved.astimezone(timezone.utc)
    return move


def load_events(day_file, alarm_file, shift):
    """Turn the sample CSVs into one time-ordered list of (event_time, gateway, topic_suffix, payload)."""
    machines = {r["machine_id"]: r for r in csv.DictReader(open(SAMPLE / "machines.csv", newline=""))}
    gateway_of = {mid: f"gw-plant-{m['plant_id']}" for mid, m in machines.items()}
    events = []

    for r in csv.DictReader(open(day_file, newline="")):
        m = machines[r["machine_id"]]
        ts = shift(parse_ts(r["recorded_at"]))
        payload = {"recorded_at": iso(ts), "is_available": r["is_available"] == "true"}
        payload.update({f: value(f, r[f]) for f in TELEMETRY_FIELDS})
        events.append((ts, gateway_of[r["machine_id"]], m["machine_code"], "telemetry", payload))

    # alarms are sent as two events, like a controller does: raised, and later cleared
    for r in csv.DictReader(open(alarm_file, newline="")):
        m = machines[r["machine_id"]]
        base = {"alarm_ref": r["alarm_id"], "severity": r["severity"], "alarm_code": r["alarm_code"], "message": r["message"]}
        raised = shift(parse_ts(r["raised_at"]))
        events.append((raised, gateway_of[r["machine_id"]], m["machine_code"], "alarms",
                       {**base, "event": "raised", "event_at": iso(raised)}))
        if r["cleared_at"]:
            cleared = shift(parse_ts(r["cleared_at"]))
            events.append((cleared, gateway_of[r["machine_id"]], m["machine_code"], "alarms",
                           {**base, "event": "cleared", "event_at": iso(cleared)}))

    events.sort(key=lambda e: e[0])
    return events


def envelope(gateway, machine_code, kind, payload):
    """Wrap a reading with the metadata every message carries."""
    key = f"{machine_code}|{kind}|{payload.get('recorded_at') or payload['event_at']}|{payload.get('event', '')}"
    return {
        "schema": SCHEMA,
        "message_id": str(uuid.uuid5(ID_NAMESPACE, key)),  # same reading -> same id, so duplicates can be found
        "gateway_id": gateway,
        "machine_code": machine_code,
        "type": kind,
        **payload,
        "sent_at": iso(datetime.now(timezone.utc)),
    }


class Sender:
    """One MQTT connection per gateway, authenticated with that gateway's certificate."""
    printed = 0  # dry run: show only the first few messages in total

    def __init__(self, gateway, cfg, dry_run):
        self.gateway, self.dry_run, self.sent = gateway, dry_run, 0
        if dry_run:
            return
        import paho.mqtt.client as mqtt  # imported here so --dry-run works without the package

        g = cfg["gateways"][gateway]
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=gateway)  # client id must equal thing name
        self.client.tls_set(ca_certs=cfg["root_ca"], certfile=g["certificate"], keyfile=g["private_key"])
        self.client.connect(cfg["endpoint"], 8883, keepalive=60)
        self.client.loop_start()

    def send(self, machine_code, kind, message):
        topic = f"cnc-sim/{self.gateway}/{machine_code}/{kind}"
        body = json.dumps(message, separators=(",", ":"))
        self.sent += 1
        if self.dry_run:
            if Sender.printed < 3:
                Sender.printed += 1
                print(f"[{self.gateway}] {topic}\n    {body}")
            return
        self.last = self.client.publish(topic, body, qos=1)

    def close(self):
        if not self.dry_run:
            if getattr(self, "last", None):
                self.last.wait_for_publish(timeout=15)  # QoS 1: wait for AWS to acknowledge the last message
            self.client.loop_stop()
            self.client.disconnect()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--gateway", default="all", help="gw-plant-1, gw-plant-2, gw-plant-3 or all (default)")
    p.add_argument("--speed", type=float, default=60, help="replay speed, 60 = one hour of data per minute")
    p.add_argument("--start", default="00:00", help="local time of day to start the replay from, e.g. 06:00")
    p.add_argument("--minutes", type=float, help="how many minutes of production data to send (default: rest of the day)")
    p.add_argument("--as-of", default=date.today().isoformat(),
                   help="date the replayed day is shifted to (default: today), so data looks fresh")
    p.add_argument("--no-chaos", action="store_true", help="send perfect data: no duplicates, no late messages")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--dry-run", action="store_true", help="print the first messages and totals, connect to nothing")
    a = p.parse_args()

    tz = ZoneInfo("Europe/Warsaw")  # plant local time
    shift = shifter(date(2026, 10, 14), date.fromisoformat(a.as_of), tz)
    events = load_events(SAMPLE / "machine_telemetry_2026-10-14.csv", SAMPLE / "alarm_events_2026-10-14.csv", shift)

    # cut the requested time window
    h, m = map(int, a.start.split(":"))
    t0 = datetime.combine(date.fromisoformat(a.as_of), datetime.min.time(), tz).replace(hour=h, minute=m)
    t1 = t0 + timedelta(minutes=a.minutes) if a.minutes else t0 + timedelta(days=1)
    events = [e for e in events if t0 <= e[0] < t1 and (a.gateway == "all" or e[1] == a.gateway)]
    if not events:
        sys.exit("No events in the selected window.")

    cfg = {} if a.dry_run else json.loads(CONFIG.read_text())
    gateways = sorted({e[1] for e in events})
    senders = {g: Sender(g, cfg, a.dry_run) for g in gateways}

    rnd = random.Random(a.seed)
    late = []  # messages held back to arrive out of order: (send_after_wallclock, gateway, machine, kind, msg)
    dup = lateness = 0
    data_start, wall_start = events[0][0], time.monotonic()
    print(f"Replaying {len(events)} events {iso(events[0][0])} .. {iso(events[-1][0])} at {a.speed:g}x "
          f"through {', '.join(gateways)}" + (" (dry run)" if a.dry_run else ""))

    try:
        for ts, g, machine, kind, payload in events:
            if not a.dry_run:  # wait until this reading is "due" at the chosen speed
                due = wall_start + (ts - data_start).total_seconds() / a.speed
                while (now := time.monotonic()) < due:
                    for item in [x for x in late if x[0] <= now]:
                        late.remove(item)
                        senders[item[1]].send(*item[2:])
                    time.sleep(min(0.05, due - now))
            msg = envelope(g, machine, kind, payload)
            if not a.no_chaos and kind == "telemetry" and rnd.random() < 0.005:
                late.append((time.monotonic() + rnd.uniform(2, 8), g, machine, kind, msg))
                lateness += 1
                continue
            senders[g].send(machine, kind, msg)
            if not a.no_chaos and rnd.random() < 0.005:
                senders[g].send(machine, kind, msg)  # the same message again: an at-least-once redelivery
                dup += 1
        for item in late:  # flush anything still held back
            senders[item[1]].send(*item[2:])
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        for s in senders.values():
            s.close()
    total = sum(s.sent for s in senders.values())
    print(f"Sent {total} messages ({dup} duplicates, {lateness} late).")


if __name__ == "__main__":
    main()
