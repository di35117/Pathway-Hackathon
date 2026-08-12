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
    with open(_CONFIG_PATH) as f:
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


def should_divert(expected_loss, diversion_cost, routing_mode="BALANCED",
                  risk_probability=0.0, co2_delta_kg=0.0):
    """
    Determine if diversion is justified under the shipment's routing mode.

    The three modes are genuinely different decision rules, not labels:

    SAFETY   — cargo integrity outranks cost. Diverts whenever risk clears
               `safety_divert_risk_threshold`, regardless of economics. Used for
               vaccines and pharmaceuticals, where a spoiled consignment is a
               patient-safety event and not merely a write-off.
    BALANCED — the expected-value rule. Divert when the loss avoided beats the
               cost of diverting, plus a buffer so a break-even call does not
               oscillate on sensor noise.
    ECO      — carbon-aware. Applies a shadow price to the detour's CO2 and
               refuses diversions whose emissions exceed `eco_co2_limit_kg`,
               unless the loss avoided is large enough to override.

    Parameters
    ----------
    expected_loss : float   Expected loss if continuing (₹)
    diversion_cost : float  Total diversion cost (₹)
    routing_mode : str      SAFETY | BALANCED | ECO
    risk_probability : float  [0, 1] — only consulted in SAFETY mode
    co2_delta_kg : float    Extra emissions from the detour — only in ECO mode

    Returns
    -------
    dict  {"should_divert", "saving", "margin_pct", "mode_rule", ...}
    """
    cfg = _load_config()
    buffer = cfg["diversion_threshold_buffer_inr"]
    monitor_margin = cfg["monitor_closely_margin_pct"]
    mode = (routing_mode or "BALANCED").upper()

    saving = expected_loss - diversion_cost
    effective_cost = diversion_cost

    # The economic rule that BALANCED uses, and that SAFETY falls back on.
    economical = expected_loss > diversion_cost + buffer

    if mode == "SAFETY":
        safety_threshold = cfg.get("safety_divert_risk_threshold", 0.55)
        risk_triggered = risk_probability >= safety_threshold
        # SAFETY is a strict superset of BALANCED: it adds a risk-only trigger
        # on top of the economic one, so it can never divert less readily than
        # BALANCED would for the same shipment.
        should = risk_triggered or economical
        if risk_triggered:
            rule = (f"SAFETY: risk {risk_probability:.0%} at or above "
                    f"{safety_threshold:.0%} threshold, cost not consulted")
        else:
            rule = (f"SAFETY: risk {risk_probability:.0%} below "
                    f"{safety_threshold:.0%}, falling back to economics "
                    f"(loss Rs {expected_loss:,.0f} vs cost Rs {diversion_cost:,.0f})")

    elif mode == "ECO":
        co2_price = cfg.get("eco_co2_shadow_price_inr_per_kg", 4000)
        co2_limit = cfg.get("eco_co2_limit_kg", 20)
        override = cfg.get("eco_override_multiplier", 3.0)

        # Price carbon into the cost side rather than bolting on a side-rule.
        effective_cost = diversion_cost + co2_delta_kg * co2_price

        if co2_delta_kg > co2_limit and expected_loss < diversion_cost * override:
            should = False
            rule = (f"ECO: {co2_delta_kg:.1f}kg CO2 exceeds {co2_limit}kg limit and "
                    f"loss avoided is under {override:g}x diversion cost")
        else:
            should = expected_loss > effective_cost + buffer
            rule = (f"ECO: loss Rs {expected_loss:,.0f} vs carbon-adjusted cost "
                    f"Rs {effective_cost:,.0f} ({co2_delta_kg:.1f}kg CO2 "
                    f"at Rs {co2_price:,.0f}/kg)")

    else:  # BALANCED
        should = economical
        rule = (f"BALANCED: loss Rs {expected_loss:,.0f} vs cost "
                f"Rs {diversion_cost:,.0f} + Rs {buffer:,.0f} buffer")

    # Margin measures how close the call was — feeds MONITOR_CLOSELY.
    if effective_cost > 0:
        margin_pct = abs(expected_loss - effective_cost) / effective_cost
    else:
        margin_pct = 1.0 if saving > 0 else 0.0

    return {
        "should_divert": should,
        "saving": round(saving, 2),
        "margin_pct": round(margin_pct, 4),
        "monitor_margin_threshold": monitor_margin,
        "buffer_applied": buffer,
        "routing_mode": mode,
        "mode_rule": rule,
        "carbon_adjusted_cost": round(effective_cost, 2),
    }
