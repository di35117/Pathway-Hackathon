"""
LiveCold Pipeline — The Single Brain

Consumes all four IoT telemetry streams from MQTT, filters sensor faults, scores
risk, decides whether to divert, selects the hub, and publishes the result.

This is the ONLY place where risk calculation, diversion decisions and hub
selection happen. The dashboard subscribes to our output and renders it.

    livecold/temp    ──┐
    livecold/gps     ──┤
    livecold/reefer  ──┼──▶ anomaly filter ──▶ risk engine ──▶ decision engine
    livecold/door    ──┘                                            │
                                                                    ▼
                                                        livecold/decisions
                                                        livecold/notifications

Engines
-------
v2 (default) — risk_engine_v2 + decision_engine_v2. Fuses six signals from all
               four streams with per-cargo weights, tracks irreversible
               degree-hours, forecasts 30 minutes ahead, and emits
               CONTINUE / MONITOR_CLOSELY / DIVERT with a confidence level.
v1           — decision_engine. Temperature and GPS only, two actions. Retained
               as a fallback and for A/B comparison: `python main.py mqtt --engine v1`.
"""

import argparse
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, UTC

import paho.mqtt.client as mqtt

from core.anomaly_detector import detector as anomaly_detector
from core.alert_notifier import notifier as alert_notifier
from core.hub_manager import find_nearest_hubs
from core.sop_parser import get_product_profile

# V2 engine (default)
from risk_engine_v2.risk_calculator_v2 import (
    assess_risk_v2,
    linear_forecast,
    compute_exposure_increment,
    compute_spoilage_probability,
    reset_tracking as reset_risk_tracking,
)
from risk_engine_v2.cargo_profiles import (
    get_default_routing_mode,
    get_degree_hour_midpoint,
)
from decision_engine_v2.decision_logic_v2 import (
    decide_v2,
    reset_tracking as reset_decision_tracking,
)

# V1 engine (fallback)
from decision_engine.evaluator import evaluate_shipment, get_metrics_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))

TEMP_TOPIC = "livecold/temp"
GPS_TOPIC = "livecold/gps"
REEFER_TOPIC = "livecold/reefer"
DOOR_TOPIC = "livecold/door"
DECISION_TOPIC = "livecold/decisions"
DIVERT_TOPIC = "livecold/divert"
NOTIFICATION_TOPIC = "livecold/notifications"
ROUTING_MODE_TOPIC = "livecold/routing-mode"
LATENCY_TOPIC = "livecold/latency"
ANOMALY_TOPIC = "livecold/anomalies"

SENSOR_TOPICS = (TEMP_TOPIC, GPS_TOPIC, REEFER_TOPIC, DOOR_TOPIC)

# Forecast horizon for predictive spoilage, in minutes.
FORECAST_HORIZON_MIN = 30
# Guards against extrapolating a 30-minute projection from a few seconds of data.
MIN_FORECAST_SAMPLES = 10
MIN_FORECAST_WINDOW_SEC = 60.0
# Fastest sustained rise a reefer body can physically show (doors wide open).
MAX_FORECAST_RATE_C_MIN = 0.8

# Nominal sensor publish interval; used when a shipment has no prior reading.
DEFAULT_TICK_SECONDS = 2.0

ENGINE = "v2"

shipment_state = {}
already_diverted = set()
event_counter = 0
pipeline_client = None

# Rolling temperature history per shipment, for the 30-minute forecast.
_temp_history = defaultdict(lambda: deque(maxlen=90))

# End-to-end latency samples (sensor publish -> decision publish), milliseconds.
_latency_samples = deque(maxlen=1000)

_metrics = {
    "total_events": 0,
    "total_diversions": 0,
    "total_monitor_closely": 0,
    "total_high_risk_events": 0,
    "cargo_value_saved_inr": 0.0,
    "total_co2_delta_kg": 0.0,
}
# Savings are counted once per shipment, not once per tick.
_saved_per_shipment = {}


# ══════════════════════════════════════════════════════════════════
#  Telemetry assembly — all four streams into one V2 event
# ══════════════════════════════════════════════════════════════════

