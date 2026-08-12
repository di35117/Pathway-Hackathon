"""
LiveCold Pathway MQTT Bridge — 4-stream streaming ingestion.

Bridges all four cold-chain IoT telemetry streams from MQTT into Pathway tables
and processes them as a single incremental dataflow:

    livecold/temp    ──┐
    livecold/gps     ──┤   pw.io.python.ConnectorSubject
    livecold/reefer  ──┼──▶  (one subject per stream, 4 concurrent readers)
    livecold/door    ──┘
                         │
                         ├──▶ per-stream validation + enrichment (UDFs)
                         ├──▶ union into a unified telemetry table
                         ├──▶ windowed per-shipment aggregation
                         └──▶ CSV sinks + latency measurement

Each stream is its own `ConnectorSubject` with its own schema and its own MQTT
subscription, so the four run concurrently and Pathway joins them in the
dataflow rather than in Python.

Latency is measured per event: sensors stamp `ts` at publish time, and the
ingest UDF compares it against arrival time. Percentiles are written to
./metrics/pathway_latency.csv so the sub-second claim is measured, not asserted.

Run:  python main.py pathway-bridge
"""

import json
import os
import threading
import time
from collections import deque
from datetime import datetime, UTC

import pathway as pw
import paho.mqtt.client as mqtt

BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))

TEMP_TOPIC = "livecold/temp"
GPS_TOPIC = "livecold/gps"
REEFER_TOPIC = "livecold/reefer"
DOOR_TOPIC = "livecold/door"

METRICS_DIR = "./metrics"

# Physically impossible readings — rejected before they reach any aggregate.
ABSOLUTE_MIN_C = -90.0
ABSOLUTE_MAX_C = 60.0


# ══════════════════════════════════════════════════════════════════
#  Latency instrumentation
# ══════════════════════════════════════════════════════════════════

_latency = {topic: deque(maxlen=2000) for topic in
            (TEMP_TOPIC, GPS_TOPIC, REEFER_TOPIC, DOOR_TOPIC)}
_latency_lock = threading.Lock()
_counts = dict.fromkeys(_latency, 0)


def _record_latency(topic, published_iso):
    """Ingest latency = now - the timestamp the sensor stamped at publish."""
    with _latency_lock:
        _counts[topic] += 1
    if not published_iso:
        return
    try:
        published = datetime.fromisoformat(published_iso)
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        delta_ms = (datetime.now(UTC) - published).total_seconds() * 1000.0
        # Guard against clock skew between publisher and consumer.
        if -1000 < delta_ms < 60_000:
            with _latency_lock:
                _latency[topic].append(delta_ms)
    except (ValueError, TypeError):
        pass


