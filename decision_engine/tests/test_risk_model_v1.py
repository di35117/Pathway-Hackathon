"""
Property tests for the V1 risk model.

These exist because of a specific defect: the original scoring was
`sigmoid(deviation * 1.8 + exposure * 0.2)`, which saturates at roughly 3 C of
deviation. Every excursion past that returned exactly 1.0, making the
"probability" a step function. A monotonicity property test catches that class
of bug immediately, which is why it is pinned here.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from decision_engine.risk_model import compute_risk, sigmoid, BASELINE_RISK


def _state(temp, exposure=0.0, eta=300, lo=2, hi=6):
    return {
        "temp": temp,
        "safe_min_temp": lo,
        "safe_max_temp": hi,
        "exposure_minutes": exposure,
        "eta_minutes_remaining": eta,
    }


class TestSigmoid:
    def test_bounded(self):
        for x in (-10_000, -50, -1, 0, 1, 50, 10_000):
            assert 0.0 <= sigmoid(x) <= 1.0

    def test_no_overflow_at_extremes(self):
        assert sigmoid(-1e9) == pytest.approx(0.0, abs=1e-9)
        assert sigmoid(1e9) == pytest.approx(1.0, abs=1e-9)

    def test_midpoint(self):
        assert sigmoid(0) == pytest.approx(0.5)


class TestRiskProperties:
    def test_risk_is_always_a_probability(self):
        for temp in range(-60, 61, 3):
            for exposure in (0, 5, 60, 600):
                p = compute_risk(_state(temp, exposure))["risk_probability"]
                assert 0.0 <= p <= 1.0

    def test_never_saturates_to_certainty(self):
        """The regression guard. The model must not claim 100% certainty."""
        for temp in (14, 20, 30, 50, 100):
            p = compute_risk(_state(temp))["risk_probability"]
            assert p < 1.0, f"risk saturated to {p} at {temp}C"

    def test_strictly_increasing_across_the_operational_range(self):
        """The property the old model violated past 3 C of deviation.

        Checked out to 30 C — a 24 C excursion on a chilled load. Beyond that
        the curve is still rising but the increments fall below the 3-decimal
        rounding of the reported value, so the next test covers the tail as
        non-decreasing instead.
        """
        temps = [7, 8, 9, 10, 12, 14, 16, 20, 25, 30]
        risks = [compute_risk(_state(t))["risk_probability"] for t in temps]
        for earlier, later in zip(risks, risks[1:], strict=False):
            assert later > earlier, f"not increasing: {list(zip(temps, risks, strict=True))}"

    def test_non_decreasing_in_the_extreme_tail(self):
        temps = [30, 40, 60, 100, 200]
        risks = [compute_risk(_state(t))["risk_probability"] for t in temps]
        for earlier, later in zip(risks, risks[1:], strict=False):
            assert later >= earlier, f"decreased in tail: {list(zip(temps, risks, strict=True))}"

    def test_discriminates_across_the_operational_range(self):
        """A 1 C excursion and a 10 C excursion must be clearly different."""
        mild = compute_risk(_state(7))["risk_probability"]
        severe = compute_risk(_state(16))["risk_probability"]
        assert severe - mild > 0.4

    def test_non_decreasing_in_exposure(self):
        risks = [compute_risk(_state(9, exposure=e))["risk_probability"]
                 for e in (0, 1, 5, 15, 45, 120)]
        for earlier, later in zip(risks, risks[1:], strict=False):
            assert later >= earlier

    def test_in_range_returns_baseline(self):
        for temp in (2, 3, 4, 5, 6):
            r = compute_risk(_state(temp))
            assert r["risk_probability"] == BASELINE_RISK
            assert r["risk_level"] == "LOW"

    def test_never_reports_zero_risk(self):
        """Honest about model uncertainty: a perfect truck is not risk-free."""
        assert compute_risk(_state(4))["risk_probability"] >= BASELINE_RISK

    def test_deviation_is_symmetric_around_the_band(self):
        too_cold = compute_risk(_state(2 - 5, lo=2, hi=6))["risk_probability"]
        too_hot = compute_risk(_state(6 + 5, lo=2, hi=6))["risk_probability"]
        assert too_cold == pytest.approx(too_hot, abs=1e-6)

    def test_longer_eta_is_riskier(self):
        near = compute_risk(_state(12, eta=20))["risk_probability"]
        far = compute_risk(_state(12, eta=600))["risk_probability"]
        assert far > near

    def test_risk_levels_are_ordered(self):
        seen = {}
        for temp in range(6, 30):
            r = compute_risk(_state(temp))
            seen.setdefault(r["risk_level"], []).append(r["risk_probability"])
        if "LOW" in seen and "MEDIUM" in seen:
            assert max(seen["LOW"]) < min(seen["MEDIUM"])
        if "MEDIUM" in seen and "HIGH" in seen:
            assert max(seen["MEDIUM"]) < min(seen["HIGH"])

    def test_handles_missing_temperature(self):
        r = compute_risk({"temp": None, "safe_min_temp": 2, "safe_max_temp": 6})
        assert r["risk_probability"] == BASELINE_RISK

    def test_handles_missing_fields(self):
        assert 0.0 <= compute_risk({})["risk_probability"] <= 1.0
