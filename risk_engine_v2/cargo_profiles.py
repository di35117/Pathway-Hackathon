"""
cargo_profiles.py — Load and query per-cargo risk configuration.

Each cargo type (vaccines, seafood, dairy, frozen_meat) has specific
temperature tolerances, risk factor weights, and economic values.
"""

import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "cargo_profiles.json")
_profiles = None


def _load_profiles():
    global _profiles
    if _profiles is not None:
        return _profiles
    with open(_CONFIG_PATH, "r") as f:
        _profiles = json.load(f)
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


def list_cargo_types():
    """Return list of all available cargo type keys."""
    profiles = _load_profiles()
    return list(profiles.keys())
