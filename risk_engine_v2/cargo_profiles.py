"""
cargo_profiles.py — Load and query per-cargo risk configuration.

Each of the 9 cargo types carries risk-factor weights, exposure tolerance and
economics in configs/cargo_profiles.json.

Temperature ranges are NOT owned here. They are overlaid from the SOP document
(core.sop_parser) on load, so the SOP stays the single source of truth for what
"safe" means — editing the SOP changes the risk model's thresholds. The JSON
ranges act as a fallback for when the SOP cannot be read.
"""

import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "cargo_profiles.json")
_profiles = None
_sop_mtime = None


def _sop_overlay(profiles):
    """Replace ideal_temp_min/max with the SOP's values where the SOP has them."""
    try:
        from core.sop_parser import get_product_temp_ranges
    except ImportError:
        return profiles

    ranges = get_product_temp_ranges()
    # SOP keys are 'Frozen_Meat'; profile keys are 'frozen_meat'.
    normalised = {name.lower().replace(" ", "_"): rng for name, rng in ranges.items()}

    for key, profile in profiles.items():
        if key in normalised:
            safe_min, safe_max = normalised[key]
            profile["ideal_temp_min"] = safe_min
            profile["ideal_temp_max"] = safe_max
            profile["temp_range_source"] = "sop"
        else:
            profile["temp_range_source"] = "config"
    return profiles


def _load_profiles():
    """Load profiles, reloading if the SOP changed since last time."""
    global _profiles, _sop_mtime

    try:
        from core.sop_parser import SOP_PATH
        current_mtime = os.path.getmtime(SOP_PATH)
    except (ImportError, OSError):
        current_mtime = None

    if _profiles is not None and _sop_mtime == current_mtime:
        return _profiles

    with open(_CONFIG_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    _profiles = _sop_overlay(profiles)
    _sop_mtime = current_mtime
    return _profiles


def load_cargo_profile(cargo_type):
    """
    Return the full profile dict for a cargo type.

    Parameters
    ----------
    cargo_type : str
        One of 'vaccines', 'seafood', 'dairy', 'frozen_meat'.
        Also accepts V1-style names like 'Vaccines', 'Frozen_Meat'.

    Returns
    -------
    dict  Profile with keys: label, ideal_temp_min, ideal_temp_max,
          max_exposure_minutes, weights, cargo_value_per_kg,
          spoilage_rate_per_minute.
    """
    profiles = _load_profiles()
    # Normalise key: lowercase, underscores
    key = cargo_type.lower().replace(" ", "_")
    if key in profiles:
        return profiles[key]

    raise KeyError(
        f"Unknown cargo type '{cargo_type}' (normalised: '{key}'). "
        f"Available types: {list(profiles.keys())}"
    )


def get_temp_range(cargo_type):
    """Return (min, max) ideal temperature for cargo type."""
    p = load_cargo_profile(cargo_type)
    return p["ideal_temp_min"], p["ideal_temp_max"]


def get_weights(cargo_type):
    """Return the risk factor weights dict for cargo type."""
    p = load_cargo_profile(cargo_type)
    return p["weights"]


def get_max_exposure(cargo_type):
    """Return maximum safe exposure time in minutes."""
    p = load_cargo_profile(cargo_type)
    return p["max_exposure_minutes"]


def get_default_routing_mode(cargo_type):
    """
    SAFETY / BALANCED / ECO default for this cargo.

    Vaccines and pharma default to SAFETY, produce and flowers to ECO, the rest
    to BALANCED. Operators can still override per shipment at runtime.
    """
    try:
        return load_cargo_profile(cargo_type).get("routing_mode", "BALANCED")
    except KeyError:
        return "BALANCED"


def get_degree_hour_midpoint(cargo_type):
    """
    Cumulative degree-hours at which spoilage probability crosses 50%.

    Vaccines cross at 2 °C·h, frozen meat at 20 — the same tolerance ordering as
    max_exposure_minutes, applied to the irreversible-damage track.
    """
    try:
        return float(load_cargo_profile(cargo_type).get("degree_hour_midpoint", 20.0))
    except KeyError:
        return 20.0


def list_cargo_types():
    """Return list of all available cargo type keys."""
    profiles = _load_profiles()
    return list(profiles.keys())