def _build_telemetry(state):
    """
    Assemble a V2 telemetry event from the four MQTT streams.

    risk_engine_v2 expects one dict carrying temperature, position, door state
    and compressor state. Each stream writes its own slice of shipment_state;
    this joins them at decision time.
    """
    return {
        "shipment_id": state["shipment_id"],
        "timestamp": datetime.now(UTC).isoformat(),
        "temperature": state["temp"],
        "product_type": state.get("product_type", "dairy"),
        "safe_min_temp": state.get("safe_min_temp", 2),
        "safe_max_temp": state.get("safe_max_temp", 8),
        "cargo_value_inr": state.get("value_inr", 0),
        "eta_minutes_remaining": state.get("eta_minutes_remaining", 300),
        # From livecold/door
        "door_status": state.get("door_status", "CLOSED"),
        "door_open_sec": state.get("door_open_sec", 0),
        # From livecold/reefer
        "compressor": {
            "status": state.get("compressor_status", "RUNNING"),
            "load_pct": state.get("compressor_load_pct"),
        },
        "gps": {"lat": state.get("lat"), "lng": state.get("lon")},
        "speed_kmh": state.get("speed_kmph", 0),
    }


def _forecast(shipment_id, telemetry, risk):
    """
    Project temperature FORECAST_HORIZON_MIN ahead by least-squares regression
    over the recent history, then re-evaluate spoilage probability at that point.

    This is what makes the system predictive rather than reactive: it answers
    "where will this cargo be in 30 minutes", which is the window in which a
    diversion can still be acted on.

    Two guards keep the extrapolation honest. Readings arrive every 2 seconds, so
    a naive 30-minute projection multiplies the fitted slope by 900 - fitting a
    line to a few seconds of noise and extrapolating half an hour produces
    physically absurd numbers. So we require a minimum observation window before
    forecasting at all, and clamp the projected rate to what a reefer can
    physically do.
    """
    history = list(_temp_history[shipment_id])
    current = float(telemetry["temperature"])

    unknown = {
        "horizon_minutes": FORECAST_HORIZON_MIN,
        "predicted_temp": None,
        "predicted_spoilage_probability": risk.get("spoilage_probability"),
        "trend": "unknown",
        "reason": "insufficient history",
    }

    if len(history) < MIN_FORECAST_SAMPLES:
        return unknown

    window_sec = (history[-1][0] - history[0][0]).total_seconds()
    if window_sec < MIN_FORECAST_WINDOW_SEC:
        return unknown

    predicted_temp = linear_forecast(history, horizon_minutes=FORECAST_HORIZON_MIN)
    if predicted_temp is None:
        return unknown

    # Clamp to a physically achievable excursion. A reefer body with the doors
    # open rises at roughly 0.5 C/min; anything beyond MAX_FORECAST_RATE_C_MIN
    # is regression noise amplified by the horizon, not a real prediction.
    max_delta = MAX_FORECAST_RATE_C_MIN * FORECAST_HORIZON_MIN
    predicted_temp = max(current - max_delta, min(current + max_delta, predicted_temp))

    safe_max = float(telemetry.get("safe_max_temp", 8))
    cargo = telemetry.get("product_type", "dairy")

    increment = compute_exposure_increment(
        predicted_temp, safe_max, FORECAST_HORIZON_MIN / 60.0
    )
    projected_degree_hours = float(risk.get("exposure_degree_hours", 0.0)) + increment
    projected_spoilage = compute_spoilage_probability(
        projected_degree_hours, b=get_degree_hour_midpoint(cargo)
    )

    delta = predicted_temp - current
    trend = "rising" if delta > 0.5 else "falling" if delta < -0.5 else "stable"

    return {
        "horizon_minutes": FORECAST_HORIZON_MIN,
        "predicted_temp": round(predicted_temp, 2),
        "predicted_exposure_degree_hours": round(projected_degree_hours, 4),
        "predicted_spoilage_probability": round(projected_spoilage, 4),
        "trend": trend,
        "will_breach": bool(predicted_temp > safe_max and current <= safe_max),
        "window_sec": round(window_sec, 1),
    }


