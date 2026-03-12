"""
traffic_model.py — Speed variation by road type and time of day.

Reads traffic_bands.json for configurable speed factors.
"""

import json
import os
from datetime import datetime, timezone, timedelta

_IST = timezone(timedelta(hours=5, minutes=30))

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "traffic_bands.json")
_config = None


def _load_config():
    global _config
    if _config is not None:
        return _config
    with open(_CONFIG_PATH, "r") as f:
        _config = json.load(f)
    return _config


def _time_to_minutes(time_str):
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _is_in_range(current_min, start_str, end_str):
    """Check if current time (minutes) falls within a range."""
    s = _time_to_minutes(start_str)
    e = _time_to_minutes(end_str)
    if s <= e:
        return s <= current_min <= e
    else:  # wraps midnight
        return current_min >= s or current_min <= e


def get_time_factor(hour_of_day, minute_of_day=0):
    """
    Return the speed multiplier for a given time.
    - Peak hours → reduced speed (factor < 1)
    - Night hours → slightly faster (factor > 1 on highways)
    - Off-peak → normal (factor = 1)
    """
    cfg = _load_config()
    current_min = hour_of_day * 60 + minute_of_day

    # Check peak hours
    for band in cfg.get("peak_hours", []):
        if _is_in_range(current_min, band["start"], band["end"]):
            return "peak"

    # Check night hours
    night = cfg.get("night_hours", {})
    if night and _is_in_range(current_min, night["start"], night["end"]):
        return "night"

    return "off_peak"


def get_speed(road_class, hour_of_day=None, minute=0):
    """
    Return the effective speed in km/h for the given road class and time.

    Parameters
    ----------
    road_class : str
        One of 'highway', 'state_road', 'city', 'industrial'.
    hour_of_day : int or None
        Hour in IST (0-23). If None, uses current IST time.
    minute : int
        Minute of the hour (0-59).

    Returns
    -------
    float  Speed in km/h.
    """
    cfg = _load_config()

    if hour_of_day is None:
        now = datetime.now(_IST)
        hour_of_day = now.hour
        minute = now.minute

    road_cfg = cfg["road_classes"].get(road_class)
    if road_cfg is None:
        # Default to state_road for unknown classes
        road_cfg = cfg["road_classes"]["state_road"]

    baseline = road_cfg["baseline_speed_kmh"]

    time_band = get_time_factor(hour_of_day, minute)
    factor_key = f"{time_band}_factor"
    factor = road_cfg.get(factor_key, 1.0)

    return round(baseline * factor, 1)


def get_road_class_info():
    """Return all road class configurations."""
    cfg = _load_config()
    return cfg["road_classes"]
