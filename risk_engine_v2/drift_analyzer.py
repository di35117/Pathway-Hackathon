"""
drift_analyzer.py — Temperature rate-of-change analysis.

Uses a sliding 5-minute window to calculate °C/min drift rate.
A positive drift exceeding 0.5 °C/min triggers an elevated weight
on the compressor signal in the risk calculator.
"""

from collections import defaultdict, deque

WINDOW_SECONDS = 300  # 5-minute sliding window
CRITICAL_DRIFT_RATE = 0.5  # °C/min — threshold for elevated risk


class DriftAnalyzer:
    """
    Track temperature drift rate per shipment using a sliding window.

    Each reading is stored as (timestamp_seconds, temp_c).
    The drift rate is computed as the slope of temp over the window.
    """

    def __init__(self, window_seconds=WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._history = defaultdict(deque)
        self._elapsed = defaultdict(float)  # cumulative seconds per shipment

    def update(self, shipment_id, temp_c, delta_t_seconds):
        """
        Add a new temperature reading and compute drift rate.

        Parameters
        ----------
        shipment_id : str
        temp_c : float
            Current temperature.
        delta_t_seconds : float
            Time elapsed since last reading.

        Returns
        -------
        dict
            {"drift_rate_c_min": float,
             "is_critical": bool,
             "window_readings": int}
        """
        self._elapsed[shipment_id] += delta_t_seconds
        t = self._elapsed[shipment_id]

        history = self._history[shipment_id]
        history.append((t, temp_c))

        # Trim window
        cutoff = t - self.window_seconds
        while history and history[0][0] < cutoff:
            history.popleft()

        # Compute drift rate
        drift_rate = self._compute_drift(history)

        return {
            "drift_rate_c_min": round(drift_rate, 4),
            "is_critical": drift_rate > CRITICAL_DRIFT_RATE,
            "window_readings": len(history),
        }

    def _compute_drift(self, history):
        """
        Compute drift as °C per minute using linear regression
        over the sliding window.
        """
        if len(history) < 2:
            return 0.0

        n = len(history)
        sum_t = sum_temp = sum_t2 = sum_t_temp = 0.0

        for t, temp in history:
            t_min = t / 60.0  # convert to minutes
            sum_t += t_min
            sum_temp += temp
            sum_t2 += t_min * t_min
            sum_t_temp += t_min * temp

        denominator = n * sum_t2 - sum_t * sum_t
        if abs(denominator) < 1e-10:
            return 0.0

        slope = (n * sum_t_temp - sum_t * sum_temp) / denominator
        return slope

    def get_drift(self, shipment_id):
        """Return current drift rate for a shipment."""
        history = self._history.get(shipment_id, deque())
        return self._compute_drift(history)

    def reset(self, shipment_id):
        """Clear history for a shipment."""
        self._history[shipment_id].clear()
        self._elapsed[shipment_id] = 0.0
