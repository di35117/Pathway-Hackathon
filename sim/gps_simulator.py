# sim/gps_simulator.py

import time
import json
import threading
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
import paho.mqtt.client as mqtt

from sim.config import BROKER, PORT, GPS_TOPIC, DIVERT_TOPIC, SIMULATION_INTERVAL
from sim.shipment_factory import generate_shipments


def move_towards(current, target, step):
    if abs(target - current) < step:
        return target
    return current + step if target > current else current - step


# Track active diversions: shipment_id -> {hub_lat, hub_lon, hub_name}
active_diversions = {}
diversion_lock = threading.Lock()


def on_divert_message(client, userdata, msg):
    """Handle diversion orders from the dashboard."""
    try:
        data = json.loads(msg.payload)
        sid = data.get("shipment_id")
        if sid and data.get("hub_lat") and data.get("hub_lon"):
            with diversion_lock:
                active_diversions[sid] = {
                    "hub_lat": data["hub_lat"],
                    "hub_lon": data["hub_lon"],
                    "hub_name": data.get("hub_name", "Unknown Hub"),
                }
            print(f"🔀 DIVERTING {sid} → {data.get('hub_name', 'Hub')} "
                  f"({data['hub_lat']:.2f}, {data['hub_lon']:.2f})")
    except Exception as e:
        print(f"⚠️ Divert parse error: {e}")


def simulate_single_truck(args):
    """
    Runs the GPS simulation for a single truck in a separate process.
    Receives (shipment_dict, diversion_info_or_None).
    Returns the computed event data AND updated shipment state.
    """
    shipment, diversion = args
    sid = shipment["shipment_id"]

    arrived = False

    if diversion:
        # Move toward the hub instead of the original destination
        target_lat = diversion["hub_lat"]
        target_lon = diversion["hub_lon"]
        dest_name = diversion["hub_name"]

        # Check if arrived at hub (within ~1km)
        dist = ((shipment["current_lat"] - target_lat)**2 +
                (shipment["current_lon"] - target_lon)**2) ** 0.5
        if dist < 0.01:  # ~1km
            arrived = True
            return {
                "event": None,
                "arrived": True,
                "sid": sid,
                "dest_name": dest_name,
                "updated_state": {
                    "current_lat": shipment["current_lat"],
                    "current_lon": shipment["current_lon"],
                    "eta_minutes_remaining": 30,
                },
            }
    else:
        # Normal: move toward original destination
        target_lat = shipment["end_lat"]
        target_lon = shipment["end_lon"]
        dest_name = shipment["destination"]

    # Movement step based on speed
    step_size = shipment["speed_kmph"] / 10000

    new_lat = move_towards(shipment["current_lat"], target_lat, step_size)
    new_lon = move_towards(shipment["current_lon"], target_lon, step_size)

    # Decrease ETA
    new_eta = max(0, shipment["eta_minutes_remaining"] - (SIMULATION_INTERVAL / 60))

    event = {
        "ts": datetime.utcnow().isoformat(),
        "shipment_id": sid,
        "lat": round(new_lat, 6),
        "lon": round(new_lon, 6),
        "speed_kmph": shipment["speed_kmph"],
        "origin": shipment["origin"],
        "destination": dest_name,
        "eta_minutes_remaining": round(new_eta, 1),
        "product_type": shipment["product_type"],
        "diverted": diversion is not None,
    }

    return {
        "event": event,
        "arrived": False,
        "sid": sid,
        "dest_name": dest_name,
        "updated_state": {
            "current_lat": new_lat,
            "current_lon": new_lon,
            "eta_minutes_remaining": new_eta,
        },
    }


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    # Subscribe to diversion orders (runs in main process thread)
    client.subscribe(DIVERT_TOPIC)
    client.message_callback_add(DIVERT_TOPIC, on_divert_message)
    client.loop_start()

    shipments = generate_shipments()

    print(f"🚚 GPS Simulator Started with {len(shipments)} shipments...")
    print(f"📡 Listening for diversions on {DIVERT_TOPIC}")

    with ProcessPoolExecutor() as executor:
        while True:
            # Prepare args: pair each shipment with its diversion info (if any)
            with diversion_lock:
                args_list = [
                    (s, active_diversions.get(s["shipment_id"]))
                    for s in shipments
                ]

            # Distribute all 25 trucks across CPU cores
            results = list(executor.map(simulate_single_truck, args_list))

            # Main process: publish events and merge state back
            for i, result in enumerate(results):
                sid = result["sid"]

                if result["arrived"]:
                    print(f"✅ {sid} ARRIVED at {result['dest_name']}")
                    with diversion_lock:
                        active_diversions.pop(sid, None)

                # Merge updated state back into shipment
                shipments[i]["current_lat"] = result["updated_state"]["current_lat"]
                shipments[i]["current_lon"] = result["updated_state"]["current_lon"]
                shipments[i]["eta_minutes_remaining"] = result["updated_state"]["eta_minutes_remaining"]

                # Publish via MQTT (single connection in main process)
                if result["event"]:
                    client.publish(GPS_TOPIC, json.dumps(result["event"]))
                    print("Published GPS:", result["event"])

            time.sleep(SIMULATION_INTERVAL)


if __name__ == "__main__":
    main()
