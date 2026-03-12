"""
risk_calculator_v2.py — Multi-factor cargo-aware risk assessment.

Combines six signals using cargo-specific weights:
  1. Temperature deviation
  2. Exposure time (cumulative out-of-range)
  3. ETA pressure
  4. Door event impact
  5. Compressor status
  6. Temperature drift rate

Maps the weighted sum through a sigmoid to produce risk_probability [0–1].
Thresholds: LOW < 0.35, MEDIUM 0.35–0.65, HIGH > 0.65.
"""

import math
from collections import defaultdict
from risk_engine_v2.cargo_profiles import load_cargo_profile, get_weights
from risk_engine_v2.exposure_tracker import ExposureTracker
from risk_engine_v2.drift_analyzer import DriftAnalyzer

# Module-level singletons for stateful tracking
_exposure_tracker = ExposureTracker()
_drift_analyzer = DriftAnalyzer()

# Sigmoid parameters
_SIGMOID_STEEPNESS = 4.0   # controls how sharply risk transitions
_SIGMOID_MIDPOINT = 0.55   # raw score at which probability = 0.5


# Tracks cumulative degree-hours above safe_max per shipment.
_degree_hour_state = defaultdict(float)


def compute_exposure_increment(temp_c, safe_max_c, dt_hours):
    """Return degree-hour increment above safe_max for a time interval."""
    if dt_hours <= 0 or temp_c <= safe_max_c:
        return 0.0
    return (temp_c - safe_max_c) * dt_hours


def compute_spoilage_probability(exposure_degree_hours, a=0.08, b=20.0):
    """Map cumulative degree-hours to spoilage probability with logistic curve."""
    x = a * (exposure_degree_hours - b)
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def linear_forecast(last_readings, horizon_minutes=30):
    """
    Forecast future temperature with simple least-squares linear regression.

    Parameters
    ----------
    last_readings : list[tuple[datetime, float]]
        Ordered temperature history.
    horizon_minutes : int
        Minutes ahead to forecast.

    Returns
    -------
    float or None
    """
    if not last_readings:
        return None
    if len(last_readings) == 1:
        return float(last_readings[-1][1])

    t0 = last_readings[0][0]
    xs = [max(0.0, (t - t0).total_seconds() / 60.0) for t, _ in last_readings]
    ys = [float(temp) for _, temp in last_readings]

    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))

    denom = n * sum_xx - (sum_x * sum_x)
    if abs(denom) < 1e-9:
        return float(ys[-1])

    m = (n * sum_xy - sum_x * sum_y) / denom
    c = (sum_y - m * sum_x) / n

    future_x = xs[-1] + max(0, horizon_minutes)
    return float(m * future_x + c)


def _sigmoid(x):
    """Map raw score to [0, 1] probability via logistic function."""
    z = _SIGMOID_STEEPNESS * (x - _SIGMOID_MIDPOINT)
    try:
        return 1.0 / (1.0 + math.exp(-z))
    except OverflowError:
        return 0.0 if z < 0 else 1.0


def _score_temp_deviation(temp, safe_min, safe_max):
    """
    Score temperature deviation from safe range [0, 1].
    0 = within range, 1 = severely out of range.
    """
    if safe_min <= temp <= safe_max:
        return 0.0
    if temp > safe_max:
        deviation = temp - safe_max
    else:
        deviation = safe_min - temp
    # Normalise: 5°C deviation → score 1.0
    return min(1.0, deviation / 5.0)


def _score_exposure_time(exposure_minutes, max_exposure):
    """
    Score based on fraction of maximum safe exposure consumed.
    1.0 = at or past maximum.
    """
    if max_exposure <= 0:
        return 1.0 if exposure_minutes > 0 else 0.0
    return min(1.0, exposure_minutes / max_exposure)


def _score_eta_pressure(eta_minutes, exposure_minutes, max_exposure):
    """
    Higher pressure when remaining exposure budget is thin
    relative to remaining delivery time.
    """
    if eta_minutes <= 0:
        return 0.0  # already delivered
    remaining_budget = max(0, max_exposure - exposure_minutes)
    if remaining_budget <= 0:
        return 1.0
    # Pressure = how much of remaining ETA would exhaust the budget
    pressure = min(1.0, eta_minutes / max(remaining_budget, 1))
    # Normalise: if ETA >> budget remaining, pressure → 1
    return min(1.0, pressure * 0.5)


def _score_door_events(door_status, door_open_sec):
    """
    Score door impact. Open door = immediate risk contribution,
    scaled by duration.
    """
    if door_status == "CLOSED":
        return 0.0
    # 5 minutes open → score 1.0
    return min(1.0, door_open_sec / 300.0)


def _score_compressor(compressor_status, compressor_load_pct=None):
    """
    Score compressor health signal.
    OFF = high risk, low load = moderate risk.
    """
    if compressor_status == "OFF":
        return 1.0
    if compressor_load_pct is not None:
        # Very high load (>95%) suggests struggling
        if compressor_load_pct > 95:
            return 0.6
        # Normal operation
        return max(0.0, 1.0 - compressor_load_pct / 100.0) * 0.3
    return 0.0


