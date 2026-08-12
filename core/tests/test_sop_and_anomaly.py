"""
Tests for the SOP source-of-truth contract and the anomaly detector.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from core import sop_parser
from core.sop_parser import (
    get_product_temp_ranges,
    get_product_profile,
    get_all_product_profiles,
    get_source,
)
from core.anomaly_detector import (
    AnomalyDetector,
    MAX_RATE_C_PER_SEC,
    MAX_RATE_ABSOLUTE_C,
    STUCK_SENSOR_COUNT,
)


# ── SOP as single source of truth ────────────────────────────────

class TestSopParser:
    def test_reads_from_sop_not_fallback(self):
        assert get_source() == "sop"

    def test_all_nine_products_present(self):
        ranges = get_product_temp_ranges()
        assert len(ranges) == 9
        for expected in ("Vaccines", "Dairy", "Seafood", "Frozen_Meat",
                         "Vegetables", "Fruits", "Pharmaceuticals",
                         "Ice_Cream", "Flowers"):
            assert expected in ranges

    def test_ranges_are_ordered(self):
        for name, (lo, hi) in get_product_temp_ranges().items():
            assert lo < hi, f"{name} has an inverted range"

    def test_name_normalisation(self):
        for variant in ("Frozen_Meat", "frozen meat", "FROZEN-MEAT", " Frozen Meat "):
            assert get_product_profile(variant)["safe_min"] == -18

    def test_unknown_product_falls_back_to_chilled(self):
        p = get_product_profile("Unobtainium")
        assert (p["safe_min"], p["safe_max"]) == (2.0, 8.0)

    def test_all_profiles_listed(self):
        assert len(get_all_product_profiles()) == 9

    def test_editing_the_sop_changes_the_ranges(self, tmp_path, monkeypatch):
        """The core claim: the SOP file drives system behaviour."""
        sop = tmp_path / "sop.txt"
        sop.write_text(
            "Cold Chain SOP\n\n"
            "<!-- PRODUCT_TEMP_RANGES\n"
            "Dairy:1:3\n"
            "Vaccines:2:8\n"
            "-->\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sop_parser, "SOP_PATH", str(sop))
        sop_parser._cache.update(ranges=None, mtime=None)

        assert get_product_profile("Dairy")["safe_max"] == 3

        # Edit the document; the parser must pick it up without a restart.
        time.sleep(0.01)
        sop.write_text(
            "Cold Chain SOP\n\n"
            "<!-- PRODUCT_TEMP_RANGES\n"
            "Dairy:1:9\n"
            "Vaccines:2:8\n"
            "-->\n",
            encoding="utf-8",
        )
        os.utime(str(sop), (time.time() + 2, time.time() + 2))

        assert get_product_profile("Dairy")["safe_max"] == 9

        sop_parser._cache.update(ranges=None, mtime=None)

    def test_malformed_rows_are_skipped_not_fatal(self, tmp_path, monkeypatch):
        sop = tmp_path / "sop.txt"
        sop.write_text(
            "<!-- PRODUCT_TEMP_RANGES\n"
            "Dairy:2:6\n"
            "Broken:notanumber:6\n"
            "TooFewFields:5\n"
            "Inverted:10:2\n"
            "Vaccines:2:8\n"
            "-->\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sop_parser, "SOP_PATH", str(sop))
        sop_parser._cache.update(ranges=None, mtime=None)

        ranges = get_product_temp_ranges()
        assert set(ranges) == {"Dairy", "Vaccines"}

        sop_parser._cache.update(ranges=None, mtime=None)


# ── Anomaly detection ────────────────────────────────────────────

class TestAnomalyLayers:
    def setup_method(self):
        self.d = AnomalyDetector()

    def test_l1_rejects_impossible_values(self):
        for bad in (999.0, -999.0, 500.0, -200.0):
            r = self.d.check("S", bad, "dairy")
            assert r.is_anomaly and r.layer == "L1_BOUNDS"
            # No safe substitute exists for a garbage reading.
            assert r.corrected_temp is None

    def test_l1_bounds_are_per_product(self):
        # -40C is a hardware fault for dairy but normal for ice cream.
        assert self.d.check("A", -40.0, "dairy").layer == "L1_BOUNDS"
        assert not self.d.check("B", -40.0, "ice_cream").is_anomaly

    def test_l2_catches_electrical_step(self):
        self.d.check("S", 4.0, "dairy")
        r = self.d.check("S", 24.0, "dairy")
        assert r.is_anomaly and r.layer == "L2_RATE"
        assert r.corrected_temp == 4.0  # falls back to last good reading

    def test_l2_allowance_is_capped(self):
        """A long gap must not disable the check.

        The old form multiplied a per-reading budget by elapsed seconds without
        a ceiling, so a 60-second stall permitted a 180C swing.
        """
        state = self.d._states["S"]
        self.d.check("S", 4.0, "dairy")
        state.last_time = time.time() - 600  # ten minute gap

        r = self.d.check("S", 4.0 + MAX_RATE_ABSOLUTE_C + 5, "dairy")
        assert r.is_anomaly and r.layer == "L2_RATE"

    def test_l2_permits_real_thermal_drift(self):
        temp = 4.0
        for _ in range(10):
            temp += 0.4  # a plausible door-open rise
            assert not self.d.check("S", temp, "dairy").is_anomaly

    def test_l3_needs_history_before_firing(self):
        # Fewer than 5 samples: standard deviation is meaningless.
        for t in (4.0, 4.1, 4.2):
            assert not self.d.check("S", t, "dairy").is_anomaly

    def test_l3_catches_statistical_outlier(self):
        for _ in range(12):
            self.d.check("S", 4.0 + (0.05 if _ % 2 else -0.05), "dairy")
        r = self.d.check("S", 6.0, "dairy")
        assert r.is_anomaly and r.layer == "L3_ZSCORE"

    def test_l3_does_not_fire_on_a_very_stable_sensor(self):
        """Guard against an inverted incentive: better refrigeration means a
        near-zero standard deviation, which would make every reading look like a
        huge z-score outlier without the std_dev floor.

        Readings vary by a hair so this exercises L3 alone — perfectly identical
        readings are a stuck sensor and are L4's job.
        """
        for i in range(20):
            r = self.d.check("S", 4.0 + (0.002 if i % 2 else -0.002), "dairy")
            assert not r.is_anomaly, f"reading {i} wrongly flagged as {r.layer}"

    def test_l4_detects_stuck_sensor(self):
        results = [self.d.check("S", 4.0, "dairy")
                   for _ in range(STUCK_SENSOR_COUNT + 2)]
        fired = [r for r in results if r.is_anomaly]
        assert fired and fired[0].layer == "L4_STUCK"
        # The value may be correct; the sensor needs maintenance.
        assert fired[0].corrected_temp == 4.0

    def test_l4_is_edge_triggered(self):
        """A stuck sensor stays stuck. Reporting it on every subsequent reading
        would spam the log and inflate the anomaly counters, so the condition is
        reported once."""
        for _ in range(60):
            self.d.check("S", 4.0, "dairy")
        assert self.d.get_stats()["l4_stuck"] == 1

    def test_l4_rearms_after_recovery(self):
        for _ in range(STUCK_SENSOR_COUNT + 2):
            self.d.check("S", 4.0, "dairy")
        assert self.d.get_stats()["l4_stuck"] == 1

        # Sensor starts moving again. The recovery has to be gradual: a jump
        # straight to a new plateau is a z-score outlier, and L3 short-circuits
        # before L4 ever sees it — which is the layering working as intended.
        temp = 4.0
        for _ in range(25):
            temp += 0.05
            self.d.check("S", round(temp, 3), "dairy")
        assert self.d.get_stats()["l4_stuck"] == 1, "must not re-fire while moving"

        # Now it sticks again at the new value.
        plateau = round(temp, 3)
        for _ in range(STUCK_SENSOR_COUNT + 2):
            self.d.check("S", plateau, "dairy")
        assert self.d.get_stats()["l4_stuck"] == 2

    def test_rejected_readings_never_enter_the_window(self):
        """The single most important property: garbage must not poison the
        statistics that later layers depend on."""
        for t in (4.0, 4.1, 4.05, 4.2, 4.1, 4.0):
            self.d.check("S", t, "dairy")
        before = list(self.d._states["S"].history)

        self.d.check("S", 999.0, "dairy")   # L1
        self.d.check("S", 60.0, "dairy")    # L2

        assert list(self.d._states["S"].history) == before

    def test_stats_are_copies_not_live_references(self):
        self.d.check("S", 999.0, "dairy")
        stats = self.d.get_stats()
        stats["total_anomalies"] = 9999
        assert self.d.get_stats()["total_anomalies"] == 1

    def test_per_layer_counters(self):
        self.d.check("S", 999.0, "dairy")
        s = self.d.get_stats()
        assert s["l1_bounds"] == 1
        assert s["total_anomalies"] == 1

    def test_max_rate_constant_is_per_second(self):
        # Documents the units, which is what the previous bug got wrong.
        assert 0 < MAX_RATE_C_PER_SEC < 1.0
