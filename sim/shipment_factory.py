# sim/shipment_factory.py

import random
from datetime import datetime
from sim.config import CITIES, NUMBER_OF_SHIPMENTS

random.seed(42)

_shipments_cache = None

PRODUCT_PROFILES = [
    {
        "name": "Vaccines",
        "safe_min": 2,
        "safe_max": 8,
        "base_value": 2500000,
        "sensitivity": "HIGH"
    },
    {
        "name": "Frozen_Meat",
        "safe_min": -18,
        "safe_max": -15,
        "base_value": 1500000,
        "sensitivity": "MEDIUM"
    },
    {
        "name": "Dairy",
        "safe_min": 1,
        "safe_max": 4,
        "base_value": 800000,
        "sensitivity": "MEDIUM"
    },
    {
        "name": "Seafood",
        "safe_min": 0,
        "safe_max": 4,
        "base_value": 1200000,
        "sensitivity": "HIGH"
    }
]


def generate_shipments():
    global _shipments_cache

    if _shipments_cache is not None:
        return _shipments_cache

    shipments = []

    for i in range(NUMBER_OF_SHIPMENTS):

        start = random.choice(CITIES)
        end = random.choice(CITIES)

        while end == start:
            end = random.choice(CITIES)

        product = random.choice(PRODUCT_PROFILES)

        speed = random.randint(40, 70)

        # simple distance estimate (not exact)
        distance_km = random.randint(200, 1200)

        eta_minutes = int((distance_km / speed) * 60)

        shipment = {
            "shipment_id": f"SHP_{i+1}",
            "origin": start[0],
            "destination": end[0],
            "start_time": datetime.utcnow().isoformat(),

            "current_lat": start[1],
            "current_lon": start[2],
            "end_lat": end[1],
            "end_lon": end[2],

            "speed_kmph": speed,
            "distance_km": distance_km,
            "eta_minutes_remaining": eta_minutes,

            "product_type": product["name"],
            "safe_min_temp": product["safe_min"],
            "safe_max_temp": product["safe_max"],
            "cargo_value_inr": product["base_value"],
            "sensitivity": product["sensitivity"],

            "base_temp": (product["safe_min"] + product["safe_max"]) / 2,
            "temp_mode": random.choice(["stable", "stable", "drift"])
        }

        shipments.append(shipment)

    _shipments_cache = shipments
    return shipments
