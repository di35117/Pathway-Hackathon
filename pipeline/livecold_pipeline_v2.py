"""
livecold_pipeline_v2.py — MQTT Pipeline using V2 Modules
Replaces decision_engine.evaluator with v2 stack (simulation_v2, risk_engine_v2, decision_engine_v2).

Receives telemetry via MQTT, runs through v2 pipeline, publishes decisions.
Entry point: python main.py mqtt-v2

No changes to Dockerfile or Docker Compose — just an alternative pipeline.
"""

import json
import logging
import paho.mqtt.client as mqtt
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from pipeline_v2 import run_pipeline_v2
from simulation_v2.telemetry_emitter import TruckSimulator, init_routes
from sim.shipment_factory import generate_shipments

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("livecold_v2")

import os
BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = 1883

TEMP_TOPIC = "livecold/temp"
GPS_TOPIC = "livecold/gps"
DECISION_TOPIC = "livecold/decision"

# Persistent simulator state per shipment
shipment_simulators = {}
shipment_state = {}
event_counter = 0

# Metrics tracking
_metrics = {
    "total_events": 0,
    "total_diversions": 0,
    "total_monitored": 0,
    "total_value_monitored_inr": 0,
    "total_expected_loss_inr": 0,
    "cargo_value_saved_inr": 0,
    "total_co2_delta_kg": 0.0,
    "total_high_risk_events": 0,
}


def get_metrics_summary():
    """Return current metrics summary."""
    return dict(_metrics)


def process_shipment_v2(shipment_id, client):
    """
    Process a shipment using V2 pipeline.
    
    Parameters
    ----------
    shipment_id : str
        Shipment ID to process.
    client : mqtt.Client
        MQTT client for publishing decisions.
    """
    global event_counter, _metrics

    state = shipment_state.get(shipment_id)
    if not state:
        return

    # Synchronization gate — only evaluate when we have both temp and position
    if state.get("temperature") is None or state.get("lat") is None:
        return

    # Get or create shipment object for V2 pipeline
    if shipment_id not in shipment_simulators:
        # Build a shipment dict from state
        shipment = {
            "shipment_id": shipment_id,
            "product_type": state.get("product_type", "Generic"),
            "cargo_value_inr": state.get("cargo_value_inr", 500000),
            "safe_min_temp": state.get("safe_min_temp", 2),
            "safe_max_temp": state.get("safe_max_temp", 8),
            "temp_mode": state.get("temp_mode", "stable"),
            "sensitivity": state.get("sensitivity", "MEDIUM"),
            "nearest_hub_distance_km": state.get("nearest_hub_distance_km", 30),
            "current_lat": state.get("lat", 0),
            "current_lon": state.get("lon", 0),
        }
        simulator = TruckSimulator(shipment)
        shipment_simulators[shipment_id] = (shipment, simulator)
    
    shipment, simulator = shipment_simulators[shipment_id]

    # Inject current telemetry into simulator (from MQTT state)
    # The simulator will use this for the next tick
    now = datetime.now(timezone.utc)

    # Run V2 pipeline: telemetry → risk → decision
    telemetry, risk, decision = run_pipeline_v2(
        shipment,
        simulator=simulator,
        sim_time=now,
        delta_t=2.0
    )

    event_counter += 1
    _metrics["total_events"] += 1
    _metrics["total_value_monitored_inr"] += risk.get("cargo_value_inr", 0)

    # Extract key fields
    action = decision.get("action", "CONTINUE")
    risk_prob = risk.get("risk_probability", 0)
    risk_level = risk.get("risk_level", "LOW")
    temp = telemetry.get("temperature", 0)

    # Update metrics
    if action == "DIVERT":
        _metrics["total_diversions"] += 1
    elif action == "MONITOR_CLOSELY":
        _metrics["total_monitored"] += 1

    if risk_level == "HIGH":
        _metrics["total_high_risk_events"] += 1

    expected_loss = decision.get("expected_loss_continue", 0)
    divert_cost = decision.get("total_diversion_cost", 0)
    saving = decision.get("saving", 0)
    co2_delta = decision.get("co2_delta_kg", 0)

    _metrics["total_expected_loss_inr"] += expected_loss
    _metrics["cargo_value_saved_inr"] += max(0, saving)
    _metrics["total_co2_delta_kg"] += co2_delta

    # ── Pretty log output ────────────────────────────────────────────────────
    if action == "DIVERT":
        log.warning(
            "🚨 DIVERT | %s | temp=%.1f°C | risk=%.0f%% | saving ₹%s | hub=%s",
            shipment_id,
            temp,
            risk_prob * 100,
            f"{saving:,.0f}",
            decision.get("selected_hub", "Unknown"),
        )
    elif action == "MONITOR_CLOSELY":
        log.info(
            "⚠️  MONITOR | %s | temp=%.1f°C | risk=%.0f%% | reason=%s",
            shipment_id,
            temp,
            risk_prob * 100,
            decision.get("divert_reason", "elevated risk"),
        )
    else:
        log.debug(
            "✅ CONTINUE | %s | temp=%.1f°C | risk=%.0f%%",
            shipment_id,
            temp,
            risk_prob * 100,
        )

    # Publish decision to MQTT
    decision_msg = {
        "shipment_id": shipment_id,
        "action": action,
        "risk_probability": risk_prob,
        "risk_level": risk_level,
        "temperature": temp,
        "timestamp": telemetry.get("timestamp", now.isoformat()),
        "selected_hub": decision.get("selected_hub"),
        "expected_loss_inr": round(expected_loss, 2),
        "diversion_cost_inr": round(divert_cost, 2),
        "saving_inr": round(saving, 2),
        "confidence": decision.get("confidence", 0),
    }
    client.publish(DECISION_TOPIC, json.dumps(decision_msg))

    # Print metrics summary every 25 events
    if event_counter % 25 == 0:
        summary = get_metrics_summary()
        log.info(
            "\n╔════════════════ SYSTEM METRICS (every 25 events) ════════════════╗"
            "\n  Events processed : %d"
            "\n  Value monitored  : ₹%s"
            "\n  Expected losses  : ₹%s"
            "\n  Cargo saved      : ₹%s"
            "\n  Diversions       : %d (%.1f%%)"
            "\n  Monitor closely  : %d"
            "\n  High-risk events : %d"
            "\n  CO₂ delta        : %.2f kg"
            "\n╚════════════════════════════════════════════════════════════════╝",
            summary["total_events"],
            f"{summary['total_value_monitored_inr']:,.0f}",
            f"{summary['total_expected_loss_inr']:,.0f}",
            f"{summary['cargo_value_saved_inr']:,.0f}",
            summary["total_diversions"],
            (summary["total_diversions"] / max(1, summary["total_events"])) * 100,
            summary["total_monitored"],
            summary["total_high_risk_events"],
            summary["total_co2_delta_kg"],
        )


