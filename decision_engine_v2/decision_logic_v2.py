"""
decision_logic_v2.py — Diversion trigger and action emitter.

Receives risk assessment, computes economic outcome, and emits:
  - DIVERT with selected hub
  - MONITOR_CLOSELY with alert
  - CONTINUE

Integrates with existing hub optimizer for hub selection.
"""

import logging

from decision_engine_v2.economic_model import (
    calculate_expected_loss,
    calculate_diversion_cost,
    should_divert,
)
from decision_engine_v2.confidence_scorer import score_confidence
from decision_engine_v2.diversion_selector_v2 import choose_diversion_store
from risk_engine_v2.cargo_profiles import get_default_routing_mode

logger = logging.getLogger(__name__)

# Track signal duration per shipment
_signal_duration = {}  # shipment_id → seconds at current risk level
_last_risk_level = {}  # shipment_id → last risk level


def _update_signal_duration(shipment_id, risk_level, delta_t=2.0):
    """Track how long a risk level has been consistent."""
    last = _last_risk_level.get(shipment_id)
    if last == risk_level:
        _signal_duration[shipment_id] = _signal_duration.get(shipment_id, 0) + delta_t
    else:
        _signal_duration[shipment_id] = 0
        _last_risk_level[shipment_id] = risk_level
    return _signal_duration[shipment_id]


def _resolve_routing_mode(shipment, risk_assessment):
    """
    Explicit per-shipment override wins; otherwise fall back to the cargo's
    default from cargo_profiles.json (SAFETY for vaccines, ECO for produce).
    """
    mode = shipment.get("routing_mode")
    if mode:
        mode = str(mode).upper()
        if mode in ("SAFETY", "BALANCED", "ECO"):
            return mode

    cargo = (shipment.get("product_type")
             or risk_assessment.get("cargo_type")
             or "dairy")
    return get_default_routing_mode(cargo)