def _score_drift_rate(drift_rate_c_min):
    """
    Score temperature drift rate.
    0.5 °C/min = critical, maps to 1.0.
    """
    if drift_rate_c_min <= 0:
        return 0.0
    return min(1.0, drift_rate_c_min / 0.5)


def assess_risk_v2(telemetry, cargo_type=None, delta_t_seconds=2.0):
    """
    Perform a full multi-factor risk assessment on a telemetry event.

    Parameters
    ----------
    telemetry : dict
        Telemetry event from simulation_v2 (or compatible dict).
    cargo_type : str or None
        Cargo type override. If None, reads from telemetry.
    delta_t_seconds : float
        Time since last reading (for exposure/drift tracking).

    Returns
    -------
    dict  Risk assessment matching the V2 output schema.
    """
    if cargo_type is None:
        cargo_type = telemetry.get("product_type", "dairy")

    profile = load_cargo_profile(cargo_type)
    weights = get_weights(cargo_type)

    sid = telemetry.get("shipment_id")
    if not sid:
        raise ValueError("telemetry dict must contain 'shipment_id'")
    temp = telemetry.get("temperature", 0)
    safe_min = telemetry.get("safe_min_temp", profile["ideal_temp_min"])
    safe_max = telemetry.get("safe_max_temp", profile["ideal_temp_max"])

    # --- Update stateful trackers ---
    exposure_result = _exposure_tracker.update(
        sid, temp, safe_min, safe_max, delta_t_seconds
    )
    drift_result = _drift_analyzer.update(sid, temp, delta_t_seconds)

    # Degree-hours uses over-temperature severity and elapsed time.
    dt_hours = max(0.0, delta_t_seconds / 3600.0)
    degree_inc = compute_exposure_increment(temp, safe_max, dt_hours)
    _degree_hour_state[sid] += degree_inc
    degree_hours = _degree_hour_state[sid]
    spoilage_prob = compute_spoilage_probability(degree_hours)

    # --- Compute individual factor scores ---
    s_temp = _score_temp_deviation(temp, safe_min, safe_max)
    s_exposure = _score_exposure_time(
        exposure_result["exposure_minutes"],
        profile["max_exposure_minutes"]
    )
    s_eta = _score_eta_pressure(
        telemetry.get("eta_minutes_remaining", 300),
        exposure_result["exposure_minutes"],
        profile["max_exposure_minutes"]
    )
    s_door = _score_door_events(
        telemetry.get("door_status", "CLOSED"),
        telemetry.get("door_open_sec", 0)
    )

    comp = telemetry.get("compressor", {})
    s_comp = _score_compressor(
        comp.get("status", "RUNNING"),
        comp.get("load_pct")
    )
    s_drift = _score_drift_rate(drift_result["drift_rate_c_min"])

    # --- Weighted combination ---
    w = weights
    raw_score = (
        w["temp_sensitivity"] * s_temp
        + w["exposure_time"] * s_exposure
        + w["eta_pressure"] * s_eta
        + w["door_event"] * s_door
        + w["compressor"] * s_comp
        + w["drift_rate"] * s_drift
    )
    sum_weights = sum(w.values())
    normalised_score = raw_score / sum_weights if sum_weights > 0 else 0

    # Boost compressor weight if drift is critical
    if drift_result["is_critical"]:
        normalised_score = min(1.0, normalised_score * 1.3)

    # --- Sigmoid mapping ---
    risk_probability = _sigmoid(normalised_score)

    # --- Risk level thresholds ---
    if risk_probability < 0.35:
        risk_level = "LOW"
    elif risk_probability < 0.65:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "shipment_id": sid,
        "cargo_type": cargo_type.lower().replace(" ", "_"),
        "risk_probability": round(risk_probability, 4),
        "risk_level": risk_level,
        "factor_scores": {
            "temp_deviation": round(s_temp, 4),
            "exposure_time": round(s_exposure, 4),
            "eta_pressure": round(s_eta, 4),
            "door_events": round(s_door, 4),
            "compressor": round(s_comp, 4),
            "drift_rate": round(s_drift, 4),
        },
        "exposure_minutes": round(exposure_result["exposure_minutes"], 2),
        "exposure_degree_hours": round(degree_hours, 4),
        "spoilage_probability": round(spoilage_prob, 4),
        "drift_rate_c_min": drift_result["drift_rate_c_min"],
        "raw_score": round(normalised_score, 4),
    }


def reset_tracking(shipment_id=None):
    """Reset exposure and drift tracking. If shipment_id is None, resets all."""
    global _exposure_tracker, _drift_analyzer, _degree_hour_state
    if shipment_id:
        _exposure_tracker.reset(shipment_id)
        _drift_analyzer.reset(shipment_id)
        _degree_hour_state.pop(shipment_id, None)
    else:
        _exposure_tracker = ExposureTracker()
        _drift_analyzer = DriftAnalyzer()
        _degree_hour_state = defaultdict(float)