def _select_hub(state, action):
    """
    Choose the destination hub. The pipeline owns this decision so that the
    driver's notification and the dashboard's proposal can never disagree —
    previously both processes selected independently and could pick different
    hubs for the same event.
    """
    if action != "DIVERT" or state.get("lat") is None or state.get("lon") is None:
        return None

    cargo = state.get("product_type", "dairy").lower().replace(" ", "_")
    hubs = find_nearest_hubs(state["lat"], state["lon"], cargo_type=cargo, top_n=1)
    return hubs[0] if hubs else None


# ══════════════════════════════════════════════════════════════════
#  Decision cycle
# ══════════════════════════════════════════════════════════════════

def process_shipment(shipment_id):
    """Run the decision engine for one shipment and publish the result."""
    global event_counter

    state = shipment_state.get(shipment_id)
    if not state:
        return

    # Synchronisation gate: a decision needs a temperature to assess risk and a
    # position to choose a hub. Both streams are independent, so we wait.
    if state.get("temp") is None or state.get("lat") is None:
        return

    decision_start = time.time()

    if ENGINE == "v2":
        final_output = _run_v2(state)
    else:
        final_output = _run_v1(state)

    event_counter += 1
    _metrics["total_events"] += 1

    # ── Diversion dedup, re-arming, and one-shot metric booking ───
    # A truck above threshold produces a DIVERT verdict on every sensor message.
    # Only the first is a real diversion; the rest are the same incident still in
    # progress. Counting each tick is what previously inflated the headline
    # "cargo saved" figure past the total value on the road.
    action = final_output["recommended_action"]
    if action == "DIVERT":
        if shipment_id in already_diverted:
            final_output["recommended_action"] = "MONITORING"
            action = "MONITORING"
        else:
            already_diverted.add(shipment_id)
            _metrics["total_diversions"] += 1
            if shipment_id not in _saved_per_shipment:
                saving = max(0.0, final_output.get("net_saving_inr", 0.0)
                             or final_output.get("expected_loss_inr", 0.0)
                             - final_output.get("diversion_cost_inr", 0.0))
                _saved_per_shipment[shipment_id] = saving
                _metrics["cargo_value_saved_inr"] += saving
                _metrics["total_co2_delta_kg"] += final_output.get("co2_delta_kg", 0.0)
    elif action == "CONTINUE" and shipment_id in already_diverted:
        already_diverted.discard(shipment_id)

    # ── Hub selection (pipeline-owned, single source) ─────────────
    hub = _select_hub(state, action)
    if hub:
        final_output["selected_hub"] = {
            "id": hub["id"],
            "name": hub["name"],
            "lat": hub["lat"],
            "lon": hub["lon"],
            "distance_km": hub["distance_km"],
            "eta_minutes": hub["eta_minutes"],
            "traffic_level": hub["traffic_level"],
            "contact": hub.get("contact", ""),
            "diversion_cost_inr": hub["diversion_cost_inr"],
            "co2_extra_kg": hub["co2_extra_kg"],
        }

    # ── Enrichment shared by both engines ─────────────────────────
    final_output.update({
        "routing_mode": state.get("routing_mode", "BALANCED"),
        "product_type": state.get("product_type", ""),
        "safe_min_temp": state.get("safe_min_temp", 2),
        "safe_max_temp": state.get("safe_max_temp", 8),
        "cargo_value_inr": state.get("value_inr", 0),
        "origin": state.get("origin", ""),
        "destination": state.get("destination", ""),
        "speed_kmph": state.get("speed_kmph", 0),
        "engine": ENGINE,
        "door_status": state.get("door_status", "CLOSED"),
        "compressor_status": state.get("compressor_status", "RUNNING"),
    })

    stats = anomaly_detector.get_stats()
    final_output["global_anomalies"] = stats["total_anomalies"]
    final_output["global_anomaly_breakdown"] = {
        "l1": stats["l1_bounds"],
        "l2": stats["l2_rate"],
        "l3": stats["l3_zscore"],
        "l4": stats["l4_stuck"],
    }

    # ── End-to-end latency: sensor publish -> decision published ──
    sensor_ts = state.get("last_sensor_epoch")
    if sensor_ts:
        latency_ms = (time.time() - sensor_ts) * 1000.0
        _latency_samples.append(latency_ms)
        final_output["pipeline_latency_ms"] = round(latency_ms, 2)
    final_output["decision_compute_ms"] = round((time.time() - decision_start) * 1000.0, 2)

    if pipeline_client:
        pipeline_client.publish(DECISION_TOPIC, json.dumps(final_output))

    _log_and_notify(final_output, state, hub)
    _publish_latency_summary()


