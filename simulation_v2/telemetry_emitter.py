"""
telemetry_emitter.py — Combined telemetry output for Simulation V2.

Wires together the GPS simulator, driver behavior, door events, traffic
model, and temperature simulation into a single telemetry event per tick.
"""

import math
import random
from datetime import datetime, timezone, timedelta

from simulation_v2.gps_simulator_v2 import TruckState
from simulation_v2.traffic_model import get_speed
from simulation_v2.driver_behavior import StopScheduler
from simulation_v2.door_event_sim import DoorEventSimulator
from simulation_v2.route_cache import load_route
from simulation_v2.route_engine import fetch_and_cache_all_routes

_IST = timezone(timedelta(hours=5, minutes=30))

# Simulation tick interval (seconds)
TICK_INTERVAL = 2


class TruckSimulator:
    """
    Full simulation state for a single truck/shipment.
    Combines GPS movement, driver behavior, door events, and temperature.
    """

    def __init__(self, shipment):
        self.shipment = shipment
        self.shipment_id = shipment["shipment_id"]

        # Load or generate route
        route = load_route(self.shipment_id)
        if not route:
            raise ValueError(f"No cached route for {self.shipment_id}. "
                             f"Run fetch_and_cache_all_routes() first.")

        self.truck = TruckState(route)
        self.scheduler = StopScheduler(self.shipment_id)
        self.door_sim = DoorEventSimulator()

        # Temperature state
        self.base_temp = shipment.get("base_temp",
                                      (shipment["safe_min_temp"] + shipment["safe_max_temp"]) / 2)
        self.current_temp = self.base_temp
        self.temp_mode = shipment.get("temp_mode", "stable")

        # Compressor state
        self.compressor_on = True
        self.compressor_load_pct = random.randint(60, 90)
        self.compressor_cycles = random.randint(50, 200)

        # Tracking
        self._prev_stop = None
        self._driving_hours = 0.0

    def _simulate_temperature(self, delta_t, is_stopped, door_open):
        """Compute temperature for this tick based on conditions.

        All rates are expressed in units per minute. The factor
        ``delta_t_min`` converts the per-tick step to minutes so that
        the simulation produces realistic temperature changes regardless
        of the tick interval.
        """
        safe_min = self.shipment["safe_min_temp"]
        safe_max = self.shipment["safe_max_temp"]
        ideal = (safe_min + safe_max) / 2
        delta_t_min = delta_t / 60.0  # convert seconds → minutes

        if self.temp_mode == "stable":
            # Normal fluctuation around ideal
            noise = random.uniform(-0.3, 0.3) * delta_t_min
            # Door open causes temp to rise (~0.5 C/min on average)
            if door_open:
                ambient_effect = random.uniform(0.3, 0.8)  # C/min
                self.current_temp += ambient_effect * delta_t_min
            # Compressor off causes slow drift (~0.3 C/min)
            if not self.compressor_on:
                self.current_temp += 0.3 * delta_t_min
            else:
                # Compressor pulls temp back towards ideal (~0.2 C/min)
                diff = self.current_temp - ideal
                recovery = min(abs(diff), 0.2 * delta_t_min)
                self.current_temp -= math.copysign(recovery, diff)

            self.current_temp += noise

        elif self.temp_mode == "drift":
            # Gradual temperature rise (simulating compressor failure)
            # Rates are in C/min: HIGH sensitivity drifts faster
            sensitivity = self.shipment.get("sensitivity", "MEDIUM")
            drift_rate = 0.12 if sensitivity == "HIGH" else 0.06  # C/min
            self.current_temp += drift_rate * delta_t_min

            # Door open accelerates drift (+0.5 C/min)
            if door_open:
                self.current_temp += 0.5 * delta_t_min

            # Auto-recover if it drifts too far (safety valve)
            if self.current_temp > safe_max + 8:
                self.current_temp = safe_max - 1
                self.temp_mode = "stable"

        return round(self.current_temp, 2)

    def _simulate_compressor(self, delta_t, is_stopped):
        """Simulate compressor cycling.

        Probabilities are per-minute rates converted to per-tick using
        ``delta_t / 60``.
        """
        delta_t_min = delta_t / 60.0
        if is_stopped:
            # 10% per minute chance compressor cycles off during stops
            if random.random() < 0.10 * delta_t_min:
                self.compressor_on = not self.compressor_on
                if self.compressor_on:
                    self.compressor_cycles += 1
        else:
            # 3% per minute chance of toggle while driving
            if random.random() < 0.03 * delta_t_min:
                self.compressor_on = not self.compressor_on
                if self.compressor_on:
                    self.compressor_cycles += 1

        if self.compressor_on:
            self.compressor_load_pct = min(100, max(40,
                self.compressor_load_pct + random.randint(-5, 5)))
        else:
            self.compressor_load_pct = 0

    def tick(self, delta_t=TICK_INTERVAL, sim_time=None):
        """
        Advance simulation by one tick and return a telemetry event.

        Parameters
        ----------
        delta_t : float
            Tick duration in seconds.
        sim_time : datetime or None
            Simulated current time. Uses real time if None.

        Returns
        -------
        dict  Telemetry event matching the V2 schema.
        """
        if sim_time is None:
            sim_time = datetime.now(_IST)

        # --- GPS movement (advance first to get distance) ---
        prev_km = self.truck.distance_covered_m / 1000
        road_class = self.truck.current_road_class
        speed_kmh = get_speed(road_class, sim_time.hour, sim_time.minute)
        # Add slight speed variation
        speed_kmh *= random.uniform(0.90, 1.10)
        speed_kmh = round(speed_kmh, 1)

        # --- Driver behavior ---
        # Only pass distance delta if the truck is actually moving
        # (avoid accumulating fuel-stop km while stopped)
        distance_delta_km = speed_kmh * delta_t / 3600 if self._prev_stop is None else 0.0
        stop = self.scheduler.update(delta_t, distance_delta_km, sim_time)
        is_stopped = stop is not None

        # Trigger door events on new stop start
        if is_stopped and self._prev_stop is None:
            self.door_sim.on_stop_start(stop["type"])
        self._prev_stop = stop

        # --- Apply movement only if not stopped ---
        if is_stopped:
            pos = self.truck.get_position()
            speed_kmh = 0.0
        else:
            pos = self.truck.advance(delta_t, speed_kmh)
            self._driving_hours += delta_t / 3600

        # Track distance covered
        new_km = self.truck.distance_covered_m / 1000
        distance_delta = new_km - prev_km

        # --- Door events ---
        door = self.door_sim.update(delta_t, is_stopped, self._driving_hours)
        door_is_open = door["door_status"] == "OPEN"

        # --- Compressor ---
        self._simulate_compressor(delta_t, is_stopped)

        # --- Temperature ---
        temp = self._simulate_temperature(delta_t, is_stopped, door_is_open)

        # --- Build telemetry event ---
        telemetry = {
            "shipment_id": self.shipment_id,
            "timestamp": sim_time.isoformat(),
            "gps": {
                "lat": round(pos["lat"], 6),
                "lng": round(pos["lng"], 6),
                "road_class": pos.get("road_class", "highway"),
            },
            "speed_kmh": speed_kmh if not is_stopped else 0.0,
            "temperature": temp,
            "door_status": door["door_status"],
            "door_open_sec": door["door_open_sec"],
            "compressor": {
                "status": "RUNNING" if self.compressor_on else "OFF",
                "load_pct": self.compressor_load_pct,
            },
            "stop_event": {
                "type": stop["type"],
                "label": stop["label"],
                "remaining_sec": stop["remaining_sec"],
            } if stop else None,
            "driver_state": "IDLE" if is_stopped else "DRIVING",
            # Extra fields for risk engine
            "product_type": self.shipment.get("product_type", "Generic"),
            "cargo_value_inr": self.shipment.get("cargo_value_inr", 0),
            "safe_min_temp": self.shipment.get("safe_min_temp", 2),
            "safe_max_temp": self.shipment.get("safe_max_temp", 8),
            "eta_minutes_remaining": round(
                self.truck.remaining_distance_km() / max(speed_kmh, 30) * 60, 1
            ) if speed_kmh > 0 else round(
                self.truck.remaining_distance_km() / 50 * 60, 1
            ),
            "distance_remaining_km": round(self.truck.remaining_distance_km(), 2),
            "route_progress": round(self.truck.progress_fraction, 4),
        }

        return telemetry


def init_routes(shipments):
    """
    Ensure all shipment routes are cached.
    Call this once at startup before creating TruckSimulators.
    """
    from simulation_v2.route_cache import is_cached
    missing = [s for s in shipments if not is_cached(s["shipment_id"])]
    if missing:
        fetch_and_cache_all_routes(missing)


def emit_telemetry_v2(shipment, simulator=None, sim_time=None):
    """
    Generate one telemetry event for a shipment.

    If no simulator is provided, creates a new one (stateless mode).
    For continuous simulation, keep the TruckSimulator instance alive.
    """
    if simulator is None:
        simulator = TruckSimulator(shipment)
    return simulator.tick(sim_time=sim_time)
