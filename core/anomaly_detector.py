"""
LiveCold — Multi-Layer Anomaly Detection Engine
Filters sensor glitches before they trigger false diversions.

4-Layer Detection:
  L1  Physical Bounds     — Reject impossible temperatures
  L2  Rate-of-Change      — Flag sudden jumps (sensor fault)
  L3  Statistical Z-Score — Detect outliers from rolling mean
  L4  Stuck Sensor        — Flag repeated identical readings
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field


# ══════════════════════════════════════════════════════════════════
#  Configuration — product-specific physical limits
# ══════════════════════════════════════════════════════════════════

PHYSICAL_LIMITS = {
    # product_type: (absolute_min_°C, absolute_max_°C)
    # Even in worst malfunction, values outside these are hardware errors
    "vaccines":    (-90,  30),
    "frozen_meat": (-45,  25),
    "dairy":       (-10,  35),
    "seafood":     (-30,  30),
    "pharmaceuticals": (-15, 40),
    "ice_cream":   (-50,  20),
    "fruits":      (-5,   45),
    "flowers":     (-5,   40),
    "default":     (-60,  60),
}

# Maximum physically possible rate of change, in °C per SECOND.
# A reefer body has thermal mass: even with the doors wide open in Indian summer
# heat, internal temperature rises around 0.05 °C/s. 0.25 gives a 5x safety
# margin over that, so genuine thermal events pass while electrical faults
# (a 20 °C step between consecutive reads) do not.
MAX_RATE_C_PER_SEC = 0.25

# Hard ceiling on the allowance regardless of how long the gap was. Without it,
# a pipeline stall makes the budget grow without bound — a 60-second gap would
# permit a 180 °C swing, which is not a check at all.
MAX_RATE_ABSOLUTE_C = 15.0

# Z-score threshold — readings this many std devs from mean are flagged
ZSCORE_THRESHOLD = 3.5

# Floor on the standard deviation used by L3, in °C — the intrinsic noise of a
# cold-chain probe. Without it, a very stable (or stuck) sensor drives the
# measured sigma toward zero and every subsequent reading becomes a huge
# z-score: a truck recovering from a stuck sensor had all of its legitimate
# temperature changes rejected as outliers, indefinitely. Flooring sigma at real
# sensor resolution keeps genuine outliers detectable while letting normal
# variation through.
MIN_SENSOR_NOISE_C = 0.25

# Stuck sensor: if N consecutive readings are identical (within epsilon)
STUCK_SENSOR_COUNT = 10
STUCK_EPSILON = 0.001       # readings within this are "identical"

# Rolling window size for statistical calculations
WINDOW_SIZE = 20


# ══════════════════════════════════════════════════════════════════
#  Anomaly Result
# ══════════════════════════════════════════════════════════════════

@dataclass
class AnomalyResult:
    """Result of anomaly detection for one reading."""
    is_anomaly: bool = False
    layer: str = ""               # "L1_BOUNDS", "L2_RATE", "L3_ZSCORE", "L4_STUCK"
    reason: str = ""
    original_temp: float = 0.0
    corrected_temp: float | None = None  # fallback safe value

    def __bool__(self):
        return self.is_anomaly


# ══════════════════════════════════════════════════════════════════
#  Per-Shipment State Tracker
# ══════════════════════════════════════════════════════════════════

@dataclass
class ShipmentSensorState:
    """Maintains rolling state for one shipment's sensor readings."""
    history: list = field(default_factory=list)    # last N temps
    timestamps: list = field(default_factory=list) # last N timestamps
    consecutive_same: int = 0                       # stuck counter
    stuck_reported: bool = False                    # edge-trigger latch for L4
    last_temp: float | None = None
    last_time: float = 0.0
    total_readings: int = 0
    anomalies_detected: int = 0


# ══════════════════════════════════════════════════════════════════
#  Anomaly Detection Engine
# ══════════════════════════════════════════════════════════════════