def _run_v2(state):
    """Six-factor risk + economic decision with confidence and forecast."""
    sid = state["shipment_id"]

    now = time.time()
    last = state.get("last_decision_epoch")
    delta_t = max(0.1, min(now - last, 300.0)) if last else DEFAULT_TICK_SECONDS
    state["last_decision_epoch"] = now

    telemetry = _build_telemetry(state)
    risk = assess_risk_v2(telemetry, delta_t_seconds=delta_t)

    _temp_history[sid].append(
        (datetime.fromisoformat(telemetry["timestamp"]), float(telemetry["temperature"]))
    )
    forecast = _forecast(sid, telemetry, risk)

    shipment = {
        "shipment_id": sid,
        "product_type": state.get("product_type", "dairy"),
        "cargo_value_inr": state.get("value_inr", 0),
        "nearest_hub_distance_km": state.get("nearest_hub_distance_km", 30),
        "routing_mode": state.get("routing_mode"),
        "lat": state.get("lat"),
        "lon": state.get("lon"),
    }

    decision = decide_v2(
        risk, shipment,
        delta_t=delta_t,
        data_staleness_sec=now - state.get("last_sensor_epoch", now),
    )

    state["exposure_minutes"] = risk["exposure_minutes"]

    if risk["risk_level"] == "HIGH":
        _metrics["total_high_risk_events"] += 1
    elif decision["action"] == "MONITOR_CLOSELY":
        _metrics["total_monitor_closely"] += 1

    return {
        "shipment_id": sid,
        "lat": state.get("lat"),
        "lon": state.get("lon"),
        "temp": state.get("temp"),
        "risk_probability": risk["risk_probability"],
        "risk_level": risk["risk_level"],
        "recommended_action": decision["action"],
        "confidence": decision["confidence"],
        "confidence_reason": decision["confidence_reason"],
        "expected_loss_inr": decision["expected_loss_continue"],
        "diversion_cost_inr": decision["total_diversion_cost"],
        "net_saving_inr": decision["saving"],
        "co2_delta_kg": decision["co2_delta_kg"],
        "decision_reason": decision["divert_reason"],
        "mode_rule": decision["mode_rule"],
        "factor_scores": risk["factor_scores"],
        "exposure_minutes": risk["exposure_minutes"],
        "exposure_degree_hours": risk["exposure_degree_hours"],
        "spoilage_probability": risk["spoilage_probability"],
        "drift_rate_c_min": risk["drift_rate_c_min"],
        "forecast": forecast,
        "timestamp": datetime.now().isoformat(),
    }


def _run_v1(state):
    """Fallback engine: temperature + GPS only, two actions."""
    out = evaluate_shipment(state)
    out["risk_level"] = (
        "HIGH" if out["risk_probability"] >= 0.65
        else "MEDIUM" if out["risk_probability"] >= 0.35
        else "LOW"
    )
    out["confidence"] = "MEDIUM"
    out["confidence_reason"] = "V1 engine does not score confidence"
    out["exposure_minutes"] = state.get("exposure_minutes", 0)
    if out["recommended_action"] == "DIVERT":
        _metrics["total_diversions"] += 1
        sid = state["shipment_id"]
        if sid not in _saved_per_shipment:
            saving = max(0.0, out["expected_loss_inr"] - out["diversion_cost_inr"])
            _saved_per_shipment[sid] = saving
            _metrics["cargo_value_saved_inr"] += saving
            _metrics["total_co2_delta_kg"] += out["co2_delta_kg"]
    return out


