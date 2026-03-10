# sim/shipment_factory.py
# Generates demo shipments with guaranteed diversity of scenarios for hackathon.

import random
from datetime import datetime
from sim.config import CITIES, NUMBER_OF_SHIPMENTS
from core.sop_parser import get_product_temp_ranges

random.seed(42)

_shipments_cache = None

# Business metadata (not SOP concerns — stays in code)
_PRODUCT_METADATA = {
    "Vaccines":        {"base_value": 2500000, "sensitivity": "HIGH"},
    "Frozen_Meat":     {"base_value": 1500000, "sensitivity": "MEDIUM"},
    "Dairy":           {"base_value": 800000,  "sensitivity": "MEDIUM"},
    "Seafood":         {"base_value": 1200000, "sensitivity": "HIGH"},
    "Vegetables":      {"base_value": 300000,  "sensitivity": "MEDIUM"},
    "Fruits":          {"base_value": 400000,  "sensitivity": "LOW"},
    "Pharmaceuticals": {"base_value": 2000000, "sensitivity": "HIGH"},
    "Ice_Cream":       {"base_value": 600000,  "sensitivity": "MEDIUM"},
    "Flowers":         {"base_value": 350000,  "sensitivity": "LOW"},
}


def _build_product_profiles():
    """Build product profiles by merging SOP temp ranges + code business metadata."""
    sop_ranges = get_product_temp_ranges()
    profiles = []
    for name, (safe_min, safe_max) in sop_ranges.items():
        meta = _PRODUCT_METADATA.get(name, {"base_value": 500000, "sensitivity": "MEDIUM"})
        profiles.append({
            "name": name,
            "safe_min": safe_min,
            "safe_max": safe_max,
            "base_value": meta["base_value"],
            "sensitivity": meta["sensitivity"],
        })
    return profiles


PRODUCT_PROFILES = _build_product_profiles()

# ── Demo scenario assignments ─────────────────────────────────────
# Guarantee that specific shipments showcase specific features.
# Index maps to shipment SHP_{i+1}.
#
# Scenarios:
#   "critical"  → Starts ABOVE safe_max, immediate DIVERT + WhatsApp
#   "drift"     → Starts safe, drifts up slowly → triggers DIVERT after ~20s
#   "stable"    → Stays in safe range (healthy truck)
#   "cold_drift"→ Drifts below safe_min (for frozen products)

DEMO_SCENARIOS = {
    # ── Immediate diversions (show DIVERT + WhatsApp within 5 seconds) ──
    0:  {"product": "Seafood",         "mode": "critical"},   # SHP_1
    1:  {"product": "Frozen_Meat",     "mode": "critical"},   # SHP_2
    2:  {"product": "Dairy",           "mode": "critical"},   # SHP_3
    3:  {"product": "Vaccines",        "mode": "critical"},   # SHP_4
    4:  {"product": "Pharmaceuticals", "mode": "critical"},   # SHP_5

    # ── Drifting shipments (show gradual risk increase → DIVERT after ~20-30s) ──
    5:  {"product": "Fruits",          "mode": "drift"},      # SHP_6
    6:  {"product": "Vegetables",      "mode": "drift"},      # SHP_7
    7:  {"product": "Ice_Cream",       "mode": "drift"},      # SHP_8
    8:  {"product": "Seafood",         "mode": "drift"},      # SHP_9
    9:  {"product": "Flowers",         "mode": "drift"},      # SHP_10

    # ── Healthy shipments (show normal operation, green status) ──
    10: {"product": "Dairy",           "mode": "stable"},     # SHP_11
    11: {"product": "Frozen_Meat",     "mode": "stable"},     # SHP_12
    12: {"product": "Vaccines",        "mode": "stable"},     # SHP_13
    13: {"product": "Fruits",          "mode": "stable"},     # SHP_14
    14: {"product": "Vegetables",      "mode": "stable"},     # SHP_15
    15: {"product": "Pharmaceuticals", "mode": "stable"},     # SHP_16
    16: {"product": "Ice_Cream",       "mode": "stable"},     # SHP_17
    17: {"product": "Flowers",         "mode": "stable"},     # SHP_18
    18: {"product": "Seafood",         "mode": "stable"},     # SHP_19
    19: {"product": "Dairy",           "mode": "stable"},     # SHP_20

    # ── More drift for variety ──
    20: {"product": "Dairy",           "mode": "drift"},      # SHP_21
    21: {"product": "Frozen_Meat",     "mode": "drift"},      # SHP_22
    22: {"product": "Pharmaceuticals", "mode": "drift"},      # SHP_23
    23: {"product": "Vegetables",      "mode": "drift"},      # SHP_24
    24: {"product": "Seafood",         "mode": "drift"},      # SHP_25
}


def _get_profile_by_name(name):
    """Find a product profile by name."""
    for p in PRODUCT_PROFILES:
        if p["name"] == name:
            return p
    return PRODUCT_PROFILES[0]  # fallback


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

        # Use scenario assignment if available, else random
        scenario = DEMO_SCENARIOS.get(i)
        if scenario:
            product = _get_profile_by_name(scenario["product"])
            mode = scenario["mode"]
        else:
            product = random.choice(PRODUCT_PROFILES)
            mode = random.choice(["stable", "drift"])

        speed = random.randint(40, 70)
        distance_km = random.randint(200, 1200)
        eta_minutes = int((distance_km / speed) * 60)

        # ── Set starting temp based on scenario ──────────────────
        safe_min = product["safe_min"]
        safe_max = product["safe_max"]
        safe_mid = (safe_min + safe_max) / 2

        if mode == "critical":
            # Start ABOVE safe_max by 3-5°C → immediate high risk
            base_temp = safe_max + random.uniform(3, 5)
        elif mode == "drift":
            # Start just below safe_max → will breach in ~10-15 seconds
            base_temp = safe_max - random.uniform(0.3, 0.8)
        elif mode == "cold_drift":
            # Start just above safe_min → drifts below
            base_temp = safe_min + random.uniform(0.3, 0.8)
        else:
            # Stable — solidly in the middle of safe range
            base_temp = safe_mid + random.uniform(-0.5, 0.5)

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
            "safe_min_temp": safe_min,
            "safe_max_temp": safe_max,
            "cargo_value_inr": product["base_value"],
            "sensitivity": product["sensitivity"],

            "base_temp": base_temp,
            "temp_mode": mode if mode != "critical" else "drift",
        }

        shipments.append(shipment)

    _shipments_cache = shipments
    return shipments
