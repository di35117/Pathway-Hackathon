"""
V1 risk model — single-factor spoilage probability.

Kept as the fallback engine (`python main.py mqtt --engine v1`). The live default
is risk_engine_v2, which fuses six signals with per-cargo weights.

Scaling note: the original form was `sigmoid(deviation * 1.8 + exposure * 0.2)`.
That saturates — at 3 C of deviation the sigmoid is already at 0.996, and every
excursion beyond it scores 1.0, which makes the "probability" a step function.

The fix is to normalise the inputs into a bounded score before the sigmoid, so
the curve spans the range that actually matters operationally:

    deviation_score = min(deviation / DEVIATION_SCALE, 1.5)
    exposure_score  = min(exposure  / EXPOSURE_SCALE,  1.0)
    raw             = W_DEV * deviation_score + W_EXP * exposure_score
    risk            = sigmoid(STEEPNESS * (raw * eta_factor - MIDPOINT))

With DEVIATION_SCALE = 6 C, a 1 C excursion reads ~20%, 3 C ~50%, 6 C ~85%, and
10 C ~97% — a curve that discriminates instead of pinning.
"""

import math

# Characteristic scale of an excursion, in degrees. At this deviation the
# smooth-saturating term reaches ~63% of its ceiling.
DEVIATION_SCALE = 6.0
DEVIATION_CEILING = 1.6
# Characteristic scale of cumulative exposure, in minutes.
EXPOSURE_SCALE = 45.0
EXPOSURE_CEILING = 1.0

W_DEVIATION = 0.75   # instantaneous severity dominates
W_EXPOSURE = 0.45    # cumulative damage contributes but cannot alone saturate

STEEPNESS = 5.0      # logistic gain
MIDPOINT = 0.45      # normalised score at which risk = 50%

BASELINE_RISK = 0.05  # never report zero risk; the model is not certain

LOW_BAND = 0.35
MEDIUM_BAND = 0.65


def sigmoid(x: float) -> float:
    """Logistic function, overflow-safe at both tails."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x)) if x < 700 else 1.0
    e = math.exp(x) if x > -700 else 0.0
    return e / (1.0 + e)


def compute_risk(shipment_state: dict) -> dict:
    temp = shipment_state.get("temp", 0)
    safe_min = shipment_state.get("safe_min_temp", 2)
    safe_max = shipment_state.get("safe_max_temp", 8)
    exposure_minutes = shipment_state.get("exposure_minutes", 0) or 0
    eta_minutes = shipment_state.get("eta_minutes_remaining", 300) or 0

    if temp is None:
        return {"risk_probability": BASELINE_RISK, "risk_score_raw": 0.0,
                "risk_level": "LOW"}

    # One-sided distance outside the safe band; anywhere inside is equally fine.
    if temp > safe_max:
        deviation = temp - safe_max
    elif temp < safe_min:
        deviation = safe_min - temp
    else:
        deviation = 0.0

    # In range with no accumulated exposure: baseline only.
    if deviation == 0 and exposure_minutes <= 0:
        return {"risk_probability": BASELINE_RISK, "risk_score_raw": 0.0,
                "risk_level": "LOW"}

    # Normalise both inputs before combining, so neither can drive the sigmoid
    # into its asymptote on its own. The deviation term saturates smoothly
    # (asymptotic to DEVIATION_CEILING) rather than being hard-clipped, so risk
    # stays strictly increasing in deviation while never reaching certainty.
    deviation_score = DEVIATION_CEILING * (
        1.0 - math.exp(-deviation / DEVIATION_SCALE)
    )
    exposure_score = EXPOSURE_CEILING * (
        1.0 - math.exp(-exposure_minutes / EXPOSURE_SCALE)
    )

    raw_score = W_DEVIATION * deviation_score + W_EXPOSURE * exposure_score

    # More journey remaining means more time for damage to accumulate.
    eta_factor = min(max(eta_minutes, 0) / 300.0, 1.5) if deviation > 0 else 1.0
    eta_factor = max(eta_factor, 0.6)  # floor: arrival is imminent, not harmless

    adjusted = raw_score * eta_factor
    risk_probability = sigmoid(STEEPNESS * (adjusted - MIDPOINT))
    risk_probability = max(risk_probability, BASELINE_RISK)

    if risk_probability < LOW_BAND:
        risk_level = "LOW"
    elif risk_probability < MEDIUM_BAND:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    return {
        "risk_probability": round(risk_probability, 3),
        "risk_score_raw": round(adjusted, 3),
        "risk_level": risk_level,
    }