def _log_and_notify(output, state, hub):
    """Terminal logging, driver notification, and the periodic metrics banner."""
    action = output["recommended_action"]
    sid = output["shipment_id"]
    risk = output["risk_probability"]
    temp = output["temp"]

    if action == "DIVERT":
        log.warning(
            "DIVERT | %s | %s | temp=%.1fC | risk=%.0f%% | conf=%s | save Rs %s | %s",
            sid, output.get("product_type", ""), temp, risk * 100,
            output.get("confidence", "?"),
            f"{output.get('net_saving_inr', 0):,.0f}",
            output.get("decision_reason", ""),
        )
        if hub:
            notification = alert_notifier.send_divert_alert(
                shipment_id=sid,
                hub_info=hub,
                product_type=state.get("product_type", "Unknown"),
                current_temp=temp,
                safe_range=(state.get("safe_min_temp", 2), state.get("safe_max_temp", 8)),
                risk_probability=risk,
            )
            if pipeline_client and notification:
                pipeline_client.publish(NOTIFICATION_TOPIC, json.dumps(notification))

    elif action == "MONITOR_CLOSELY":
        log.info("MONITOR | %s | temp=%.1fC | risk=%.0f%% | %s",
                 sid, temp, risk * 100, output.get("decision_reason", ""))
    else:
        log.debug("%s | %s | temp=%.1fC | risk=%.0f%%", action, sid, temp, risk * 100)

    if event_counter % 50 == 0:
        p50, p95 = _latency_percentiles()
        log.info(
            "\n  PIPELINE METRICS (every 50 events)"
            "\n    events=%d  anomalies filtered=%d"
            "\n    diversions=%d  monitor=%d  high-risk=%d"
            "\n    cargo saved=Rs %s   CO2 delta=%.1f kg"
            "\n    latency p50=%.1f ms  p95=%.1f ms  (sensor -> decision)",
            _metrics["total_events"],
            anomaly_detector.get_stats()["total_anomalies"],
            _metrics["total_diversions"],
            _metrics["total_monitor_closely"],
            _metrics["total_high_risk_events"],
            f"{_metrics['cargo_value_saved_inr']:,.0f}",
            _metrics["total_co2_delta_kg"],
            p50, p95,
        )


def _latency_percentiles():
    if not _latency_samples:
        return 0.0, 0.0
    ordered = sorted(_latency_samples)
    n = len(ordered)
    return ordered[n // 2], ordered[min(n - 1, int(n * 0.95))]


def _publish_latency_summary():
    """Publish rolling latency stats so the dashboard can display them."""
    if not pipeline_client or event_counter % 25 != 0 or not _latency_samples:
        return
    p50, p95 = _latency_percentiles()
    pipeline_client.publish(LATENCY_TOPIC, json.dumps({
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(_latency_samples), 2),
        "samples": len(_latency_samples),
        "sub_second_pct": round(
            100.0 * sum(1 for x in _latency_samples if x < 1000) / len(_latency_samples), 2
        ),
        "engine": ENGINE,
    }))


def get_metrics():
    """Snapshot of pipeline metrics (used by tests and the metrics banner)."""
    p50, p95 = _latency_percentiles()
    summary = dict(_metrics)
    summary["latency_p50_ms"] = round(p50, 2)
    summary["latency_p95_ms"] = round(p95, 2)
    if ENGINE == "v1":
        summary["v1_engine"] = get_metrics_summary()
    return summary


# ══════════════════════════════════════════════════════════════════
#  MQTT ingest — four streams
# ══════════════════════════════════════════════════════════════════

def _init_state(shipment_id, data):
    """Create per-shipment state, seeding safe ranges from the SOP."""
    product = data.get("product_type", "Dairy")
    profile = get_product_profile(product)

    return {
        "shipment_id": shipment_id,
        "lat": None,
        "lon": None,
        "temp": None,
        "product_type": product,
        "value_inr": data.get("cargo_value_inr", 500000),
        # SOP is the source of truth; the sensor payload only overrides it if
        # it actually carries a range.
        "safe_min_temp": data.get("safe_min_temp", profile["safe_min"]),
        "safe_max_temp": data.get("safe_max_temp", profile["safe_max"]),
        "nearest_hub_distance_km": data.get("nearest_hub_distance_km", 30),
        "eta_minutes_remaining": data.get("eta_minutes_remaining", 300),
        "routing_mode": get_default_routing_mode(product),
        "exposure_minutes": 0.0,
        "origin": data.get("origin", ""),
        "destination": data.get("destination", ""),
        "speed_kmph": 0,
        "door_status": "CLOSED",
        "door_open_sec": 0,
        "compressor_status": "RUNNING",
        "compressor_load_pct": None,
        "last_sensor_epoch": None,
        "last_decision_epoch": None,
    }


