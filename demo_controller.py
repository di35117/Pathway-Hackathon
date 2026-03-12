"""
demo_controller.py -- Run all 25 shipments through the V2 pipeline.

Uses the same 25 shipments from the V1 factory, but with:
  - Real highway polylines (NH/SH) for GPS movement
  - Multi-factor risk assessment per cargo type
  - Economic diversion decisions

Usage:
    python demo_controller.py          # Run all 25 shipments (quick)
    python demo_controller.py full     # Run all 25 with more ticks
    python demo_controller.py demo     # Run 4 showcase scenarios

No external dependencies needed (no MQTT, no API keys).
"""

import json
import sys
import random
from datetime import datetime, timezone, timedelta

# Force UTF-8 output on Windows
import io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim.shipment_factory import generate_shipments
from simulation_v2.telemetry_emitter import TruckSimulator, init_routes
from simulation_v2.route_engine import fetch_and_cache_all_routes
from simulation_v2.route_cache import load_route
from risk_engine_v2.risk_calculator_v2 import assess_risk_v2, reset_tracking
from decision_engine_v2.decision_logic_v2 import decide_v2, reset_tracking as reset_decision

_IST = timezone(timedelta(hours=5, minutes=30))


def _print_header(text, width=72):
    print(f"\n{'-'*width}")
    print(f"  {text}")
    print(f"{'-'*width}")


def _print_json(data, label=""):
    if label:
        print(f"\n  >> {label}:")
    print(json.dumps(data, indent=2, default=str))


def run_all_shipments(shipments, ticks=20, verbose=True, tick_interval=30):
    """
    Run ALL shipments through the full V2 pipeline.

    Parameters
    ----------
    shipments : list
        Shipments from shipment_factory or showcase.
    ticks : int
        Number of simulation ticks per shipment.
    verbose : bool
        If True, print tick-by-tick output. If False, only summary.
    tick_interval : int
        Seconds of simulated time per tick (default 30).
        30 s/tick x 60 ticks = 30 min simulated time — enough for
        temperature drift to develop and trigger diversion decisions.
    """
    print(f"\n{'#'*72}")
    print(f"#{'':^70}#")
    print(f"#{'LIVECOLD V2 -- ALL 25 SHIPMENTS':^70}#")
    print(f"#{'Real Highway GPS | Multi-Factor Risk | Economic Decision':^70}#")
    print(f"#{'':^70}#")
    print(f"{'#'*72}")

    # Pre-generate routes for all 25 shipments
    print(f"\n  Generating highway routes for {len(shipments)} shipments...")
    routes = fetch_and_cache_all_routes(shipments)
    route_types = {}
    for sid, route in routes.items():
        road_classes = set(wp.get("road_class", "highway") for wp in route)
        route_types[sid] = ", ".join(sorted(road_classes))
    print(f"  Done! {len(routes)} routes cached with real NH/SH waypoints.\n")

    # Show route summary
    _print_header("ROUTE SUMMARY")
    print(f"\n  {'ID':<8} {'Route':<35} {'Cargo':<14} {'Waypoints':>10} {'Road Types'}")
    print(f"  {'='*8} {'='*35} {'='*14} {'='*10} {'='*25}")
    for s in shipments:
        sid = s["shipment_id"]
        route = routes.get(sid, [])
        print(f"  {sid:<8} {s['origin']+' -> '+s['destination']:<35} "
              f"{s['product_type']:<14} {len(route):>10} "
              f"{route_types.get(sid, 'synthetic')}")

    # Reset tracking
    reset_tracking()
    reset_decision()

    # Create simulators for all trucks
    simulators = {}
    for s in shipments:
        sid = s["shipment_id"]
        try:
            simulators[sid] = TruckSimulator(s)
        except Exception as e:
            print(f"  Warning: Could not create simulator for {sid}: {e}")

    sim_time = datetime.now(_IST)
    results = []

    total_sim_sec = ticks * tick_interval
    total_sim_min = total_sim_sec / 60
    _print_header(f"RUNNING {ticks} TICKS x {tick_interval}s = {total_sim_min:.0f} min simulated")

    for tick in range(ticks):
        sim_time = sim_time + timedelta(seconds=tick_interval)

        for s in shipments:
            sid = s["shipment_id"]
            sim = simulators.get(sid)
            if not sim:
                continue

            telemetry = sim.tick(delta_t=tick_interval, sim_time=sim_time)
            risk = assess_risk_v2(telemetry, delta_t_seconds=float(tick_interval))
            decision = decide_v2(risk, s, delta_t=float(tick_interval))

            # Store last state
            if tick == ticks - 1:
                results.append({
                    "shipment_id": sid,
                    "origin": s["origin"],
                    "destination": s["destination"],
                    "product_type": s["product_type"],
                    "cargo_value": s["cargo_value_inr"],
                    "lat": telemetry["gps"]["lat"],
                    "lng": telemetry["gps"]["lng"],
                    "road_class": telemetry["gps"]["road_class"],
                    "speed": telemetry["speed_kmh"],
                    "temp": telemetry["temperature"],
                    "risk_prob": risk["risk_probability"],
                    "risk_level": risk["risk_level"],
                    "action": decision["action"],
                    "confidence": decision["confidence"],
                    "progress": telemetry.get("route_progress", 0),
                    "driver_state": telemetry["driver_state"],
                })

            # Print notable events in verbose mode
            if verbose and decision["action"] != "CONTINUE":
                print(f"  !! {sid} | {s['origin']}->{s['destination']} | "
                      f"Temp: {telemetry['temperature']:5.1f}C | "
                      f"Risk: {risk['risk_probability']:.1%} | "
                      f"Action: {decision['action']}")

        if verbose and tick % 10 == 0:
            active = sum(1 for s in simulators.values() if not s.truck.finished)
            elapsed_min = (tick + 1) * tick_interval / 60
            print(f"  -- Tick {tick+1:3d} ({elapsed_min:5.1f} min) | "
                  f"{active}/{len(simulators)} trucks active")

    # Final summary
    _print_header("FINAL STATE - ALL 25 SHIPMENTS")
    print(f"\n  {'ID':<8} {'Route':<30} {'Cargo':<12} {'Temp':>6} {'Risk':>7} "
          f"{'Level':>7} {'Action':>15} {'Road':>10} {'State':>8}")
    print(f"  {'='*8} {'='*30} {'='*12} {'='*6} {'='*7} {'='*7} {'='*15} {'='*10} {'='*8}")

    divert_count = 0
    monitor_count = 0
    high_risk_count = 0

    for r in results:
        tag = {"DIVERT": "[!!]", "MONITOR_CLOSELY": "[??]", "CONTINUE": "[OK]"}.get(
            r["action"], "[--]"
        )
        print(f"  {r['shipment_id']:<8} "
              f"{r['origin']+'->'+r['destination']:<30} "
              f"{r['product_type']:<12} "
              f"{r['temp']:>5.1f}C "
              f"{r['risk_prob']:>6.1%} "
              f"{r['risk_level']:>7} "
              f"{tag} {r['action']:>11} "
              f"{r['road_class']:>10} "
              f"{r['driver_state']:>8}")

        if r["action"] == "DIVERT":
            divert_count += 1
        elif r["action"] == "MONITOR_CLOSELY":
            monitor_count += 1
        if r["risk_level"] == "HIGH":
            high_risk_count += 1

    # Aggregate stats
    _print_header("AGGREGATE METRICS")
    print(f"\n  Total shipments:   {len(results)}")
    print(f"  High risk:         {high_risk_count}")
    print(f"  Diversions:        {divert_count}")
    print(f"  Monitor closely:   {monitor_count}")
    print(f"  Total cargo value: INR {sum(r['cargo_value'] for r in results):,.0f}")
    print(f"  Avg risk:          {sum(r['risk_prob'] for r in results)/len(results):.1%}")

    print(f"\n{'='*72}")
    print(f"  Demo complete. All {len(results)} shipments processed through V2 pipeline.")
    print(f"{'='*72}\n")

    return results


