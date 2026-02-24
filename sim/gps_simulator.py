# sim/gps_simulator.py

import time
import json
from datetime import datetime
import paho.mqtt.client as mqtt

from sim.config import BROKER, PORT, GPS_TOPIC, SIMULATION_INTERVAL
from sim.shipment_factory import generate_shipments


def move_towards(current, target, step):
    if abs(target - current) < step:
        return target
    return current + step if target > current else current - step


def main():
    client = mqtt.Client()
    client.connect(BROKER, PORT)

    shipments = generate_shipments()

    print(f"🚚 GPS Simulator Started with {len(shipments)} shipments...")

    while True:
        for shipment in shipments:

            # movement step based on speed
            step_size = shipment["speed_kmph"] / 10000

            shipment["current_lat"] = move_towards(
                shipment["current_lat"],
                shipment["end_lat"],
                step_size
            )

            shipment["current_lon"] = move_towards(
                shipment["current_lon"],
                shipment["end_lon"],
                step_size
            )

            # decrease ETA
            shipment["eta_minutes_remaining"] = max(
                0,
                shipment["eta_minutes_remaining"] - (SIMULATION_INTERVAL / 60)
            )

            event = {
                "ts": datetime.utcnow().isoformat(),
                "shipment_id": shipment["shipment_id"],
                "lat": round(shipment["current_lat"], 6),
                "lon": round(shipment["current_lon"], 6),
                "speed_kmph": shipment["speed_kmph"],
                "origin": shipment["origin"],
                "destination": shipment["destination"],
                "eta_minutes_remaining": round(shipment["eta_minutes_remaining"], 1),
                "product_type": shipment["product_type"]
            }

            client.publish(GPS_TOPIC, json.dumps(event))
            print("Published GPS:", event)

        time.sleep(SIMULATION_INTERVAL)


if __name__ == "__main__":
    main()
