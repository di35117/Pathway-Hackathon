# sim/shipment_factory.py
"""
Builds the demo fleet.

Product types and their safe temperature ranges come from the SOP document via
core.sop_parser — editing watched_docs/cold_chain_SOP.txt changes what the fleet
carries and what counts as safe. Cargo economics and default routing mode come
from risk_engine_v2/configs/cargo_profiles.json.
"""

import random
from datetime import datetime, UTC

from sim.config import CITIES, NUMBER_OF_SHIPMENTS
from core.sop_parser import get_all_product_profiles

random.seed(42)

_shipments_cache = None

# Cargo value in ₹ and sensitivity per SOP product. Sensitivity drives how fast
# the temperature simulator drifts when a reefer degrades.
_CARGO_ECONOMICS = {
    "Vaccines":        {"value": 2_500_000, "sensitivity": "HIGH"},
    "Pharmaceuticals": {"value": 1_800_000, "sensitivity": "HIGH"},
    "Seafood":         {"value": 1_200_000, "sensitivity": "HIGH"},
    "Frozen_Meat":     {"value": 1_500_000, "sensitivity": "MEDIUM"},
    "Ice_Cream":       {"value":   900_000, "sensitivity": "MEDIUM"},
    "Dairy":           {"value":   800_000, "sensitivity": "MEDIUM"},
    "Flowers":         {"value":   600_000, "sensitivity": "MEDIUM"},
    "Vegetables":      {"value":   400_000, "sensitivity": "LOW"},
    "Fruits":          {"value":   500_000, "sensitivity": "LOW"},
}

_DEFAULT_ECONOMICS = {"value": 500_000, "sensitivity": "MEDIUM"}


def _product_catalogue():
    """SOP products joined with their economics, sorted for reproducibility."""
    catalogue = []
    for profile in get_all_product_profiles():
        econ = _CARGO_ECONOMICS.get(profile["name"], _DEFAULT_ECONOMICS)
        catalogue.append({
            "name": profile["name"],
            "safe_min": profile["safe_min"],
            "safe_max": profile["safe_max"],
            "base_value": econ["value"],
            "sensitivity": econ["sensitivity"],
        })
    catalogue.sort(key=lambda p: p["name"])
    return catalogue


def generate_shipments(force_regenerate=False):
    """
    Build (and cache) the fleet.

    The cache matters: under `sim-all` four simulator threads each call this, and
    they must receive the same list objects so a temperature drift written by one
    is visible to the others. Without it you get four independent fleets sharing
    shipment IDs and reporting contradictory telemetry.
    """
    global _shipments_cache

    if _shipments_cache is not None and not force_regenerate:
        return _shipments_cache

    products = _product_catalogue()
    if not products:
        raise RuntimeError("No product profiles available from SOP or fallback")

    shipments = []
    for i in range(NUMBER_OF_SHIPMENTS):
        start = random.choice(CITIES)
        end = random.choice(CITIES)
        while end == start:
            end = random.choice(CITIES)

        # Round-robin over the catalogue so all 9 product types appear in a
        # 25-truck fleet; random.choice would leave some types absent.
        product = products[i % len(products)]

        speed = random.randint(40, 70)
        distance_km = random.randint(200, 1200)
        eta_minutes = int((distance_km / speed) * 60)

        shipments.append({
            "shipment_id": f"SHP_{i + 1}",
            "origin": start[0],
            "destination": end[0],
            "start_time": datetime.now(UTC).isoformat(),

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
            "temp_mode": random.choice(["stable", "stable", "drift"]),
            # Fixed per shipment so diversion cost is stable across ticks.
            "nearest_hub_distance_km": random.randint(10, 80),
        })

    _shipments_cache = shipments
    return shipments
