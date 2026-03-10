"""
exposure_tracker.py — Cumulative out-of-range temperature tracking.

Maintains a per-shipment rolling counter of minutes spent outside the
safe temperature range. Resets if temperature returns to safe range
for more than 5 consecutive minutes.
"""

from collections import defaultdict


class ExposureTracker:
    """
    Track cumulative exposure time outside safe temperature range.

    Per-shipment state:
    - exposure_minutes: total time outside range
    - recovery_minutes: consecutive time back inside range
    - Resets exposure if recovery exceeds RECOVERY_THRESHOLD
    """

    RECOVERY_THRESHOLD_MIN = 5.0  # minutes of safe temp before reset

    def __init__(self):
        self._state = defaultdict(lambda: {
            "exposure_minutes": 0.0,
            "recovery_minutes": 0.0,
            "is_out_of_range": False,
        })

    def update(self, shipment_id, current_temp, safe_min, safe_max,
               delta_t_seconds):
        """
        Update exposure tracking for a shipment.

        Parameters
        ----------
        shipment_id : str
        current_temp : float
            Current temperature reading.
        safe_min, safe_max : float
            Safe temperature range.
        delta_t_seconds : float
            Time elapsed since last update.

        Returns
        -------
        dict
            {"exposure_minutes": float,
             "is_out_of_range": bool,
             "exposure_ratio": float}
        """
        state = self._state[shipment_id]
        delta_min = delta_t_seconds / 60.0

        is_out = current_temp < safe_min or current_temp > safe_max

        if is_out:
            state["exposure_minutes"] += delta_min
            state["recovery_minutes"] = 0.0
            state["is_out_of_range"] = True
        else:
            state["recovery_minutes"] += delta_min
            state["is_out_of_range"] = False

            # Reset exposure if recovered long enough
            if state["recovery_minutes"] >= self.RECOVERY_THRESHOLD_MIN:
                state["exposure_minutes"] = 0.0
                state["recovery_minutes"] = 0.0

        return {
            "exposure_minutes": round(state["exposure_minutes"], 2),
            "is_out_of_range": state["is_out_of_range"],
        }

    def get_exposure(self, shipment_id):
        """Return current exposure minutes for a shipment."""
        return self._state[shipment_id]["exposure_minutes"]

    def reset(self, shipment_id):
        """Manually reset exposure for a shipment."""
        self._state[shipment_id] = {
            "exposure_minutes": 0.0,
            "recovery_minutes": 0.0,
            "is_out_of_range": False,
        }