def run_showcase_scenarios():
    """Run 4 hand-picked scenarios that demonstrate V2 capabilities."""
    showcase = [
        {
            "shipment_id": "DEMO-VAX-001",
            "origin": "Delhi", "destination": "Jaipur",
            "current_lat": 28.7041, "current_lon": 77.1025,
            "end_lat": 26.9124, "end_lon": 75.7873,
            "speed_kmph": 55, "distance_km": 280,
            "eta_minutes_remaining": 305,
            "product_type": "Vaccines",
            "safe_min_temp": 2, "safe_max_temp": 8,
            "cargo_value_inr": 2500000, "sensitivity": "HIGH",
            "base_temp": 6.5, "temp_mode": "drift",
            "nearest_hub_distance_km": 25,
        },
        {
            "shipment_id": "DEMO-SEA-002",
            "origin": "Kochi", "destination": "Chennai",
            "current_lat": 9.9312, "current_lon": 76.2673,
            "end_lat": 13.0827, "end_lon": 80.2707,
            "speed_kmph": 50, "distance_km": 700,
            "eta_minutes_remaining": 840,
            "product_type": "Seafood",
            "safe_min_temp": 0, "safe_max_temp": 4,
            "cargo_value_inr": 1200000, "sensitivity": "HIGH",
            "base_temp": 2.0, "temp_mode": "stable",
            "nearest_hub_distance_km": 35,
        },
        {
            "shipment_id": "DEMO-DRY-003",
            "origin": "Mumbai", "destination": "Pune",
            "current_lat": 19.0760, "current_lon": 72.8777,
            "end_lat": 18.5204, "end_lon": 73.8567,
            "speed_kmph": 45, "distance_km": 150,
            "eta_minutes_remaining": 200,
            "product_type": "Dairy",
            "safe_min_temp": 1, "safe_max_temp": 4,
            "cargo_value_inr": 800000, "sensitivity": "MEDIUM",
            "base_temp": 3.5, "temp_mode": "drift",
            "nearest_hub_distance_km": 15,
        },
        {
            "shipment_id": "DEMO-FZN-004",
            "origin": "Bangalore", "destination": "Hyderabad",
            "current_lat": 12.9716, "current_lon": 77.5946,
            "end_lat": 17.3850, "end_lon": 78.4867,
            "speed_kmph": 60, "distance_km": 570,
            "eta_minutes_remaining": 570,
            "product_type": "Frozen_Meat",
            "safe_min_temp": -20, "safe_max_temp": -10,
            "cargo_value_inr": 1500000, "sensitivity": "MEDIUM",
            "base_temp": -17.0, "temp_mode": "stable",
            "nearest_hub_distance_km": 40,
        },
    ]

    fetch_and_cache_all_routes(showcase)
    # 60 ticks x 30s = 30 min simulated — enough for vaccine drift to trigger DIVERT
    return run_all_shipments(showcase, ticks=60, verbose=True, tick_interval=30)


def main():
    """Entry point. Default: run all 25 shipments."""
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"

    if mode == "demo":
        run_showcase_scenarios()
    elif mode == "full":
        shipments = generate_shipments()
        run_all_shipments(shipments, ticks=60, verbose=True, tick_interval=30)
    else:
        # Default: quick run with all 25
        shipments = generate_shipments()
        run_all_shipments(shipments, ticks=40, verbose=True, tick_interval=30)


if __name__ == "__main__":
    main()
