"""
test_decision_v2.py — Tests for Decision Engine V2 modules.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from decision_engine_v2.economic_model import (
    calculate_expected_loss,
    calculate_diversion_cost,
    should_divert,
)
from decision_engine_v2.confidence_scorer import score_confidence
from decision_engine_v2.decision_logic_v2 import decide_v2, reset_tracking


# ── Economic model tests ─────────────────────────────────────────────────────

class TestEconomicModel:
    def test_expected_loss_calculation(self):
        loss = calculate_expected_loss(0.7, 1000000)
        assert loss == 700000

    def test_expected_loss_zero_risk(self):
        loss = calculate_expected_loss(0.0, 1000000)
        assert loss == 0

    def test_diversion_cost_structure(self):
        result = calculate_diversion_cost(30, 0.7, 1000000)
        assert "total_cost" in result
        assert "fuel_cost" in result
        assert "hub_cost" in result
        assert "residual_loss" in result
        assert "co2_delta_kg" in result
        assert result["fuel_cost"] == 30 * 42  # 30km × ₹42/km

    def test_should_divert_yes(self):
        # High loss, low diversion cost
        result = should_divert(500000, 50000)
        assert result["should_divert"] is True
        assert result["saving"] > 0

    def test_should_divert_no(self):
        # Low loss, high diversion cost
        result = should_divert(10000, 50000)
        assert result["should_divert"] is False

    def test_buffer_prevents_borderline(self):
        # Loss just barely above diversion cost
        result = should_divert(50400, 50000)
        # Buffer is ₹500, so 50400 < 50000 + 500 = 50500
        assert result["should_divert"] is False


# ── Confidence scorer tests ──────────────────────────────────────────────────

class TestConfidenceScorer:
    @pytest.fixture
    def all_elevated_factors(self):
        return {
            "temp_deviation": 0.8,
            "exposure_time": 0.6,
            "eta_pressure": 0.5,
            "door_events": 0.7,
            "compressor": 0.9,
            "drift_rate": 0.4,
        }

    @pytest.fixture
    def mixed_factors(self):
        return {
            "temp_deviation": 0.8,
            "exposure_time": 0.1,
            "eta_pressure": 0.05,
            "door_events": 0.7,
            "compressor": 0.02,
            "drift_rate": 0.4,
        }

    @pytest.fixture
    def low_factors(self):
        return {
            "temp_deviation": 0.05,
            "exposure_time": 0.02,
            "eta_pressure": 0.01,
            "door_events": 0.0,
            "compressor": 0.03,
            "drift_rate": 0.01,
        }

    def test_high_confidence(self, all_elevated_factors):
        result = score_confidence(
            all_elevated_factors,
            signal_duration_sec=700,
            risk_level="HIGH"
        )
        assert result["confidence"] == "HIGH"

    def test_medium_confidence(self, mixed_factors):
        result = score_confidence(
            mixed_factors,
            signal_duration_sec=300,
            risk_level="HIGH"
        )
        assert result["confidence"] == "MEDIUM"

    def test_low_confidence_stale(self, all_elevated_factors):
        result = score_confidence(
            all_elevated_factors,
            signal_duration_sec=700,
            data_staleness_sec=60,  # stale data
            risk_level="HIGH"
        )
        assert result["confidence"] == "LOW"

    def test_low_confidence_few_factors(self, low_factors):
        result = score_confidence(
            low_factors,
            signal_duration_sec=100,
            risk_level="HIGH"
        )
        # Few factors elevated → LOW
        assert result["confidence"] in ("LOW", "MEDIUM")


# ── Decision logic tests ─────────────────────────────────────────────────────

class TestDecisionLogic:
    @pytest.fixture(autouse=True)
    def reset(self):
        reset_tracking()

    def _make_risk(self, risk_prob=0.1, risk_level="LOW"):
        return {
            "shipment_id": "TEST-001",
            "cargo_type": "vaccines",
            "risk_probability": risk_prob,
            "risk_level": risk_level,
            "factor_scores": {
                "temp_deviation": risk_prob,
                "exposure_time": risk_prob * 0.5,
                "eta_pressure": 0.1,
                "door_events": 0.0,
                "compressor": 0.0,
                "drift_rate": 0.0,
            },
            "exposure_minutes": 0,
            "drift_rate_c_min": 0.0,
        }

    def _make_shipment(self):
        return {
            "shipment_id": "TEST-001",
            "cargo_value_inr": 2500000,
            "nearest_hub_distance_km": 25,
        }

    def test_continue_low_risk(self):
        risk = self._make_risk(0.1, "LOW")
        decision = decide_v2(risk, self._make_shipment())
        assert decision["action"] == "CONTINUE"

    def test_divert_high_risk(self):
        risk = self._make_risk(0.85, "HIGH")
        # Make all factors elevated for high risk
        risk["factor_scores"] = {k: 0.8 for k in risk["factor_scores"]}
        decision = decide_v2(risk, self._make_shipment())
        assert decision["action"] in ("DIVERT", "MONITOR_CLOSELY")

    def test_output_schema(self):
        risk = self._make_risk(0.5, "MEDIUM")
        decision = decide_v2(risk, self._make_shipment())
        assert "shipment_id" in decision
        assert "action" in decision
        assert "confidence" in decision
        assert "expected_loss_continue" in decision
        assert "total_diversion_cost" in decision
        assert "saving" in decision
        assert "selected_hub" in decision

    def test_divert_reason_provided(self):
        risk = self._make_risk(0.85, "HIGH")
        risk["factor_scores"] = {k: 0.9 for k in risk["factor_scores"]}
        decision = decide_v2(risk, self._make_shipment())
        assert len(decision["divert_reason"]) > 0

    def test_mock_hub_selector(self):
        def mock_hub(state):
            return {"nearest_hub_distance_km": 10}

        risk = self._make_risk(0.85, "HIGH")
        risk["factor_scores"] = {k: 0.8 for k in risk["factor_scores"]}
        decision = decide_v2(risk, self._make_shipment(),
                             hub_selector=mock_hub)
        assert decision["total_diversion_cost"] > 0
