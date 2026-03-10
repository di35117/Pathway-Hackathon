"""Additional tests for non-breaking V2 risk extensions."""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from risk_engine_v2.risk_calculator_v2 import (
    compute_exposure_increment,
    compute_spoilage_probability,
    linear_forecast,
    assess_risk_v2,
    reset_tracking,
)


def test_degree_hour_increment_positive():
    inc = compute_exposure_increment(temp_c=12.0, safe_max_c=8.0, dt_hours=2.0)
    assert inc == 8.0


def test_degree_hour_increment_zero_when_safe():
    inc = compute_exposure_increment(temp_c=7.5, safe_max_c=8.0, dt_hours=2.0)
    assert inc == 0.0


def test_spoilage_probability_monotonic():
    p_low = compute_spoilage_probability(5.0)
    p_high = compute_spoilage_probability(25.0)
    assert 0.0 <= p_low <= 1.0
    assert 0.0 <= p_high <= 1.0
    assert p_high > p_low


def test_linear_forecast_uptrend():
    t0 = datetime(2026, 3, 10, 10, 0, 0)
    readings = [
        (t0, 6.0),
        (t0 + timedelta(minutes=5), 7.0),
        (t0 + timedelta(minutes=10), 8.0),
    ]
    predicted = linear_forecast(readings, horizon_minutes=10)
    assert predicted is not None
    assert predicted > 8.0


def test_assess_risk_includes_extension_fields():
    reset_tracking()
    telemetry = {
        "shipment_id": "EXT-001",
        "temperature": 12.0,
        "door_status": "CLOSED",
        "door_open_sec": 0,
        "compressor": {"status": "RUNNING", "load_pct": 70},
        "eta_minutes_remaining": 120,
        "product_type": "vaccines",
        "safe_min_temp": 2,
        "safe_max_temp": 8,
    }
    result = assess_risk_v2(telemetry, delta_t_seconds=3600)
    assert "exposure_degree_hours" in result
    assert "spoilage_probability" in result
    assert result["exposure_degree_hours"] >= 4.0
