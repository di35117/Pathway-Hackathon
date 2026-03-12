"""
test_risk_v2.py — Tests for Risk Engine V2 modules.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from risk_engine_v2.cargo_profiles import (
    load_cargo_profile, get_temp_range, get_weights,
    get_max_exposure, list_cargo_types,
)
from risk_engine_v2.exposure_tracker import ExposureTracker
from risk_engine_v2.drift_analyzer import DriftAnalyzer
from risk_engine_v2.risk_calculator_v2 import assess_risk_v2, _sigmoid, reset_tracking


# ── Cargo profile tests ──────────────────────────────────────────────────────

class TestCargoProfiles:
    def test_load_vaccines(self):
        p = load_cargo_profile("vaccines")
        assert p["ideal_temp_min"] == 2
        assert p["ideal_temp_max"] == 8

    def test_load_frozen_meat_alt_name(self):
        p = load_cargo_profile("Frozen_Meat")
        assert p["ideal_temp_min"] == -18

    def test_get_temp_range(self):
        lo, hi = get_temp_range("seafood")
        assert lo == 0
        assert hi == 4

    def test_get_weights_has_all_keys(self):
        w = get_weights("dairy")
        expected_keys = {"temp_sensitivity", "door_event", "compressor",
                         "exposure_time", "eta_pressure", "drift_rate"}
        assert set(w.keys()) == expected_keys

    def test_max_exposure(self):
        assert get_max_exposure("vaccines") == 10
        assert get_max_exposure("frozen_meat") == 120

    def test_list_cargo_types(self):
        types = list_cargo_types()
        assert len(types) >= 4
        assert "vaccines" in types


# ── Exposure tracker tests ───────────────────────────────────────────────────

class TestExposureTracker:
    def test_accumulates_out_of_range(self):
        tracker = ExposureTracker()
        # Temp 12°C is outside vaccines range (2-8)
        result = tracker.update("S001", 12.0, 2, 8, 60)  # 1 minute
        assert result["exposure_minutes"] == 1.0
        assert result["is_out_of_range"] is True

    def test_no_accumulation_in_range(self):
        tracker = ExposureTracker()
        result = tracker.update("S001", 5.0, 2, 8, 60)
        assert result["exposure_minutes"] == 0.0
        assert result["is_out_of_range"] is False

    def test_resets_after_recovery(self):
        tracker = ExposureTracker()
        # Accumulate 2 minutes of exposure
        tracker.update("S001", 12.0, 2, 8, 120)
        assert tracker.get_exposure("S001") == 2.0

        # Recover for 6 minutes (above 5-min threshold)
        tracker.update("S001", 5.0, 2, 8, 360)
        assert tracker.get_exposure("S001") == 0.0

    def test_no_reset_before_threshold(self):
        tracker = ExposureTracker()
        tracker.update("S001", 12.0, 2, 8, 120)
        # Recover for only 3 minutes (below 5-min threshold)
        tracker.update("S001", 5.0, 2, 8, 180)
        assert tracker.get_exposure("S001") > 0


# ── Drift analyzer tests ────────────────────────────────────────────────────

class TestDriftAnalyzer:
    def test_no_drift_single_reading(self):
        analyzer = DriftAnalyzer()
        result = analyzer.update("S001", 5.0, 2)
        assert result["drift_rate_c_min"] == 0.0

    def test_positive_drift(self):
        analyzer = DriftAnalyzer()
        # Simulate rising temperature
        for i in range(30):
            result = analyzer.update("S001", 5.0 + i * 0.5, 10)
        assert result["drift_rate_c_min"] > 0

    def test_critical_drift_flagged(self):
        analyzer = DriftAnalyzer()
        # Rapid temperature rise
        for i in range(30):
            result = analyzer.update("S001", 5.0 + i * 2.0, 10)
        assert result["is_critical"] is True

    def test_stable_temp_no_drift(self):
        analyzer = DriftAnalyzer()
        for _ in range(30):
            result = analyzer.update("S001", 5.0, 10)
        assert abs(result["drift_rate_c_min"]) < 0.01


# ── Risk calculator tests ───────────────────────────────────────────────────

class TestRiskCalculator:
    @pytest.fixture(autouse=True)
    def reset(self):
        reset_tracking()

    def _make_telemetry(self, temp=5.0, door="CLOSED", door_sec=0,
                        comp_status="RUNNING", comp_load=70,
                        eta=300, product="vaccines"):
        return {
            "shipment_id": "TEST-001",
            "temperature": temp,
            "door_status": door,
            "door_open_sec": door_sec,
            "compressor": {"status": comp_status, "load_pct": comp_load},
            "eta_minutes_remaining": eta,
            "product_type": product,
            "safe_min_temp": 2,
            "safe_max_temp": 8,
        }

    def test_low_risk_normal_conditions(self):
        telemetry = self._make_telemetry(temp=5.0)
        result = assess_risk_v2(telemetry)
        assert result["risk_level"] == "LOW"
        assert result["risk_probability"] < 0.35

    def test_high_risk_temp_deviation(self):
        # Simulate sustained high temperature (15°C, 7° above max)
        # Need enough readings with big delta_t to accumulate exposure
        for i in range(40):
            telemetry = self._make_telemetry(temp=15.0)
            result = assess_risk_v2(telemetry, delta_t_seconds=60)
        assert result["risk_level"] in ("HIGH", "MEDIUM")
        assert result["risk_probability"] > 0.50

    def test_medium_risk_door_open(self):
        telemetry = self._make_telemetry(
            temp=7.5, door="OPEN", door_sec=120
        )
        result = assess_risk_v2(telemetry)
        assert result["risk_probability"] > 0.1

    def test_compressor_off_raises_risk(self):
        t1 = self._make_telemetry(temp=6.0, comp_status="RUNNING")
        r1 = assess_risk_v2(t1, cargo_type="vaccines")

        reset_tracking()

        t2 = self._make_telemetry(temp=6.0, comp_status="OFF")
        r2 = assess_risk_v2(t2, cargo_type="vaccines")

        assert r2["factor_scores"]["compressor"] > r1["factor_scores"]["compressor"]

    def test_sigmoid_bounds(self):
        assert 0.0 <= _sigmoid(-10) < 0.01
        assert _sigmoid(10) >= 0.99
        assert 0.3 < _sigmoid(0.55) < 0.7  # midpoint check

    def test_output_schema(self):
        telemetry = self._make_telemetry()
        result = assess_risk_v2(telemetry)

        assert "shipment_id" in result
        assert "risk_probability" in result
        assert "risk_level" in result
        assert "factor_scores" in result
        assert len(result["factor_scores"]) == 6
        assert "exposure_minutes" in result
        assert "drift_rate_c_min" in result
