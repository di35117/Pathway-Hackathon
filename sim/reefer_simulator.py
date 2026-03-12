"""
Reefer Unit Telemetry Simulator
Publishes compressor status, setpoint, power draw to MQTT.
Uses ProcessPoolExecutor for parallel simulation across all trucks.
"""

import time
import json
import random
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
import paho.mqtt.client as mqtt

from sim.config import BROKER, PORT, REEFER_TOPIC, SIMULATION_INTERVAL
from sim.shipment_factory import generate_shipments


def simulate_single_truck(shipment):
    """
    Runs the reefer simulation for a single truck in a separate process.
    Returns the computed event data AND updated shipment state.
    """
    shipment_id = shipment["shipment_id"]

    # Simulate compressor behavior
    compressor_on = shipment["compressor_on"]
    compressor_cycles = shipment["compressor_cycles"]

    # Occasionally toggle compressor (simulates cycling)
    if random.random() < 0.05:
        compressor_on = not compressor_on
        if compressor_on:
            compressor_cycles += 1

    power = shipment["power_draw_kw"] if compressor_on else 0.0
    # Add slight variation
    power = round(power + random.uniform(-0.2, 0.2), 2) if power > 0 else 0.0

    setpoint = (shipment["safe_min_temp"] + shipment["safe_max_temp"]) / 2

    event = {
        "ts": datetime.utcnow().isoformat(),
        "shipment_id": shipment_id,
        "compressor_status": "ON" if compressor_on else "OFF",
        "setpoint_c": round(setpoint, 1),
        "power_draw_kw": max(0, power),
        "compressor_cycles": compressor_cycles,
        "product_type": shipment["product_type"],
    }

    return {
        "event": event,
        "updated_state": {
            "compressor_on": compressor_on,
            "compressor_cycles": compressor_cycles,
        },
    }


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    shipments = generate_shipments()

    print(f"❄️  Reefer Simulator Started with {len(shipments)} shipments...")

    # Initialize reefer state per shipment
    for s in shipments:
        s["compressor_on"] = True
        s["compressor_cycles"] = random.randint(50, 200)
        s["power_draw_kw"] = round(random.uniform(1.5, 3.5), 2)

    with ProcessPoolExecutor() as executor:
        while True:
            # Distribute all 25 trucks across CPU cores
            results = list(executor.map(simulate_single_truck, shipments))

            # Main process: publish events and merge state back
            for i, result in enumerate(results):
                event = result["event"]

                # Merge updated state back into shipment
                shipments[i]["compressor_on"] = result["updated_state"]["compressor_on"]
                shipments[i]["compressor_cycles"] = result["updated_state"]["compressor_cycles"]

                # Publish via MQTT (single connection in main process)
                client.publish(REEFER_TOPIC, json.dumps(event))
                print("Published Reefer:", event)

            time.sleep(SIMULATION_INTERVAL)


if __name__ == "__main__":
    main()
