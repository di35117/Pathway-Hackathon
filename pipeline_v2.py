"""
pipeline_v2.py — Wires V2 modules together.

This is the single entry point that replaces the V1 pipeline flow.
It exposes the same output interface so the dashboard/API need no changes.

Usage:
    from pipeline_v2 import run_pipeline_v2
    telemetry, risk, decision = run_pipeline_v2(shipment)
"""

from collections import defaultdict, deque
from datetime import datetime

from simulation_v2.telemetry_emitter import emit_telemetry_v2, TruckSimulator, init_routes
from risk_engine_v2.risk_calculator_v2 import (
    assess_risk_v2,
    linear_forecast,
    compute_exposure_increment,
    compute_spoilage_probability,
)
from decision_engine_v2.decision_logic_v2 import decide_v2


# Rolling temp history per shipment for optional forecast output.
_temp_history = defaultdict(lambda: deque(maxlen=60))


def run_pipeline_v2(shipment, simulator=None, sim_time=None,
                    hub_selector=None, delta_t=2.0):
    """
    Run one tick of the V2 pipeline for a single shipment.

    Parameters
    ----------
    shipment : dict
        Shipment data (from shipment_factory or compatible dict).
    simulator : TruckSimulator or None
        Persistent simulator instance. Create one per shipment and reuse.
    sim_time : datetime or None
        Simulated time. Uses real time if None.
    hub_selector : callable or None
        Optional hub selection function from existing decision_engine.
    delta_t : float
        Tick interval in seconds.

    Returns
    -------
    tuple  (telemetry_event, risk_assessment, decision_output)
    """
    # Step 1: Generate telemetry via Simulation V2
    telemetry = emit_telemetry_v2(shipment, simulator=simulator, sim_time=sim_time)

    # Step 2: Assess risk via Risk Engine V2
    risk = assess_risk_v2(telemetry, delta_t_seconds=delta_t)

    # Step 3: Make decision via Decision Engine V2
    decision = decide_v2(risk, shipment, hub_selector=hub_selector)

    return telemetry, risk, decision


def run_pipeline_v2_enhanced(
    shipment,
    simulator=None,
    sim_time=None,
    hub_selector=None,
    delta_t=2.0,
    stores=None,
    forecast_horizon_min=0,
):
    """
    Run one tick of the V2 pipeline with optional forecast and store-aware outputs.

    This function is additive and does not change `run_pipeline_v2` behavior.
    """
    telemetry = emit_telemetry_v2(shipment, simulator=simulator, sim_time=sim_time)
    risk = assess_risk_v2(telemetry, delta_t_seconds=delta_t)

    decision = decide_v2(
        risk,
        shipment,
        hub_selector=hub_selector,
        stores=stores,
    )

    sid = telemetry["shipment_id"]
    ts = datetime.fromisoformat(telemetry["timestamp"])
    temp = float(telemetry["temperature"])
    history = _temp_history[sid]
    history.append((ts, temp))

    predicted_temp = None
    predicted_exposure_degree_hours = risk.get("exposure_degree_hours")
    predicted_spoilage_prob = risk.get("spoilage_probability")

    if forecast_horizon_min and forecast_horizon_min > 0:
        predicted_temp = linear_forecast(list(history), horizon_minutes=forecast_horizon_min)
        if predicted_temp is not None:
            safe_max = float(telemetry.get("safe_max_temp", shipment.get("safe_max_temp", 8.0)))
            increment = compute_exposure_increment(
                predicted_temp,
                safe_max,
                forecast_horizon_min / 60.0,
            )
            predicted_exposure_degree_hours = round(
                float(risk.get("exposure_degree_hours", 0.0)) + increment,
                4,
            )
            predicted_spoilage_prob = round(
                compute_spoilage_probability(predicted_exposure_degree_hours),
                4,
            )

    forecast = {
        "horizon_minutes": int(max(0, forecast_horizon_min)),
        "predicted_temp": round(predicted_temp, 3) if predicted_temp is not None else None,
        "predicted_exposure_degree_hours": predicted_exposure_degree_hours,
        "predicted_spoilage_probability": predicted_spoilage_prob,
    }

    return telemetry, risk, decision, forecast


def run_pipeline_v2_batch(shipments, simulators=None, sim_time=None,
                          hub_selector=None, delta_t=2.0):
    """
    Run one tick of the V2 pipeline for all shipments.

    Parameters
    ----------
    shipments : list[dict]
    simulators : dict[str, TruckSimulator] or None
        Map of shipment_id → TruckSimulator. Creates new ones if None.
    sim_time : datetime or None
    hub_selector : callable or None
    delta_t : float

    Returns
    -------
    list[tuple]  [(telemetry, risk, decision), ...]
    """
    if simulators is None:
        simulators = {}

    # Ensure all routes are cached before creating simulators
    init_routes(shipments)

    results = []
    for shipment in shipments:
        sid = shipment["shipment_id"]
        sim = simulators.get(sid)
        if sim is None:
            sim = TruckSimulator(shipment)
            simulators[sid] = sim

        result = run_pipeline_v2(shipment, simulator=sim,
                                 sim_time=sim_time,
                                 hub_selector=hub_selector,
                                 delta_t=delta_t)
        results.append(result)

    return results