class AnomalyDetector:
    """
    Multi-layer anomaly detector for cold-chain temperature sensors.

    Usage:
        detector = AnomalyDetector()
        result = detector.check("SHP_1", 4.5, "dairy")
        if result.is_anomaly:
            print(f"Anomaly! {result.reason}")
            # Use result.corrected_temp instead of original
    """

    def __init__(self):
        self._states = defaultdict(ShipmentSensorState)
        self._lock = threading.Lock()
        self._global_stats = {
            "total_readings": 0,
            "total_anomalies": 0,
            "l1_bounds": 0,
            "l2_rate": 0,
            "l3_zscore": 0,
            "l4_stuck": 0,
        }

    def check(self, shipment_id: str, temp: float, product_type: str = "default") -> AnomalyResult:
        """
        Run all 4 layers of anomaly detection on a temperature reading.
        Returns AnomalyResult with is_anomaly flag and reason.
        """
        with self._lock:
            state = self._states[shipment_id]
            state.total_readings += 1
            self._global_stats["total_readings"] += 1
            now = time.time()

            # ── L1: Physical Bounds Check ─────────────────────────
            result = self._check_bounds(temp, product_type)
            if result.is_anomaly:
                state.anomalies_detected += 1
                self._global_stats["total_anomalies"] += 1
                self._global_stats["l1_bounds"] += 1
                return result

            # ── L2: Rate-of-Change Check ──────────────────────────
            result = self._check_rate(temp, state, now)
            if result.is_anomaly:
                state.anomalies_detected += 1
                self._global_stats["total_anomalies"] += 1
                self._global_stats["l2_rate"] += 1
                # Don't update history with anomalous reading
                return result

            # ── L3: Statistical Z-Score Check ─────────────────────
            result = self._check_zscore(temp, state)
            if result.is_anomaly:
                state.anomalies_detected += 1
                self._global_stats["total_anomalies"] += 1
                self._global_stats["l3_zscore"] += 1
                return result

            # ── L4: Stuck Sensor Check ────────────────────────────
            # Unlike L1-L3 this does NOT reject the reading: a frozen ADC may
            # still be reporting the correct value. The sensor needs
            # maintenance, the reading does not need discarding. So we fall
            # through to the history update and then return the flag, letting
            # the caller raise a maintenance alert while still using the value.
            stuck = self._check_stuck(temp, state)
            if stuck.is_anomaly:
                state.anomalies_detected += 1
                self._global_stats["total_anomalies"] += 1
                self._global_stats["l4_stuck"] += 1

            # ── Update rolling state ──────────────────────────────
            state.history.append(temp)
            state.timestamps.append(now)
            if len(state.history) > WINDOW_SIZE:
                state.history.pop(0)
                state.timestamps.pop(0)
            state.last_temp = temp
            state.last_time = now

            if stuck.is_anomaly:
                return stuck
            return AnomalyResult(is_anomaly=False, original_temp=temp)

    def _check_bounds(self, temp: float, product_type: str) -> AnomalyResult:
        """L1: Reject physically impossible values."""
        key = product_type.lower().replace(" ", "_")
        bounds = PHYSICAL_LIMITS.get(key, PHYSICAL_LIMITS["default"])

        if temp < bounds[0] or temp > bounds[1]:
            return AnomalyResult(
                is_anomaly=True,
                layer="L1_BOUNDS",
                reason=f"Temp {temp}°C outside physical limits [{bounds[0]}, {bounds[1]}] for {product_type}",
                original_temp=temp,
                corrected_temp=None,  # no safe fallback — discard entirely
            )
        return AnomalyResult(is_anomaly=False, original_temp=temp)

    def _check_rate(self, temp: float, state: ShipmentSensorState, now: float) -> AnomalyResult:
        """L2: Detect impossibly fast temperature changes (sensor fault)."""
        if state.last_temp is None:
            return AnomalyResult(is_anomaly=False, original_temp=temp)

        elapsed = max(now - state.last_time, 0.1)  # avoid div/0
        change = abs(temp - state.last_temp)

        # Allowance scales with the real gap between readings but is capped, so
        # a long gap cannot silently disable the check.
        allowed_change = min(MAX_RATE_C_PER_SEC * elapsed, MAX_RATE_ABSOLUTE_C)
        # Floor for very short intervals: at a 2 s tick the raw allowance is
        # 0.5 °C, which would flag ordinary door-open warming as a fault.
        allowed_change = max(allowed_change, 2.0)

        if change > allowed_change:
            return AnomalyResult(
                is_anomaly=True,
                layer="L2_RATE",
                reason=(f"Temp jumped {change:.1f}°C in {elapsed:.1f}s "
                        f"(max allowed: {allowed_change:.1f}°C)"),
                original_temp=temp,
                corrected_temp=state.last_temp,  # fall back to last good reading
            )
        return AnomalyResult(is_anomaly=False, original_temp=temp)

    def _check_zscore(self, temp: float, state: ShipmentSensorState) -> AnomalyResult:
        """L3: Flag readings that are statistical outliers from rolling mean."""
        if len(state.history) < 5:
            return AnomalyResult(is_anomaly=False, original_temp=temp)

        mean = sum(state.history) / len(state.history)
        variance = sum((t - mean) ** 2 for t in state.history) / len(state.history)
        std_dev = variance ** 0.5

        # Floor sigma at the probe's intrinsic noise. A measured sigma near zero
        # means the sensor is very stable or stuck, not that a 0.1°C change is a
        # 9-sigma event.
        effective_std = max(std_dev, MIN_SENSOR_NOISE_C)
        z_score = abs(temp - mean) / effective_std

        if z_score > ZSCORE_THRESHOLD:
            return AnomalyResult(
                is_anomaly=True,
                layer="L3_ZSCORE",
                reason=(f"Z-score {z_score:.1f} exceeds {ZSCORE_THRESHOLD} "
                        f"(temp={temp}°C, mean={mean:.1f}°C, σ={effective_std:.2f})"),
                original_temp=temp,
                corrected_temp=mean,  # fall back to rolling mean
            )
        return AnomalyResult(is_anomaly=False, original_temp=temp)

    def _check_stuck(self, temp: float, state: ShipmentSensorState) -> AnomalyResult:
        """
        L4: Detect frozen/stuck sensors producing identical readings.

        Edge-triggered, not level-triggered. A stuck sensor stays stuck for
        every subsequent reading, so firing on each one would spam the log,
        inflate the anomaly counters and write a duplicate audit row every tick.
        The condition is reported once when it is first detected, and re-arms
        only after the sensor starts moving again.
        """
        if state.last_temp is not None and abs(temp - state.last_temp) < STUCK_EPSILON:
            state.consecutive_same += 1
        else:
            state.consecutive_same = 0
            state.stuck_reported = False  # sensor recovered — re-arm

        if state.consecutive_same >= STUCK_SENSOR_COUNT and not state.stuck_reported:
            state.stuck_reported = True
            return AnomalyResult(
                is_anomaly=True,
                layer="L4_STUCK",
                reason=(f"Sensor stuck: {state.consecutive_same} identical "
                        f"readings ({temp}°C)"),
                original_temp=temp,
                corrected_temp=temp,  # value may be correct; sensor needs service
            )
        return AnomalyResult(is_anomaly=False, original_temp=temp)

    def reset(self, shipment_id: str = None):
        """
        Clear detector state. Pass a shipment_id to clear one truck, or nothing
        to clear everything including the global counters.

        Used by tests, and by the pipeline when a shipment completes so its
        rolling window does not linger for a reused identifier.
        """
        with self._lock:
            if shipment_id is not None:
                self._states.pop(shipment_id, None)
                return
            self._states.clear()
            for key in self._global_stats:
                self._global_stats[key] = 0

    def get_stats(self) -> dict:
        """Return global anomaly detection stats for dashboard."""
        with self._lock:
            return dict(self._global_stats)

    def get_shipment_stats(self, shipment_id: str) -> dict:
        """Return anomaly stats for a specific shipment."""
        with self._lock:
            state = self._states.get(shipment_id)
            if not state:
                return {"total_readings": 0, "anomalies_detected": 0}
            return {
                "total_readings": state.total_readings,
                "anomalies_detected": state.anomalies_detected,
                "anomaly_rate": round(state.anomalies_detected / max(state.total_readings, 1) * 100, 2),
                "history_size": len(state.history),
            }


# ── Global singleton ──────────────────────────────────────────────
detector = AnomalyDetector()