def _handle_temp(state, data):
    """Anomaly-filter a temperature reading, then commit it."""
    shipment_id = state["shipment_id"]
    raw_temp = data.get("temp_c")
    if raw_temp is None:
        return False

    product = data.get("product_type", state["product_type"])
    if product != state["product_type"]:
        # The first message for a shipment is often GPS, which carries no cargo
        # type. Once temperature tells us what is actually on the truck, adopt
        # the SOP range and the cargo's default routing mode - unless an
        # operator has already overridden the mode by hand.
        state["product_type"] = product
        profile = get_product_profile(product)
        state["safe_min_temp"] = profile["safe_min"]
        state["safe_max_temp"] = profile["safe_max"]
        if not state.get("routing_mode_overridden"):
            state["routing_mode"] = get_default_routing_mode(product)

    anomaly = anomaly_detector.check(shipment_id, raw_temp, product)
    if anomaly.is_anomaly:
        log.warning("ANOMALY [%s] %s - %s", shipment_id, anomaly.layer, anomaly.reason)
        state["last_anomaly"] = {
            "layer": anomaly.layer,
            "reason": anomaly.reason,
            "at": datetime.now().isoformat(),
        }
        # Publish so the dashboard can persist it. Every filtered reading must be
        # auditable: if a spoilage claim arrives you replay the shipment's
        # filtered stream and check whether a real warning was suppressed.
        if pipeline_client:
            pipeline_client.publish(ANOMALY_TOPIC, json.dumps({
                "shipment_id": shipment_id,
                "layer": anomaly.layer,
                "reason": anomaly.reason,
                "raw_temp": anomaly.original_temp,
                "corrected_temp": anomaly.corrected_temp,
                "product_type": product,
                "ts": datetime.now(UTC).isoformat(),
            }))

        if alert_notifier.record_anomaly(shipment_id) and state.get("lat") is not None:
            cargo = product.lower().replace(" ", "_")
            repair = find_nearest_hubs(
                state["lat"], state["lon"],
                cargo_type=cargo, top_n=1, repair_only=True,
            )
            if repair:
                counts = alert_notifier.get_anomaly_counts()
                notification = alert_notifier.send_repair_alert(
                    shipment_id=shipment_id,
                    anomaly_count=counts.get(shipment_id, 3),
                    repair_hub_info=repair[0],
                    product_type=product,
                )
                if pipeline_client and notification:
                    pipeline_client.publish(NOTIFICATION_TOPIC, json.dumps(notification))

        # L4 flags a sensor needing maintenance but the value may still be
        # correct, so it is accepted. The other layers substitute or discard.
        if anomaly.layer != "L4_STUCK":
            if anomaly.corrected_temp is None:
                return False
            raw_temp = anomaly.corrected_temp

    state["temp"] = raw_temp
    state["value_inr"] = data.get("cargo_value_inr", state["value_inr"])
    if "nearest_hub_distance_km" in data:
        state["nearest_hub_distance_km"] = data["nearest_hub_distance_km"]
    return True


