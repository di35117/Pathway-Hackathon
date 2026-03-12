"""
driver_behavior.py — Simulates realistic Indian truck driver stop patterns.

Manages tea breaks, fuel stops, lunch breaks, loading/unloading,
and warehouse checkpoints with configurable schedules.
"""

import json
import os
import random
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "stops.json")
_config = None


def _load_config():
    global _config
    if _config is not None:
        return _config
    with open(_CONFIG_PATH, "r") as f:
        _config = json.load(f)
    return _config


class StopScheduler:
    """
    Determines when a truck should stop based on elapsed time,
    distance covered, and time of day.

    State tracked per truck:
    - hours since last tea break
    - km since last fuel stop
    - whether lunch was taken today
    - loading/unloading done at origin
    """

    def __init__(self, shipment_id, start_time=None):
        self.shipment_id = shipment_id
        self.start_time = start_time or datetime.now(_IST)
        self.config = _load_config()["stop_rules"]

        # Internal state
        self._hours_since_tea = 0.0
        self._km_since_fuel = 0.0
        self._lunch_taken_today = False
        self._loading_done = False
        self._current_stop = None       # active stop dict or None
        self._stop_remaining_sec = 0.0  # seconds left in current stop
        self._last_date = self.start_time.date()

        # Pre-compute next break thresholds (fixed per cycle, not per tick)
        tea_rule = self.config["tea_break"]
        self._next_tea_interval = random.uniform(
            tea_rule["interval_hours_min"], tea_rule["interval_hours_max"])
        fuel_rule = self.config["fuel_stop"]
        self._next_fuel_interval = random.uniform(
            fuel_rule["interval_km_min"], fuel_rule["interval_km_max"])

    def _random_duration(self, stop_type):
        """Return random duration in seconds for a stop type."""
        rule = self.config.get(stop_type, {})
        lo = rule.get("duration_minutes_min", 15)
        hi = rule.get("duration_minutes_max", 30)
        return random.randint(lo, hi) * 60

    @property
    def is_stopped(self):
        return self._current_stop is not None

    @property
    def current_stop_type(self):
        if self._current_stop:
            return self._current_stop["type"]
        return None

    @property
    def current_stop_label(self):
        if self._current_stop:
            return self._current_stop.get("label", self._current_stop["type"])
        return None

    def update(self, delta_t_seconds, distance_delta_km, current_time=None):
        """
        Advance the scheduler by one tick.

        Parameters
        ----------
        delta_t_seconds : float
            Simulation tick duration in seconds.
        distance_delta_km : float
            Distance covered this tick in km.
        current_time : datetime or None
            Current simulation time. Uses real time if None.

        Returns
        -------
        dict or None
            If a stop is active: {"type", "label", "remaining_sec", "driver_state"}
            If no stop: None
        """
        if current_time is None:
            current_time = datetime.now(_IST)

        # Reset lunch flag on new day
        if current_time.date() != self._last_date:
            self._lunch_taken_today = False
            self._last_date = current_time.date()

        # If currently in a stop, count down
        if self._current_stop is not None:
            self._stop_remaining_sec -= delta_t_seconds
            if self._stop_remaining_sec <= 0:
                # Stop finished
                finished_stop = self._current_stop
                self._current_stop = None
                self._stop_remaining_sec = 0
                return None
            return {
                "type": self._current_stop["type"],
                "label": self._current_stop.get("label", ""),
                "remaining_sec": round(self._stop_remaining_sec, 1),
                "driver_state": "IDLE",
            }

        # Accumulate driving counters
        self._hours_since_tea += delta_t_seconds / 3600
        self._km_since_fuel += distance_delta_km

        # --- Check if any stop should trigger ---

        # 1. Loading at origin (first stop)
        if not self._loading_done:
            self._loading_done = True
            duration = self._random_duration("loading_unloading")
            self._current_stop = {
                "type": "loading_unloading",
                "label": self.config["loading_unloading"]["label"],
            }
            self._stop_remaining_sec = duration
            return {
                "type": "loading_unloading",
                "label": self._current_stop["label"],
                "remaining_sec": duration,
                "driver_state": "IDLE",
            }

        # 2. Lunch break
        hour = current_time.hour
        minute = current_time.minute
        current_total_min = hour * 60 + minute
        lunch_start = 12 * 60 + 30  # 12:30
        lunch_end = 14 * 60         # 14:00
        if (not self._lunch_taken_today
                and lunch_start <= current_total_min <= lunch_end):
            self._lunch_taken_today = True
            self._hours_since_tea = 0  # lunch counts as rest
            duration = self._random_duration("lunch_break")
            self._current_stop = {
                "type": "lunch_break",
                "label": self.config["lunch_break"]["label"],
            }
            self._stop_remaining_sec = duration
            return {
                "type": "lunch_break",
                "label": self._current_stop["label"],
                "remaining_sec": duration,
                "driver_state": "IDLE",
            }

        # 3. Tea break (every 2-3 hours)
        tea_rule = self.config["tea_break"]
        if self._hours_since_tea >= self._next_tea_interval:
            self._hours_since_tea = 0
            # Re-randomize the next tea break threshold
            self._next_tea_interval = random.uniform(
                tea_rule["interval_hours_min"], tea_rule["interval_hours_max"])
            duration = self._random_duration("tea_break")
            self._current_stop = {
                "type": "tea_break",
                "label": tea_rule["label"],
            }
            self._stop_remaining_sec = duration
            return {
                "type": "tea_break",
                "label": self._current_stop["label"],
                "remaining_sec": duration,
                "driver_state": "IDLE",
            }

        # 4. Fuel stop (every 300-400 km)
        fuel_rule = self.config["fuel_stop"]
        if self._km_since_fuel >= self._next_fuel_interval:
            self._km_since_fuel = 0
            # Re-randomize the next fuel stop threshold
            self._next_fuel_interval = random.uniform(
                fuel_rule["interval_km_min"], fuel_rule["interval_km_max"])
            duration = self._random_duration("fuel_stop")
            self._current_stop = {
                "type": "fuel_stop",
                "label": fuel_rule["label"],
            }
            self._stop_remaining_sec = duration
            return {
                "type": "fuel_stop",
                "label": self._current_stop["label"],
                "remaining_sec": duration,
                "driver_state": "IDLE",
            }

        return None