def on_message(client, userdata, msg):
    """MQTT message callback — handle telemetry from simulators."""
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return

    shipment_id = data.get("shipment_id")
    if not shipment_id:
        return

    # Initialize shipment state on first message
    if shipment_id not in shipment_state:
        shipment_state[shipment_id] = {
            "shipment_id": shipment_id,
            "lat": None,
            "lon": None,
            "temperature": None,
            # Product & Cargo
            "product_type": data.get("product_type", "Generic"),
            "cargo_value_inr": data.get("cargo_value_inr", 500000),
            "safe_min_temp": data.get("safe_min_temp", 2),
            "safe_max_temp": data.get("safe_max_temp", 8),
            "sensitivity": data.get("sensitivity", "MEDIUM"),
            "temp_mode": data.get("temp_mode", "stable"),
            "nearest_hub_distance_km": data.get("nearest_hub_distance_km", 30),
            "eta_minutes_remaining": data.get("eta_minutes_remaining", 300),
        }

    # Update telemetry streams
    if topic == TEMP_TOPIC:
        shipment_state[shipment_id]["temperature"] = data.get("temperature")
        shipment_state[shipment_id]["compressor_status"] = data.get("compressor_status")

    elif topic == GPS_TOPIC:
        shipment_state[shipment_id]["lat"] = data.get("lat")
        shipment_state[shipment_id]["lon"] = data.get("lon")
        if "eta_minutes_remaining" in data:
            shipment_state[shipment_id]["eta_minutes_remaining"] = data.get("eta_minutes_remaining")

    # Process shipment through V2 pipeline
    process_shipment_v2(shipment_id, client)


def start_pipeline_v2():
    """Start V2 MQTT pipeline."""
    log.info("🚀 LiveCold V2 Pipeline Starting...")
    log.info("📦 Using: simulation_v2, risk_engine_v2, decision_engine_v2")

    # Pre-initialize shipments and routes for V2
    try:
        shipments = generate_shipments()
        init_routes(shipments)
        log.info(f"✓ Initialized {len(shipments)} shipments and cached routes")
    except Exception as e:
        log.warning(f"Route caching failed (non-critical): {e}")

    # MQTT setup
    client = mqtt.Client()
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT)
        client.subscribe(TEMP_TOPIC)
        client.subscribe(GPS_TOPIC)
        log.info(f"✓ Connected to MQTT broker at {BROKER}:{PORT}")
        log.info(f"✓ Subscribed to {TEMP_TOPIC} and {GPS_TOPIC}")

        log.info("="*60)
        log.info("🎯 V2 Pipeline Running — Waiting for sensor data...")
        log.info("="*60)

        client.loop_forever()

    except Exception as e:
        log.error(f"❌ Pipeline startup failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = start_pipeline_v2()
    exit(exit_code)
