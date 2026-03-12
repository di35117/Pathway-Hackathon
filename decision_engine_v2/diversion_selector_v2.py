"""
diversion_selector_v2.py — Capacity-aware cold-store diversion helper.
"""

import math


def haversine_km(lat1, lon1, lat2, lon2):
    """Compute great-circle distance in kilometers."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def choose_diversion_store(shipment, stores, spoilage_prob,
                           cost_per_km=50.0, handling_cost=2000.0):
    """
    Choose the best feasible store using expected-loss versus diversion-cost margin.

    Feasibility checks:
    - store open == True
    - store certified == True (if present)
    - store capacity >= shipment doses (when both are present)
    """
    if not stores:
        return None

    origin_lat = shipment.get("lat", shipment.get("current_lat"))
    origin_lon = shipment.get("lon", shipment.get("current_lon"))
    if origin_lat is None or origin_lon is None:
        return None

    value_inr = float(shipment.get("cargo_value_inr", shipment.get("value_inr", 0.0)))
    demand = shipment.get("doses", shipment.get("needed_capacity", 0))

    expected_loss = max(0.0, spoilage_prob) * value_inr
    best = None

    for store in stores:
        if not store.get("open", True):
            continue
        if store.get("certified", True) is False:
            continue

        store_capacity = store.get("capacity")
        if demand and store_capacity is not None and store_capacity < demand:
            continue

        lat = store.get("lat")
        lon = store.get("lon")
        if lat is None or lon is None:
            continue

        dist_km = haversine_km(float(origin_lat), float(origin_lon), float(lat), float(lon))
        diversion_cost = dist_km * cost_per_km + handling_cost
        score = expected_loss - diversion_cost

        candidate = {
            "store": store,
            "dist_km": round(dist_km, 3),
            "diversion_cost": round(diversion_cost, 2),
            "expected_loss": round(expected_loss, 2),
            "score": round(score, 2),
        }

        if best is None or candidate["score"] > best["score"]:
            best = candidate

    return best
