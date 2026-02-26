import json
import logging
import paho.mqtt.client as mqtt

from decision_engine.evaluator import evaluate_shipment, get_metrics_summary

# ── Logging setup (timestamps + level for free) ────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("livecold")
# ──────────────────────────────────────────────────────────────────────────────

import os
BROKER = os.getenv("MQTT_HOST", "localhost")
PORT   = 1883

TEMP_TOPIC = "livecold/temp"
GPS_TOPIC  = "livecold/gps"

# Exposure decay per tick when temp is back in range (gradual cool-down)
EXPOSURE_DECAY_PER_TICK = 0.5

shipment_state = {}
event_counter  = 0


def process_shipment(shipment_id):
    global event_counter

    state = shipment_state.get(shipment_id)
    if not state:
        return

    # Synchronization gate — only evaluate when we have both streams
    if state.get("temp") is None or state.get("lat") is None:
        return

    # Call intelligence layer
    final_output = evaluate_shipment(state)

    event_counter += 1

    # ── Pretty log for every event ────────────────────────────────────────────
    action = final_output["recommended_action"]
    risk   = final_output["risk_probability"]
    temp   = final_output["temp"]
    sid    = final_output["shipment_id"]

    if action == "DIVERT":
        # ── 🚨 Prominent DIVERT alert for demo ────────────────────────────────
        net_saving = (
            final_output["expected_loss_inr"] - final_output["diversion_cost_inr"]
        )
        log.warning(
            "🚨 DIVERT | %s | temp=%.1f°C | risk=%.0f%% | saving ₹%s | reason: %s",
            sid, temp, risk * 100,
            f"{net_saving:,.0f}",
            final_output["decision_reason"],
        )
        # Full structured output only for diverts (keeps demo terminal readable)
        print(json.dumps(final_output, indent=2))
    else:
        log.info(
            "✅ CONTINUE | %s | temp=%.1f°C | risk=%.0f%%",
            sid, temp, risk * 100,
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Print system metrics summary every 25 events
    if event_counter % 25 == 0:
        summary = get_metrics_summary()
        log.info(
            "\n╔═══════════════ SYSTEM METRICS (every 25 events) ═══════════════╗"
            "\n  Events processed : %d"
            "\n  Value monitored  : ₹%s"
            "\n  Expected losses  : ₹%s"
            "\n  Cargo saved      : ₹%s  ← 💰 value our system protected"
            "\n  Diversions       : %d (%.1f%%)"
            "\n  High-risk events : %d"
            "\n  CO₂ delta        : %.2f kg"
            "\n╚════════════════════════════════════════════════════════════════╝",
            summary["total_events_processed"],
            f"{summary['total_value_monitored_inr']:,.0f}",
            f"{summary['total_expected_loss_inr']:,.0f}",
            f"{summary['cargo_value_saved_inr']:,.0f}",
            summary["total_diversions"],
            summary["diversion_rate_percent"],
            summary["total_high_risk_events"],
            summary["total_co2_delta_kg"],
        )


def on_message(client, userdata, msg):
    topic = msg.topic
    data  = json.loads(msg.payload.decode())

    shipment_id = data.get("shipment_id")
    if not shipment_id:
        return

    # Initialise shipment state on first sight
    if shipment_id not in shipment_state:
        shipment_state[shipment_id] = {
            "shipment_id": shipment_id,
            "lat": None,
            "lon": None,
            "temp": None,

            # Product & Cargo
            "product_type":  data.get("product_type", "Generic"),
            "value_inr":     data.get("cargo_value_inr", 500000),
            "safe_min_temp": data.get("safe_min_temp", 2),
            "safe_max_temp": data.get("safe_max_temp", 8),

            # Operational
            "nearest_hub_distance_km": data.get("nearest_hub_distance_km", 30),
            "eta_minutes_remaining":   data.get("eta_minutes_remaining", 300),
            "objective_mode":          "cost",   # switch to "eco" for eco-mode demo

            # Intelligence tracking
            "exposure_minutes": 0,
            "last_temp": None,
        }

    # ── Update temperature ────────────────────────────────────────────────────
    if topic == TEMP_TOPIC:
        temp_value = data.get("temp_c")
        safe_min   = shipment_state[shipment_id]["safe_min_temp"]
        safe_max   = shipment_state[shipment_id]["safe_max_temp"]

        shipment_state[shipment_id]["temp"]      = temp_value
        shipment_state[shipment_id]["last_temp"] = temp_value

        # Exposure: increment when out of range, decay gradually when back in range
        if temp_value < safe_min or temp_value > safe_max:
            shipment_state[shipment_id]["exposure_minutes"] += 1
        else:
            # Gradual decay — don't instantly forget prior exposure
            current = shipment_state[shipment_id]["exposure_minutes"]
            shipment_state[shipment_id]["exposure_minutes"] = max(
                0.0, current - EXPOSURE_DECAY_PER_TICK
            )

    # ── Update GPS ────────────────────────────────────────────────────────────
    elif topic == GPS_TOPIC:
        shipment_state[shipment_id]["lat"] = data.get("lat")
        shipment_state[shipment_id]["lon"] = data.get("lon")

        if "eta_minutes_remaining" in data:
            shipment_state[shipment_id]["eta_minutes_remaining"] = data.get(
                "eta_minutes_remaining"
            )

    process_shipment(shipment_id)


def start_pipeline():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    client.subscribe(TEMP_TOPIC)
    client.subscribe(GPS_TOPIC)

    client.on_message = on_message

    log.info("🚀 LiveCold Pipeline Started — listening on %s:%d", BROKER, PORT)
    client.loop_forever()


if __name__ == "__main__":
    start_pipeline()