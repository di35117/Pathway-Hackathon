import time
import json
import random
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
import paho.mqtt.client as mqtt

from sim.config import BROKER, PORT, TEMP_TOPIC, SIMULATION_INTERVAL
from sim.shipment_factory import generate_shipments


def simulate_single_truck(shipment):
    """
    Runs the temperature simulation for a single truck in a separate process.
    Returns the computed event data AND updated shipment state.
    """
    shipment_id = shipment["shipment_id"]
    mode        = shipment["temp_mode"]
    base_temp   = shipment["base_temp"]
    safe_min    = shipment["safe_min_temp"]
    safe_max    = shipment["safe_max_temp"]

    if mode == "stable":
        temp = base_temp + random.uniform(-0.5, 0.5)

    elif mode == "drift":
        drift_rate = 0.6 if shipment["sensitivity"] == "HIGH" else 0.3
        new_temp = base_temp + drift_rate

        # Cap drift before it goes absurd
        if new_temp > safe_max + 12:
            new_temp = safe_max - 1
            shipment["temp_mode"] = "stable"

        temp = new_temp
        shipment["base_temp"] = temp

    else:
        temp = base_temp

    # Inject anomalous readings for demo (~9% of readings)
    anomaly_type = None
    if random.random() < 0.03:
        temp = random.choice([999.0, -999.0, 500.0, -200.0])
        anomaly_type = "L1_GLITCH"
    elif random.random() < 0.04:
        temp = temp + random.choice([20, -20, 15, -15])
        anomaly_type = "L2_SPIKE"
    elif random.random() < 0.02:
        temp = temp + random.uniform(6, 10) * random.choice([1, -1])
        anomaly_type = "L3_OUTLIER"

    event = {
        "ts":                       datetime.utcnow().isoformat(),
        "shipment_id":              shipment_id,
        "sensor_id":                "PALLET_1",
        "temp_c":                   round(temp, 2),
        "product_type":             shipment["product_type"],
        "safe_min_temp":            safe_min,
        "safe_max_temp":            safe_max,
        "cargo_value_inr":          shipment["cargo_value_inr"],
        "nearest_hub_distance_km":  shipment["nearest_hub_distance_km"],
    }

    # Return both the event to publish AND updated shipment state
    return {
        "event": event,
        "anomaly_type": anomaly_type,
        "updated_state": {
            "base_temp": shipment["base_temp"],
            "temp_mode": shipment["temp_mode"],
        },
    }


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    shipments = generate_shipments()

    print(f"🌡  Temperature Simulator Started with {len(shipments)} shipments...")

    # Assign a fixed nearest-hub distance per shipment
    for shipment in shipments:
        shipment["nearest_hub_distance_km"] = random.randint(10, 80)

    with ProcessPoolExecutor() as executor:
        while True:
            # Distribute all 25 trucks across CPU cores
            results = list(executor.map(simulate_single_truck, shipments))

            # Main process: publish events and merge state back
            for i, result in enumerate(results):
                event = result["event"]
                anomaly_type = result["anomaly_type"]

                # Merge updated state back into shipment
                shipments[i]["base_temp"] = result["updated_state"]["base_temp"]
                shipments[i]["temp_mode"] = result["updated_state"]["temp_mode"]

                # Publish via MQTT (single connection in main process)
                client.publish(TEMP_TOPIC, json.dumps(event))
                print("Published Temp:", event)

                if anomaly_type:
                    print(f"⚡ [{event['shipment_id']}] Injected {anomaly_type}: {event['temp_c']}°C")

            time.sleep(SIMULATION_INTERVAL)


if __name__ == "__main__":
    main()