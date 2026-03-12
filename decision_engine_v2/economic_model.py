"""
economic_model.py — Loss vs diversion cost calculation.

Compares two monetary outcomes:
  - expected_loss_continue = risk_probability × cargo_value
  - total_diversion_cost = hub_cost + residual_risk × cargo_value + fuel_penalty

Divert if: expected_loss_continue > total_diversion_cost + buffer
"""

import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "cost_config.json")
_config = None


def _load_config():
    global _config
    if _config is not None:
        return _config
    with open(_CONFIG_PATH, "r") as f:
        _config = json.load(f)
    return _config


def calculate_expected_loss(risk_probability, cargo_value):
    """
    Expected monetary loss if shipment continues without intervention.

    Parameters
    ----------
    risk_probability : float  [0, 1]
    cargo_value : float  Total cargo value in ₹

    Returns
    -------
    float  Expected loss in ₹
    """
    return risk_probability * cargo_value


def calculate_diversion_cost(hub_distance_km, risk_probability,
                              cargo_value, hub_fixed_cost=None):
    """
    Total cost of diverting to a cold hub.

    Components:
    - Fuel cost for detour
    - Hub handling fixed cost
    - Residual risk (reduced by RISK_REDUCTION_IF_DIVERT)

    Parameters
    ----------
    hub_distance_km : float
    risk_probability : float  [0, 1]
    cargo_value : float  Total cargo value in ₹
    hub_fixed_cost : float or None
        Override hub handling cost. Uses config default if None.

    Returns
    -------
    dict  {"total_cost", "fuel_cost", "hub_cost", "residual_loss", "co2_delta_kg"}
    """
    cfg = _load_config()

    fuel_cost = hub_distance_km * cfg["fuel_cost_per_km"]
    hub_cost = hub_fixed_cost if hub_fixed_cost is not None else cfg["base_hub_fixed_cost_inr"]

    reduced_risk = risk_probability * (1 - cfg["risk_reduction_if_divert"])
    residual_loss = reduced_risk * cargo_value

    co2_delta = hub_distance_km * cfg["emission_factor_kg_per_km"]

    total = fuel_cost + hub_cost + residual_loss

    return {
        "total_cost": round(total, 2),
        "fuel_cost": round(fuel_cost, 2),
        "hub_cost": round(hub_cost, 2),
        "residual_loss": round(residual_loss, 2),
        "co2_delta_kg": round(co2_delta, 2),
    }


def should_divert(expected_loss, diversion_cost):
    """
    Determine if diversion is economically justified.

    Parameters
    ----------
    expected_loss : float  Expected loss if continuing (₹)
    diversion_cost : float  Total diversion cost (₹)

    Returns
    -------
    dict  {"should_divert": bool, "saving": float, "margin_pct": float}
    """
    cfg = _load_config()
    buffer = cfg["diversion_threshold_buffer_inr"]
    monitor_margin = cfg["monitor_closely_margin_pct"]

    saving = expected_loss - diversion_cost
    threshold = diversion_cost + buffer

    should = expected_loss > threshold

    # Calculate margin for MONITOR_CLOSELY decision
    if diversion_cost > 0:
        margin_pct = abs(saving) / diversion_cost
    else:
        margin_pct = 1.0 if saving > 0 else 0.0

    return {
        "should_divert": should,
        "saving": round(saving, 2),
        "margin_pct": round(margin_pct, 4),
        "monitor_margin_threshold": monitor_margin,
        "buffer_applied": buffer,
    }