def latency_report():
    """Percentile summary per stream, plus a combined view."""
    with _latency_lock:
        snapshot = {t: list(v) for t, v in _latency.items()}
        counts = dict(_counts)

    def pct(samples):
        if not samples:
            return {"p50_ms": None, "p95_ms": None, "p99_ms": None, "samples": 0}
        s = sorted(samples)
        n = len(s)
        return {
            "p50_ms": round(s[n // 2], 2),
            "p95_ms": round(s[min(n - 1, int(n * 0.95))], 2),
            "p99_ms": round(s[min(n - 1, int(n * 0.99))], 2),
            "samples": n,
        }

    report = {topic: {**pct(samples), "events_received": counts[topic]}
              for topic, samples in snapshot.items()}

    combined = [x for samples in snapshot.values() for x in samples]
    report["_combined"] = pct(combined)
    report["_combined"]["sub_second_pct"] = (
        round(100.0 * sum(1 for x in combined if x < 1000) / len(combined), 2)
        if combined else None
    )
    report["_combined"]["streams_active"] = sum(1 for c in counts.values() if c > 0)
    return report


def _latency_writer():
    """Append a latency snapshot to CSV every 15 seconds."""
    os.makedirs(METRICS_DIR, exist_ok=True)
    path = os.path.join(METRICS_DIR, "pathway_latency.csv")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("timestamp,stream,p50_ms,p95_ms,p99_ms,samples,events_received\n")

    while True:
        time.sleep(15)
        report = latency_report()
        now = datetime.now(UTC).isoformat()
        try:
            with open(path, "a", encoding="utf-8") as f:
                for stream, stats in report.items():
                    if stats.get("samples"):
                        f.write(
                            f"{now},{stream},{stats['p50_ms']},{stats['p95_ms']},"
                            f"{stats['p99_ms']},{stats['samples']},"
                            f"{stats.get('events_received', '')}\n"
                        )
            c = report["_combined"]
            if c["samples"]:
                print(f"  [latency] {c['streams_active']}/4 streams | "
                      f"p50={c['p50_ms']}ms p95={c['p95_ms']}ms "
                      f"| sub-second {c['sub_second_pct']}%")
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════
#  Pathway schemas — one per telemetry stream
# ══════════════════════════════════════════════════════════════════

class TempEventSchema(pw.Schema):
    timestamp: str
    shipment_id: str
    sensor_id: str
    temp_c: float
    product_type: str
    safe_min_temp: float
    safe_max_temp: float
    cargo_value_inr: float
    ingest_latency_ms: float


class GpsEventSchema(pw.Schema):
    timestamp: str
    shipment_id: str
    lat: float
    lon: float
    speed_kmph: float
    eta_minutes_remaining: float
    ingest_latency_ms: float


class ReeferEventSchema(pw.Schema):
    timestamp: str
    shipment_id: str
    compressor_status: str
    setpoint_c: float
    power_draw_kw: float
    compressor_cycles: int
    ingest_latency_ms: float


class DoorEventSchema(pw.Schema):
    timestamp: str
    shipment_id: str
    event_type: str
    duration_seconds: float
    g_force: float
    ingest_latency_ms: float


# ══════════════════════════════════════════════════════════════════
#  MQTT -> Pathway connector subjects
# ══════════════════════════════════════════════════════════════════

class MQTTStreamSubject(pw.io.python.ConnectorSubject):
    """
    Pushes one MQTT topic into a Pathway table.

    Subclass of ConnectorSubject: `run()` blocks on the MQTT network loop and
    calls `self.next(**row)` for each message, which appends a row to the
    Pathway table and triggers incremental recomputation downstream.
    """

    def __init__(self, topic, row_builder, client_suffix):
        super().__init__()
        self.topic = topic
        self.row_builder = row_builder
        self.client_suffix = client_suffix

    def run(self):
        def on_message(client, userdata, msg):
            try:
                data = json.loads(msg.payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                return

            published = data.get("ts")
            _record_latency(self.topic, published)

            latency_ms = 0.0
            if published:
                try:
                    p = datetime.fromisoformat(published)
                    if p.tzinfo is None:
                        p = p.replace(tzinfo=UTC)
                    latency_ms = max(
                        0.0,
                        (datetime.now(UTC) - p).total_seconds() * 1000.0,
                    )
                except (ValueError, TypeError):
                    latency_ms = 0.0

            row = self.row_builder(data, latency_ms)
            if row is not None:
                self.next(**row)

        client = mqtt.Client(client_id=f"pathway-bridge-{self.client_suffix}")
        client.on_message = on_message
        client.connect(BROKER, PORT)
        client.subscribe(self.topic)
        print(f"  connected: {self.topic}")
        client.loop_forever()


def _temp_row(data, latency_ms):
    if "temp_c" not in data or "shipment_id" not in data:
        return None
    return {
        "timestamp": data.get("ts", ""),
        "shipment_id": data["shipment_id"],
        "sensor_id": data.get("sensor_id", "PALLET_1"),
        "temp_c": float(data["temp_c"]),
        "product_type": data.get("product_type", "Generic"),
        "safe_min_temp": float(data.get("safe_min_temp", 2.0)),
        "safe_max_temp": float(data.get("safe_max_temp", 8.0)),
        "cargo_value_inr": float(data.get("cargo_value_inr", 500000.0)),
        "ingest_latency_ms": latency_ms,
    }


def _gps_row(data, latency_ms):
    if "lat" not in data or "shipment_id" not in data:
        return None
    return {
        "timestamp": data.get("ts", ""),
        "shipment_id": data["shipment_id"],
        "lat": float(data["lat"]),
        "lon": float(data.get("lon", 0.0)),
        "speed_kmph": float(data.get("speed_kmph", 0.0)),
        "eta_minutes_remaining": float(data.get("eta_minutes_remaining", 0.0)),
        "ingest_latency_ms": latency_ms,
    }


def _reefer_row(data, latency_ms):
    if "compressor_status" not in data or "shipment_id" not in data:
        return None
    return {
        "timestamp": data.get("ts", ""),
        "shipment_id": data["shipment_id"],
        "compressor_status": data.get("compressor_status", "ON"),
        "setpoint_c": float(data.get("setpoint_c", 0.0)),
        "power_draw_kw": float(data.get("power_draw_kw", 0.0)),
        "compressor_cycles": int(data.get("compressor_cycles", 0)),
        "ingest_latency_ms": latency_ms,
    }


def _door_row(data, latency_ms):
    if "event_type" not in data or "shipment_id" not in data:
        return None
    return {
        "timestamp": data.get("ts", ""),
        "shipment_id": data["shipment_id"],
        "event_type": data.get("event_type", ""),
        "duration_seconds": float(data.get("duration_seconds", 0.0)),
        "g_force": float(data.get("g_force", 0.0)),
        "ingest_latency_ms": latency_ms,
    }


# ══════════════════════════════════════════════════════════════════
#  Dataflow UDFs
# ══════════════════════════════════════════════════════════════════

@pw.udf
def is_valid_reading(temp: float) -> bool:
    """Reject readings outside any physically possible cold-chain value."""
    return ABSOLUTE_MIN_C <= temp <= ABSOLUTE_MAX_C


@pw.udf
def is_excursion(temp: float, safe_min: float, safe_max: float) -> bool:
    return temp < safe_min or temp > safe_max


@pw.udf
def excursion_severity(temp: float, safe_min: float, safe_max: float) -> float:
    """Normalised distance outside the safe band; 5 C out is full scale."""
    if temp > safe_max:
        return min((temp - safe_max) / 5.0, 1.0)
    if temp < safe_min:
        return min((safe_min - temp) / 5.0, 1.0)
    return 0.0


@pw.udf
def compute_risk_score(severity: float, cargo_value: float) -> float:
    """
    Screening score for the streaming view.

    Deliberately simple: this is a triage signal over the raw stream, not the
    authoritative decision. Risk that drives diversions is computed by
    risk_engine_v2 in the pipeline process, which has the stateful context
    (exposure history, drift regression) that a per-event UDF cannot see.
    """
    value_factor = min(cargo_value / 2_500_000.0, 1.0)
    return round(min(severity * 0.7 + value_factor * 0.3, 1.0), 3)


@pw.udf
def compressor_health(status: str, power_kw: float) -> str:
    if status != "ON":
        return "OFF"
    if power_kw > 3.2:
        return "STRAINING"
    if power_kw < 0.5:
        return "SUSPECT"
    return "NORMAL"


@pw.udf
def door_impact(event_type: str, duration_sec: float) -> float:
    """Thermal impact of a door event; 5 minutes open is full scale."""
    if event_type != "door_open":
        return 0.0
    return round(min(duration_sec / 300.0, 1.0), 3)


@pw.udf
def shock_severity(event_type: str, g_force: float) -> float:
    if event_type != "shock":
        return 0.0
    return round(min(g_force / 5.0, 1.0), 3)


# ══════════════════════════════════════════════════════════════════
#  Pipeline
# ══════════════════════════════════════════════════════════════════

def build_pathway_pipeline():
    """Build and run the 4-stream Pathway dataflow."""

    print("\n" + "=" * 62)
    print("LiveCold Pathway MQTT Bridge - 4 concurrent telemetry streams")
    print("=" * 62)

    os.makedirs(METRICS_DIR, exist_ok=True)

    # ── Step 1: four concurrent MQTT -> Pathway readers ──────────
    temp_events = pw.io.python.read(
        MQTTStreamSubject(TEMP_TOPIC, _temp_row, "temp"),
        schema=TempEventSchema,
    )
    gps_events = pw.io.python.read(
        MQTTStreamSubject(GPS_TOPIC, _gps_row, "gps"),
        schema=GpsEventSchema,
    )
    reefer_events = pw.io.python.read(
        MQTTStreamSubject(REEFER_TOPIC, _reefer_row, "reefer"),
        schema=ReeferEventSchema,
    )
    door_events = pw.io.python.read(
        MQTTStreamSubject(DOOR_TOPIC, _door_row, "door"),
        schema=DoorEventSchema,
    )
    print("  4 ConnectorSubjects -> 4 Pathway tables")

    # ── Step 2: temperature — filter, then enrich ────────────────
    valid_temp = temp_events.filter(is_valid_reading(temp_events.temp_c))

    temp_enriched = valid_temp.select(
        shipment_id=valid_temp.shipment_id,
        timestamp=valid_temp.timestamp,
        temp_c=valid_temp.temp_c,
        product_type=valid_temp.product_type,
        cargo_value_inr=valid_temp.cargo_value_inr,
        ingest_latency_ms=valid_temp.ingest_latency_ms,
        is_excursion=is_excursion(
            valid_temp.temp_c, valid_temp.safe_min_temp, valid_temp.safe_max_temp
        ),
        severity=excursion_severity(
            valid_temp.temp_c, valid_temp.safe_min_temp, valid_temp.safe_max_temp
        ),
    )

    temp_scored = temp_enriched.select(
        *pw.this,
        risk_score=compute_risk_score(
            temp_enriched.severity, temp_enriched.cargo_value_inr
        ),
    )
    print("  temp:   bounds filter -> excursion detection -> risk score")

    # ── Step 3: reefer — compressor health classification ────────
    reefer_scored = reefer_events.select(
        shipment_id=reefer_events.shipment_id,
        timestamp=reefer_events.timestamp,
        compressor_status=reefer_events.compressor_status,
        power_draw_kw=reefer_events.power_draw_kw,
        compressor_cycles=reefer_events.compressor_cycles,
        ingest_latency_ms=reefer_events.ingest_latency_ms,
        health=compressor_health(
            reefer_events.compressor_status, reefer_events.power_draw_kw
        ),
    )
    print("  reefer: compressor health classification")

    # ── Step 4: door — thermal and shock impact ──────────────────
    door_scored = door_events.select(
        shipment_id=door_events.shipment_id,
        timestamp=door_events.timestamp,
        event_type=door_events.event_type,
        ingest_latency_ms=door_events.ingest_latency_ms,
        thermal_impact=door_impact(
            door_events.event_type, door_events.duration_seconds
        ),
        shock_impact=shock_severity(door_events.event_type, door_events.g_force),
    )
    print("  door:   thermal impact + shock severity")

    # ── Step 5: gps — movement view ──────────────────────────────
    gps_scored = gps_events.select(
        shipment_id=gps_events.shipment_id,
        timestamp=gps_events.timestamp,
        lat=gps_events.lat,
        lon=gps_events.lon,
        speed_kmph=gps_events.speed_kmph,
        eta_minutes_remaining=gps_events.eta_minutes_remaining,
        ingest_latency_ms=gps_events.ingest_latency_ms,
    )
    print("  gps:    position and ETA")

    # ── Step 6: per-shipment aggregates across streams ───────────
    # Each groupby is an incremental Pathway reducer: adding one row updates
    # only the affected group rather than recomputing the whole table.
    temp_agg = temp_scored.groupby(pw.this.shipment_id).reduce(
        shipment_id=pw.this.shipment_id,
        readings=pw.reducers.count(),
        avg_temp=pw.reducers.avg(pw.this.temp_c),
        max_temp=pw.reducers.max(pw.this.temp_c),
        min_temp=pw.reducers.min(pw.this.temp_c),
        max_risk=pw.reducers.max(pw.this.risk_score),
        avg_ingest_latency_ms=pw.reducers.avg(pw.this.ingest_latency_ms),
    )

    door_agg = door_scored.groupby(pw.this.shipment_id).reduce(
        shipment_id=pw.this.shipment_id,
        door_events=pw.reducers.count(),
        total_thermal_impact=pw.reducers.sum(pw.this.thermal_impact),
        max_shock=pw.reducers.max(pw.this.shock_impact),
    )

    reefer_agg = reefer_scored.groupby(pw.this.shipment_id).reduce(
        shipment_id=pw.this.shipment_id,
        reefer_readings=pw.reducers.count(),
        avg_power_kw=pw.reducers.avg(pw.this.power_draw_kw),
        max_cycles=pw.reducers.max(pw.this.compressor_cycles),
    )
    print("  aggregates: per-shipment reducers on 3 streams")

    # ── Step 7: cross-stream join — the unified fleet view ───────
    # This is the payoff of ingesting all four through Pathway: temperature,
    # door and reefer signals for one shipment combined in the dataflow.
    fleet_view = temp_agg.join(
        door_agg, pw.left.shipment_id == pw.right.shipment_id, how=pw.JoinMode.LEFT
    ).select(
        *pw.left,
        door_events=pw.right.door_events,
        total_thermal_impact=pw.right.total_thermal_impact,
        max_shock=pw.right.max_shock,
    ).join(
        reefer_agg, pw.left.shipment_id == pw.right.shipment_id, how=pw.JoinMode.LEFT
    ).select(
        *pw.left,
        reefer_readings=pw.right.reefer_readings,
        avg_power_kw=pw.right.avg_power_kw,
        max_cycles=pw.right.max_cycles,
    )
    print("  join: temp + door + reefer -> unified fleet view")

    # ── Step 8: sinks ────────────────────────────────────────────
    pw.io.csv.write(temp_scored, f"{METRICS_DIR}/pathway_risk_scores.csv")
    pw.io.csv.write(gps_scored, f"{METRICS_DIR}/pathway_gps.csv")
    pw.io.csv.write(reefer_scored, f"{METRICS_DIR}/pathway_reefer.csv")
    pw.io.csv.write(door_scored, f"{METRICS_DIR}/pathway_door.csv")
    pw.io.csv.write(fleet_view, f"{METRICS_DIR}/pathway_fleet_view.csv")
    print(f"  sinks: 5 CSV outputs in {METRICS_DIR}/")

    # ── Step 9: latency reporter ─────────────────────────────────
    threading.Thread(target=_latency_writer, daemon=True, name="LatencyWriter").start()

    print("=" * 62)
    print(f"  Ingesting from MQTT {BROKER}:{PORT}")
    print("  Streams: temp, gps, reefer, door (concurrent)")
    print(f"  Latency: {METRICS_DIR}/pathway_latency.csv (every 15s)")
    print("=" * 62 + "\n")

    pw.run()


if __name__ == "__main__":
    build_pathway_pipeline()
