"""
door_event_sim.py — Context-aware door event simulation.

Door events are triggered based on stop type rather than random chance,
producing realistic open durations and frequencies.
"""

import random

# Door event rules per stop type
_DOOR_RULES = {
    "loading_unloading": {
        "num_events_min": 2,
        "num_events_max": 4,
        "open_duration_sec_min": 120,   # 2 minutes
        "open_duration_sec_max": 480,   # 8 minutes
    },
    "warehouse_checkpoint": {
        "num_events_min": 1,
        "num_events_max": 1,
        "open_duration_sec_min": 60,    # 1 minute
        "open_duration_sec_max": 180,   # 3 minutes
    },
    "tea_break": {
        "num_events_min": 0,
        "num_events_max": 1,
        "open_duration_sec_min": 30,    # 30 seconds
        "open_duration_sec_max": 90,    # 90 seconds
    },
    "fuel_stop": {
        "num_events_min": 0,
        "num_events_max": 1,
        "open_duration_sec_min": 30,
        "open_duration_sec_max": 60,
    },
    "lunch_break": {
        "num_events_min": 0,
        "num_events_max": 1,
        "open_duration_sec_min": 30,
        "open_duration_sec_max": 90,
    },
}

# Roadside check: rare event while driving
ROADSIDE_CHECK_PROB_PER_HOUR = 0.05
ROADSIDE_CHECK_OPEN_SEC_MIN = 120   # 2 minutes
ROADSIDE_CHECK_OPEN_SEC_MAX = 300   # 5 minutes


class DoorEventSimulator:
    """
    Generates context-aware door open/close events for a single truck.

    State
    -----
    is_open : bool
        Whether the door is currently open.
    open_elapsed_sec : float
        How long the door has been continuously open.
    total_open_sec : float
        Cumulative open time across all events (for risk engine).
    """

    def __init__(self):
        self.is_open = False
        self.open_elapsed_sec = 0.0
        self.total_open_sec = 0.0
        self._pending_events = []  # list of durations to play out
        self._current_event_duration = 0.0
        self._gap_remaining = 0.0  # gap between events during a stop

    def _schedule_events(self, stop_type):
        """Queue up door events for a new stop."""
        rules = _DOOR_RULES.get(stop_type)
        if not rules:
            return

        count = random.randint(rules["num_events_min"], rules["num_events_max"])
        self._pending_events = []
        for _ in range(count):
            dur = random.randint(rules["open_duration_sec_min"],
                                 rules["open_duration_sec_max"])
            self._pending_events.append(dur)

    def on_stop_start(self, stop_type):
        """Called when a truck begins a new stop."""
        self._schedule_events(stop_type)
        # Small delay before first door opens
        self._gap_remaining = random.uniform(10, 30)

    def update(self, delta_t_seconds, is_stopped, driving_hours=0):
        """
        Advance the door simulation by one tick.

        Parameters
        ----------
        delta_t_seconds : float
            Time step in seconds.
        is_stopped : bool
            Whether the truck is currently stopped.
        driving_hours : float
            Total driving hours (scales roadside check probability).

        Returns
        -------
        dict
            {"door_status": "OPEN"/"CLOSED",
             "door_open_sec": float,
             "event_type": str or None}
        """
        event_type = None

        # Handle door currently open
        if self.is_open:
            self.open_elapsed_sec += delta_t_seconds
            self.total_open_sec += delta_t_seconds

            if self.open_elapsed_sec >= self._current_event_duration:
                # Door closes this tick
                self.is_open = False
                event_type = "door_close"
                self.open_elapsed_sec = 0.0
                self._current_event_duration = 0.0
                # Gap before next event at stop
                self._gap_remaining = random.uniform(15, 60)

                return {
                    "door_status": "CLOSED",
                    "door_open_sec": 0,
                    "event_type": event_type,
                }

            return {
                "door_status": "OPEN",
                "door_open_sec": round(self.open_elapsed_sec, 1),
                "event_type": event_type,
            }

        # Door is closed — check if we should open it
        if is_stopped and self._pending_events:
            self._gap_remaining -= delta_t_seconds
            if self._gap_remaining <= 0:
                # Open door for next queued event
                self._current_event_duration = self._pending_events.pop(0)
                self.is_open = True
                self.open_elapsed_sec = 0.0
                event_type = "door_open"
                return {
                    "door_status": "OPEN",
                    "door_open_sec": 0.0,
                    "event_type": event_type,
                }

        # Random roadside check while driving (probability scales with driving hours)
        if not is_stopped and delta_t_seconds > 0:
            hour_scale = min(2.0, 1.0 + driving_hours / 10.0)
            prob = ROADSIDE_CHECK_PROB_PER_HOUR * hour_scale * (delta_t_seconds / 3600)
            if random.random() < prob:
                self._current_event_duration = random.randint(
                    ROADSIDE_CHECK_OPEN_SEC_MIN, ROADSIDE_CHECK_OPEN_SEC_MAX
                )
                self.is_open = True
                self.open_elapsed_sec = 0.0
                event_type = "roadside_check"
                return {
                    "door_status": "OPEN",
                    "door_open_sec": 0.0,
                    "event_type": event_type,
                }

        return {
            "door_status": "CLOSED",
            "door_open_sec": 0,
            "event_type": None,
        }


def generate_door_event(stop_type):
    """
    Quick helper: generate a single door event dict for a given stop type.
    Returns {"num_events": int, "durations_sec": [int, ...]} or None.
    """
    rules = _DOOR_RULES.get(stop_type)
    if not rules:
        return None

    count = random.randint(rules["num_events_min"], rules["num_events_max"])
    if count == 0:
        return None

    durations = [random.randint(rules["open_duration_sec_min"],
                                rules["open_duration_sec_max"])
                 for _ in range(count)]

    return {"num_events": count, "durations_sec": durations}
