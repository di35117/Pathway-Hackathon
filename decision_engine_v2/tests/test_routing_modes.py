"""
Tests that SAFETY / BALANCED / ECO are genuinely different decision rules.

The README advertises three routing modes. Previously the optimiser only
branched on eco-vs-not, so SAFETY and BALANCED were byte-identical. These tests
pin the distinction so it cannot silently regress.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from decision_engine_v2.economic_model import should_divert, _load_config
from decision_engine_v2.decision_logic_v2 import decide_v2, reset_tracking
from risk_engine_v2.cargo_profiles import get_default_routing_mode


@pytest.fixture(autouse=True)
def _clean():
    reset_tracking()
    yield
    reset_tracking()


class TestModeDefaults:
    def test_vaccines_and_pharma_default_to_safety(self):
        assert get_default_routing_mode("vaccines") == "SAFETY"
        assert get_default_routing_mode("pharmaceuticals") == "SAFETY"

    def test_produce_defaults_to_eco(self):
        for cargo in ("fruits", "vegetables", "flowers"):
            assert get_default_routing_mode(cargo) == "ECO"

    def test_staples_default_to_balanced(self):
        for cargo in ("dairy", "seafood", "frozen_meat", "ice_cream"):
            assert get_default_routing_mode(cargo) == "BALANCED"

    def test_unknown_cargo_is_balanced(self):
        assert get_default_routing_mode("unobtainium") == "BALANCED"


class TestSafetyMode:
    def test_safety_diverts_when_economics_say_no(self):
        """The whole point of SAFETY: cargo integrity outranks cost.

        Cheap consignment, expensive detour — BALANCED refuses, SAFETY does not.
        """
        expected_loss, diversion_cost, risk = 12_000, 40_000, 0.80

        balanced = should_divert(expected_loss, diversion_cost,
                                 routing_mode="BALANCED", risk_probability=risk)
        safety = should_divert(expected_loss, diversion_cost,
                               routing_mode="SAFETY", risk_probability=risk)

        assert balanced["should_divert"] is False
        assert safety["should_divert"] is True
        assert "cost not consulted" in safety["mode_rule"]

    def test_safety_is_a_superset_of_balanced(self):
        """SAFETY must never divert LESS readily than BALANCED, at any input."""
        cfg = _load_config()
        threshold = cfg["safety_divert_risk_threshold"]

        for loss in (0, 5_000, 25_000, 500_000, 5_000_000):
            for cost in (1_000, 20_000, 200_000):
                for risk in (0.0, 0.2, threshold - 0.01, threshold, 0.9):
                    b = should_divert(loss, cost, routing_mode="BALANCED",
                                      risk_probability=risk)["should_divert"]
                    s = should_divert(loss, cost, routing_mode="SAFETY",
                                      risk_probability=risk)["should_divert"]
                    assert not (b and not s), (
                        f"SAFETY refused where BALANCED diverted: "
                        f"loss={loss} cost={cost} risk={risk}"
                    )

    def test_safety_falls_back_to_economics_below_threshold(self):
        cfg = _load_config()
        low_risk = cfg["safety_divert_risk_threshold"] - 0.2
        # Economics strongly favour diverting.
        r = should_divert(1_000_000, 10_000, routing_mode="SAFETY",
                          risk_probability=low_risk)
        assert r["should_divert"] is True
        assert "falling back to economics" in r["mode_rule"]


class TestEcoMode:
    def test_eco_refuses_a_high_carbon_detour(self):
        """A long detour for modest cargo is rejected on emissions grounds."""
        cfg = _load_config()
        over_limit = cfg["eco_co2_limit_kg"] + 10

        balanced = should_divert(60_000, 20_000, routing_mode="BALANCED",
                                 risk_probability=0.5, co2_delta_kg=over_limit)
        eco = should_divert(60_000, 20_000, routing_mode="ECO",
                            risk_probability=0.5, co2_delta_kg=over_limit)

        assert balanced["should_divert"] is True
        assert eco["should_divert"] is False
        assert "CO2" in eco["mode_rule"]

    def test_eco_allows_diversion_when_loss_is_catastrophic(self):
        """The carbon veto is overridden when the cargo at stake is large."""
        cfg = _load_config()
        over_limit = cfg["eco_co2_limit_kg"] + 10
        override = cfg["eco_override_multiplier"]

        cost = 20_000
        huge_loss = cost * override * 10

        eco = should_divert(huge_loss, cost, routing_mode="ECO",
                            risk_probability=0.8, co2_delta_kg=over_limit)
        assert eco["should_divert"] is True

    def test_eco_prices_carbon_into_the_cost(self):
        r = should_divert(100_000, 20_000, routing_mode="ECO",
                          risk_probability=0.6, co2_delta_kg=5)
        assert r["carbon_adjusted_cost"] > 20_000

    def test_zero_carbon_eco_matches_balanced(self):
        """With no extra emissions, ECO reduces to the plain economic rule."""
        for loss in (10_000, 100_000, 1_000_000):
            b = should_divert(loss, 30_000, routing_mode="BALANCED",
                              risk_probability=0.7)["should_divert"]
            e = should_divert(loss, 30_000, routing_mode="ECO",
                              risk_probability=0.7, co2_delta_kg=0)["should_divert"]
            assert b == e


class TestModesThroughDecideV2:
    @staticmethod
    def _risk(prob, level):
        return {
            "shipment_id": "SHP_T",
            "risk_probability": prob,
            "risk_level": level,
            "cargo_type": "vaccines",
            "factor_scores": {
                "temp_deviation": 0.9, "exposure_time": 0.5, "eta_pressure": 0.4,
                "door_events": 0.2, "compressor": 0.8, "drift_rate": 0.7,
            },
            "exposure_minutes": 12.0,
            "exposure_degree_hours": 1.2,
            "spoilage_probability": 0.4,
        }

    def test_mode_appears_in_the_decision_output(self):
        for mode in ("SAFETY", "BALANCED", "ECO"):
            d = decide_v2(self._risk(0.8, "HIGH"),
                          {"cargo_value_inr": 500_000,
                           "nearest_hub_distance_km": 30,
                           "routing_mode": mode,
                           "product_type": "vaccines"})
            assert d["routing_mode"] == mode
            assert d["mode_rule"]

    def test_explicit_mode_overrides_cargo_default(self):
        d = decide_v2(self._risk(0.8, "HIGH"),
                      {"cargo_value_inr": 500_000,
                       "nearest_hub_distance_km": 30,
                       "routing_mode": "ECO",
                       "product_type": "vaccines"})   # vaccines default to SAFETY
        assert d["routing_mode"] == "ECO"

    def test_cargo_default_applies_when_unset(self):
        d = decide_v2(self._risk(0.8, "HIGH"),
                      {"cargo_value_inr": 500_000,
                       "nearest_hub_distance_km": 30,
                       "product_type": "vaccines"})
        assert d["routing_mode"] == "SAFETY"

    def test_low_risk_continues_in_every_mode(self):
        """A sanity floor: at LOW risk the economic rule alone would fire for
        valuable cargo, because 10% of 25 lakh still beats a detour."""
        for mode in ("SAFETY", "BALANCED", "ECO"):
            d = decide_v2(self._risk(0.10, "LOW"),
                          {"cargo_value_inr": 2_500_000,
                           "nearest_hub_distance_km": 15,
                           "routing_mode": mode,
                           "product_type": "vaccines"})
            assert d["action"] == "CONTINUE", f"{mode} diverted at LOW risk"
