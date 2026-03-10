"""Tests for capacity-aware diversion selector in Decision Engine V2."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from decision_engine_v2.diversion_selector_v2 import choose_diversion_store


def test_choose_store_skips_closed_and_capacity_shortage():
    shipment = {
        "lat": 28.4595,
        "lon": 77.0266,
        "cargo_value_inr": 500000,
        "doses": 250,
    }
    stores = [
        {"id": "cs001", "name": "Closed", "lat": 28.45, "lon": 77.02,
         "capacity": 1000, "open": False, "certified": True},
        {"id": "cs002", "name": "Small", "lat": 28.46, "lon": 77.03,
         "capacity": 100, "open": True, "certified": True},
        {"id": "cs003", "name": "Feasible", "lat": 28.47, "lon": 77.04,
         "capacity": 300, "open": True, "certified": True},
    ]

    result = choose_diversion_store(shipment, stores, spoilage_prob=0.5)
    assert result is not None
    assert result["store"]["id"] == "cs003"


def test_returns_none_when_origin_missing():
    shipment = {"cargo_value_inr": 500000, "doses": 250}
    stores = [{"id": "cs001", "lat": 28.45, "lon": 77.02, "open": True}]
    assert choose_diversion_store(shipment, stores, spoilage_prob=0.5) is None
