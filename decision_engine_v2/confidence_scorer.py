"""
confidence_scorer.py — Decision confidence level assessment.

Assigns HIGH / MEDIUM / LOW confidence based on:
- Factor agreement (how many of the 6 risk factors agree)
- Signal duration (how long the pattern has been consistent)
- Data staleness (lag since last reading)
"""


def _count_agreeing_factors(factor_scores, threshold=0.3):
    """Count how many factors exceed the threshold."""
    return sum(1 for v in factor_scores.values() if v > threshold)


def _count_low_factors(factor_scores, threshold=0.15):
    """Count how many factors are below the threshold (safe)."""
    return sum(1 for v in factor_scores.values() if v < threshold)


def score_confidence(factor_scores, signal_duration_sec=0,
                     data_staleness_sec=0, risk_level="LOW"):
    """
    Assign a confidence level to a risk/decision assessment.

    Parameters
    ----------
    factor_scores : dict
        The 6 risk factor scores (each 0–1).
    signal_duration_sec : float
        How long the current risk pattern has been consistent (seconds).
    data_staleness_sec : float
        Seconds since last sensor reading.
    risk_level : str
        Current risk level ("LOW", "MEDIUM", "HIGH").

    Returns
    -------
    dict  {"confidence": str, "reason": str, "factor_agreement": int}
    """
    total_factors = len(factor_scores)

    if risk_level == "HIGH":
        agreeing = _count_agreeing_factors(factor_scores, threshold=0.3)
    elif risk_level == "LOW":
        agreeing = _count_low_factors(factor_scores, threshold=0.15)
    else:
        agreeing = _count_agreeing_factors(factor_scores, threshold=0.25)

    signal_duration_min = signal_duration_sec / 60.0

    # --- Confidence rules ---

    # Data staleness check first
    if data_staleness_sec > 30:
        return {
            "confidence": "LOW",
            "reason": f"Data stale ({data_staleness_sec:.0f}s lag)",
            "factor_agreement": agreeing,
        }

    # HIGH confidence: consistent across all/most factors for > 10 minutes
    if agreeing >= 5 and signal_duration_min >= 10:
        return {
            "confidence": "HIGH",
            "reason": (f"{agreeing}/{total_factors} factors consistent "
                       f"for {signal_duration_min:.1f} min"),
            "factor_agreement": agreeing,
        }

    # MEDIUM confidence: 3-5 factors agree, or signal < 10 minutes
    if agreeing >= 3 or (agreeing >= 2 and signal_duration_min >= 5):
        reason = f"{agreeing}/{total_factors} factors agree"
        if signal_duration_min < 10:
            reason += f", signal active {signal_duration_min:.1f} min"
        return {
            "confidence": "MEDIUM",
            "reason": reason,
            "factor_agreement": agreeing,
        }

    # LOW confidence: fewer than 3 factors agree
    return {
        "confidence": "LOW",
        "reason": f"Only {agreeing}/{total_factors} factors agree",
        "factor_agreement": agreeing,
    }