def on_message(client, userdata, msg):
    topic = msg.topic

    try:
        data = json.loads(msg.payload.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    # Never react to our own output.
    if topic in (DECISION_TOPIC, DIVERT_TOPIC, NOTIFICATION_TOPIC,
                 LATENCY_TOPIC, ANOMALY_TOPIC):
        return

    if topic == ROUTING_MODE_TOPIC:
        sid = data.get("shipment_id")
        new_mode = str(data.get("mode", "")).upper()
        if sid in shipment_state and new_mode in ("SAFETY", "BALANCED", "ECO"):
            old = shipment_state[sid].get("routing_mode")
            shipment_state[sid]["routing_mode"] = new_mode
            # Sticky: cargo-type defaults must not silently revert an operator.
            shipment_state[sid]["routing_mode_overridden"] = True
            log.info("[%s] routing mode %s -> %s (operator override)", sid, old, new_mode)
        return

    if topic not in SENSOR_TOPICS:
        return

    shipment_id = data.get("shipment_id")
    if not shipment_id:
        return

    if shipment_id not in shipment_state:
        shipment_state[shipment_id] = _init_state(shipment_id, data)

    state = shipment_state[shipment_id]
    state["last_sensor_epoch"] = time.time()

    if topic == TEMP_TOPIC:
        if not _handle_temp(state, data):
            return  # reading discarded, no decision on garbage

    elif topic == GPS_TOPIC:
        state["lat"] = data.get("lat", state["lat"])
        state["lon"] = data.get("lon", state["lon"])
        state["speed_kmph"] = data.get("speed_kmph", state["speed_kmph"])
        state["origin"] = data.get("origin", state["origin"])
        state["destination"] = data.get("destination", state["destination"])
        if "eta_minutes_remaining" in data:
            state["eta_minutes_remaining"] = data["eta_minutes_remaining"]

    elif topic == REEFER_TOPIC:
        # Reefer telemetry feeds the compressor risk factor.
        status = data.get("compressor_status", "ON")
        state["compressor_status"] = "RUNNING" if status == "ON" else "OFF"
        power = data.get("power_draw_kw")
        if power is not None:
            # Map power draw onto a 0-100 load percentage; 3.5 kW is full load.
            state["compressor_load_pct"] = max(0, min(100, round(power / 3.5 * 100)))

    elif topic == DOOR_TOPIC:
        # Door events feed the door risk factor.
        event_type = data.get("event_type", "")
        if event_type == "door_open":
            state["door_status"] = "OPEN"
            state["door_open_sec"] = data.get("duration_seconds", 0)
        elif event_type == "door_close":
            state["door_status"] = "CLOSED"
            state["door_open_sec"] = 0
        elif event_type == "shock":
            state["last_shock_g"] = data.get("g_force", 0)

    process_shipment(shipment_id)


def reset_pipeline_state():
    """
    Clear every piece of state the pipeline touches. Used by tests.

    This must include the shared singletons — the anomaly detector and the alert
    notifier are module-level objects, so without resetting them one test's
    rolling temperature window and diversion-cooldown timers leak into the next.
    """
    global event_counter
    shipment_state.clear()
    already_diverted.clear()
    _temp_history.clear()
    _latency_samples.clear()
    _saved_per_shipment.clear()
    event_counter = 0
    for key in _metrics:
        _metrics[key] = 0 if isinstance(_metrics[key], int) else 0.0
    reset_risk_tracking()
    reset_decision_tracking()
    anomaly_detector.reset()
    alert_notifier.reset()


def start_pipeline(engine="v2"):
    global pipeline_client, ENGINE
    ENGINE = engine

    pipeline_client = mqtt.Client(client_id=f"livecold-pipeline-{engine}")
    pipeline_client.connect(BROKER, PORT)

    for topic in SENSOR_TOPICS:
        pipeline_client.subscribe(topic)
    pipeline_client.subscribe(ROUTING_MODE_TOPIC)
    pipeline_client.on_message = on_message

    log.info("LiveCold Pipeline started (engine=%s)", engine)
    log.info("  subscribing: %s", ", ".join(SENSOR_TOPICS))
    log.info("  publishing:  %s, %s, %s",
             DECISION_TOPIC, NOTIFICATION_TOPIC, LATENCY_TOPIC)
    log.info("  anomaly detection: 4 layers")
    if engine == "v2":
        log.info("  risk: 6-factor cargo-weighted + %d-min forecast", FORECAST_HORIZON_MIN)
        log.info("  decision: SAFETY / BALANCED / ECO with confidence scoring")
    else:
        log.info("  risk: V1 single-factor (fallback engine)")

    pipeline_client.loop_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LiveCold intelligence pipeline")
    parser.add_argument("--engine", choices=["v1", "v2"], default="v2",
                        help="decision engine to run (default: v2)")
    args = parser.parse_args()
    start_pipeline(engine=args.engine)
