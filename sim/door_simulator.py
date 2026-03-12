"""
Door Open/Close & Shock Event Simulator
Publishes occasional door and shock events to MQTT.
Uses ProcessPoolExecutor for parallel simulation across all trucks.
"""

import time
import json
import random
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
import paho.mqtt.client as mqtt

from sim.config import BROKER, PORT, DOOR_TOPIC, SIMULATION_INTERVAL
from sim.shipment_factory import generate_shipments


def simulate_single_truck(shipment):
    """
    Runs the door/shock simulation for a single truck in a separate process.
    Returns the computed event data (or None if no event this tick).
    """
    # Door events are occasional (10% chance per tick)
    if random.random() < 0.10:
        event_type = random.choice(["door_open", "door_close", "shock"])

        event = {
            "ts": datetime.utcnow().isoformat(),
            "shipment_id": shipment["shipment_id"],
            "event_type": event_type,
            "product_type": shipment["product_type"],
        }

        if event_type == "door_open":
            event["duration_seconds"] = random.randint(5, 120)
        elif event_type == "shock":
            event["g_force"] = round(random.uniform(0.5, 5.0), 2)

        return {"event": event}

    return {"event": None}


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    shipments = generate_shipments()

    print(f"🚪 Door/Shock Simulator Started with {len(shipments)} shipments...")

    with ProcessPoolExecutor() as executor:
        while True:
            # Distribute all 25 trucks across CPU cores
            results = list(executor.map(simulate_single_truck, shipments))

            # Main process: publish events via MQTT
            for result in results:
                event = result["event"]
                if event:
                    client.publish(DOOR_TOPIC, json.dumps(event))
                    print(f"Published Door Event: {event}")

            time.sleep(SIMULATION_INTERVAL * 2)  # Less frequent than other sensors


if __name__ == "__main__":
    main()
