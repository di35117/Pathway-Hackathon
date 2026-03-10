"""
test_simulation_v2.py — Tests for Simulation Engine V2 modules.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from simulation_v2.gps_simulator_v2 import TruckState, haversine_distance, interpolate_point
from simulation_v2.traffic_model import get_speed, get_time_factor
from simulation_v2.door_event_sim import DoorEventSimulator, generate_door_event
from simulation_v2.driver_behavior import StopScheduler


# ── Haversine tests ──────────────────────────────────────────────────────────

class TestHaversine:
    def test_same_point_is_zero(self):
        d = haversine_distance(28.7041, 77.1025, 28.7041, 77.1025)
        assert d == 0.0

    def test_delhi_to_jaipur_approx(self):
        # ~260 km straight line
        d = haversine_distance(28.7041, 77.1025, 26.9124, 75.7873)
        assert 230_000 < d < 300_000  # metres

    def test_short_distance(self):
        d = haversine_distance(28.7041, 77.1025, 28.7051, 77.1035)
        assert 0 < d < 500  # should be < 500 metres


# ── TruckState tests ─────────────────────────────────────────────────────────

class TestTruckState:
    @pytest.fixture
    def simple_polyline(self):
        return [
            {"lat": 28.0, "lng": 77.0, "road_class": "city"},
            {"lat": 28.1, "lng": 77.1, "road_class": "highway"},
            {"lat": 28.2, "lng": 77.2, "road_class": "highway"},
            {"lat": 28.3, "lng": 77.3, "road_class": "state_road"},
        ]

    def test_initial_position(self, simple_polyline):
        ts = TruckState(simple_polyline)
        pos = ts.get_position()
        assert pos["lat"] == 28.0
        assert pos["lng"] == 77.0
        assert not ts.finished

    def test_advance_moves_forward(self, simple_polyline):
        ts = TruckState(simple_polyline)
        pos1 = ts.get_position()
        ts.advance(10, 60)  # 10 seconds at 60 km/h
        pos2 = ts.get_position()
        assert pos2["lat"] != pos1["lat"] or pos2["lng"] != pos1["lng"]

    def test_progress_increases(self, simple_polyline):
        ts = TruckState(simple_polyline)
        assert ts.progress_fraction == 0.0
        ts.advance(100, 80)
        assert ts.progress_fraction > 0.0

    def test_remaining_distance_decreases(self, simple_polyline):
        ts = TruckState(simple_polyline)
        d1 = ts.remaining_distance_km()
        ts.advance(100, 80)
        d2 = ts.remaining_distance_km()
        assert d2 < d1

    def test_reaches_end(self, simple_polyline):
        ts = TruckState(simple_polyline)
        # Advance a lot
        for _ in range(1000):
            ts.advance(60, 120)
        assert ts.finished
        assert ts.remaining_distance_km() == 0

    def test_invalid_polyline(self):
        with pytest.raises(ValueError):
            TruckState([{"lat": 28.0, "lng": 77.0}])  # only 1 point


# ── Traffic model tests ──────────────────────────────────────────────────────

class TestTrafficModel:
    def test_highway_off_peak(self):
        speed = get_speed("highway", hour_of_day=14, minute=0)
        assert speed == 65.0  # baseline × 1.0

    def test_highway_peak(self):
        speed = get_speed("highway", hour_of_day=9, minute=0)
        assert speed == pytest.approx(65 * 0.65, rel=0.01)

    def test_highway_night(self):
        speed = get_speed("highway", hour_of_day=23, minute=0)
        assert speed == pytest.approx(65 * 1.10, rel=0.01)

    def test_city_peak(self):
        speed = get_speed("city", hour_of_day=18, minute=0)
        assert speed == pytest.approx(30 * 0.45, rel=0.01)

    def test_unknown_road_class(self):
        speed = get_speed("unknown_road", hour_of_day=14, minute=0)
        assert speed > 0  # should fallback to state_road

    def test_time_factor_types(self):
        assert get_time_factor(9) == "peak"
        assert get_time_factor(14) == "off_peak"
        assert get_time_factor(23) == "night"


# ── Door event tests ─────────────────────────────────────────────────────────

class TestDoorEvents:
    def test_loading_generates_events(self):
        result = generate_door_event("loading_unloading")
        assert result is not None
        assert result["num_events"] >= 2

    def test_checkpoint_generates_one_event(self):
        result = generate_door_event("warehouse_checkpoint")
        assert result is not None
        assert result["num_events"] == 1

    def test_unknown_stop_returns_none(self):
        result = generate_door_event("unknown_stop")
        assert result is None

    def test_simulator_starts_closed(self):
        sim = DoorEventSimulator()
        state = sim.update(2, is_stopped=False)
        assert state["door_status"] == "CLOSED"

    def test_simulator_opens_on_stop(self):
        sim = DoorEventSimulator()
        sim.on_stop_start("loading_unloading")
        # Run enough ticks to get past the gap
        opened = False
        for _ in range(50):
            state = sim.update(2, is_stopped=True)
            if state["door_status"] == "OPEN":
                opened = True
                break
        assert opened


# ── Stop scheduler tests ─────────────────────────────────────────────────────

class TestStopScheduler:
    def test_first_stop_is_loading(self):
        scheduler = StopScheduler("TEST-001")
        stop = scheduler.update(2, 0)
        assert stop is not None
        assert stop["type"] == "loading_unloading"

    def test_stop_eventually_ends(self):
        scheduler = StopScheduler("TEST-002")
        stop = scheduler.update(2, 0)  # triggers loading
        assert stop is not None

        # Keep ticking until stop ends
        ended = False
        for _ in range(5000):
            stop = scheduler.update(2, 0.01)
            if stop is None:
                ended = True
                break
        assert ended