def decide_v2(risk_assessment, shipment, hub_selector=None, delta_t=2.0,
              data_staleness_sec=None, stores=None):
    """
    Make a diversion decision based on risk assessment and economics.

    Parameters
    ----------
    risk_assessment : dict
        Output from risk_calculator_v2.assess_risk_v2().
    shipment : dict
        Shipment data including cargo_value_inr, nearest_hub_distance_km.
    hub_selector : callable or None
        Optional hub selection function. If None, uses default distance.
    delta_t : float
        Tick interval in seconds (used for signal duration tracking).
    data_staleness_sec : float or None
        Seconds since last telemetry. Defaults to delta_t if None.
    stores : list[dict] or None
        Optional cold-store candidates for capacity-aware diversion selection.

    Returns
    -------
    dict  Decision output matching the V2 schema.
    """
    sid = risk_assessment["shipment_id"]
    risk_prob = risk_assessment["risk_probability"]
    risk_level = risk_assessment["risk_level"]
    factor_scores = risk_assessment["factor_scores"]

    cargo_value = shipment.get("cargo_value_inr", 0)
    hub_distance = shipment.get("nearest_hub_distance_km", 30)

    if data_staleness_sec is None:
        data_staleness_sec = delta_t

    # --- Signal duration tracking ---
    signal_dur = _update_signal_duration(sid, risk_level, delta_t=delta_t)

    # --- Confidence assessment ---
    conf = score_confidence(
        factor_scores,
        signal_duration_sec=signal_dur,
        data_staleness_sec=data_staleness_sec,
        risk_level=risk_level,
    )

    # --- Economic calculations ---
    expected_loss = calculate_expected_loss(risk_prob, cargo_value)

    # Call existing hub optimizer if available
    hub_name = "Nearest Cold Hub"
    hub_eta = round(hub_distance / 40 * 60, 0)  # rough ETA at 40 km/h
    selected_store = None

    if hub_selector:
        try:
            hub_result = hub_selector({
                "shipment_id": sid,
                "risk_probability": risk_prob,
                "value_inr": cargo_value,
                "nearest_hub_distance_km": hub_distance,
                "objective_mode": "cost",
            })
            if isinstance(hub_result, dict):
                hub_name = hub_result.get("hub_name", hub_name)
                hub_distance = hub_result.get("nearest_hub_distance_km", hub_distance)
                hub_eta = round(hub_distance / 40 * 60, 0)
        except Exception as exc:
            logger.warning("Hub selector failed for %s: %s", sid, exc)

    # Prefer explicit store selection when store candidates are provided.
    if stores:
        diversion_choice = choose_diversion_store(shipment, stores, risk_prob)
        if diversion_choice:
            selected_store = diversion_choice["store"]
            hub_name = (selected_store.get("name")
                        or selected_store.get("id")
                        or hub_name)
            hub_distance = diversion_choice["dist_km"]
            hub_eta = round(hub_distance / 40 * 60, 0)

    diversion = calculate_diversion_cost(hub_distance, risk_prob, cargo_value)

    routing_mode = _resolve_routing_mode(shipment, risk_assessment)
    divert_check = should_divert(
        expected_loss,
        diversion["total_cost"],
        routing_mode=routing_mode,
        risk_probability=risk_prob,
        co2_delta_kg=diversion["co2_delta_kg"],
    )

    # --- Decision logic ---
    # LOW risk always continues, in every mode. This is a sanity floor, not an
    # optimisation: for valuable cargo the economic rule alone would fire even at
    # 10% risk, because 10% of a 25 lakh consignment still exceeds a detour's
    # cost. SAFETY's own trigger sits at 55%, well above the LOW band ceiling of
    # 35%, so this gate never suppresses a safety-mode diversion.
    if risk_level == "LOW":
        action = "CONTINUE"
        reason = "Risk within acceptable limits"
    elif divert_check["should_divert"]:
        action = "DIVERT"
        reason = _build_divert_reason(risk_assessment)
    elif risk_level == "HIGH":
        action = "MONITOR_CLOSELY"
        if divert_check["margin_pct"] <= divert_check.get("monitor_margin_threshold", 0.15):
            reason = (f"Risk HIGH but costs within {divert_check['margin_pct']*100:.0f}% — "
                      f"monitoring before committing to diversion")
        else:
            reason = (f"Risk HIGH but diversion not justified under {routing_mode} — "
                      f"{divert_check['mode_rule']}")
    elif risk_level == "MEDIUM" and risk_prob > 0.55:
        action = "MONITOR_CLOSELY"
        reason = "Elevated risk trending upward — close monitoring"
    else:
        action = "CONTINUE"
        reason = "Risk acceptable, continuing delivery"

    return {
        "shipment_id": sid,
        "action": action,
        "confidence": conf["confidence"],
        "confidence_reason": conf["reason"],
        "expected_loss_continue": round(expected_loss, 2),
        "total_diversion_cost": round(diversion["total_cost"], 2),
        "saving": round(divert_check["saving"], 2),
        "selected_hub": hub_name,
        "selected_store_id": selected_store.get("id") if selected_store else None,
        "selected_store_distance_km": round(hub_distance, 2),
        "hub_eta_min": int(hub_eta),
        "co2_delta_kg": diversion["co2_delta_kg"],
        "divert_reason": reason,
        "risk_probability": risk_prob,
        "risk_level": risk_level,
        "routing_mode": routing_mode,
        "mode_rule": divert_check["mode_rule"],
        "fuel_cost_inr": diversion["fuel_cost"],
        "hub_cost_inr": diversion["hub_cost"],
        "residual_loss_inr": diversion["residual_loss"],
    }


def _build_divert_reason(risk_assessment):
    """Build a human-readable diversion reason from top risk factors."""
    factors = risk_assessment["factor_scores"]
    top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)

    elevated = [name.replace("_", " ") for name, score in top_factors
                if score > 0.3][:3]

    if elevated:
        factor_str = " + ".join(elevated)
        duration = ""
        exp_min = risk_assessment.get("exposure_minutes", 0)
        if exp_min > 1:
            duration = f" sustained > {exp_min:.0f} min"
        return f"{factor_str.capitalize()}{duration}"

    return "Multiple risk factors elevated"


def reset_tracking(shipment_id=None):
    """Reset signal duration tracking. Pass shipment_id to clean up a single shipment."""
    global _signal_duration, _last_risk_level
    if shipment_id:
        _signal_duration.pop(shipment_id, None)
        _last_risk_level.pop(shipment_id, None)
    else:
        _signal_duration = {}
        _last_risk_level = {}
