# V2 Integration Report

This report explains how `simulation_v2`, `risk_engine_v2`, and `decision_engine_v2` work together, and how to integrate them safely into API/dashboard/gateway layers without breaking existing V2 behavior.

## 1. System Overview

Primary orchestration lives in `pipeline_v2.py` and runs three stages per tick:

1. Telemetry generation (`simulation_v2.telemetry_emitter.emit_telemetry_v2`)
2. Risk assessment (`risk_engine_v2.risk_calculator_v2.assess_risk_v2`)
3. Decisioning (`decision_engine_v2.decision_logic_v2.decide_v2`)

Core entrypoints:

- `run_pipeline_v2(...)`
- `run_pipeline_v2_batch(...)`
- `run_pipeline_v2_enhanced(...)` (additive path for forecast + store-aware diversion)

## 2. Execution Flow

Single-shipment flow (`run_pipeline_v2`):

```text
shipment + simulator state
  -> emit_telemetry_v2(...)
  -> assess_risk_v2(...)
  -> decide_v2(...)
  -> returns (telemetry, risk, decision)
```

Enhanced flow (`run_pipeline_v2_enhanced`):

```text
shipment + simulator + optional stores + optional forecast_horizon_min
  -> emit_telemetry_v2(...)
  -> assess_risk_v2(...)
  -> decide_v2(..., stores=stores)
  -> linear_forecast(history, horizon)
  -> predicted exposure/spoilage projection
  -> returns (telemetry, risk, decision, forecast)
```

## 3. Simulation V2 Features

Implemented in `simulation_v2/telemetry_emitter.py` and related modules:

- Road-following GPS movement via cached route polyline (OSRM real road geometry; synthetic fallback only if routing API is unavailable)
- Traffic-aware speed using road class + time band factors
- Driver stop behavior (loading, tea/fuel/lunch/checkpoints)
- Door open/close events tied to stop context
- Compressor state and load simulation
- Temperature model (`stable` and `drift` modes)
- ETA and route progress tracking

Telemetry output contract (`emit_telemetry_v2`):

```json
{
  "shipment_id": "S001",
  "timestamp": "2026-03-10T10:05:00+05:30",
  "gps": {"lat": 28.4595, "lng": 77.0266, "road_class": "highway"},
  "speed_kmh": 58.2,
  "temperature": 7.4,
  "door_status": "CLOSED",
  "door_open_sec": 0,
  "compressor": {"status": "RUNNING", "load_pct": 76},
  "stop_event": null,
  "driver_state": "DRIVING",
  "product_type": "vaccines",
  "cargo_value_inr": 2500000,
  "safe_min_temp": 2,
  "safe_max_temp": 8,
  "eta_minutes_remaining": 240.5,
  "distance_remaining_km": 195.2,
  "route_progress": 0.43
}
```

## 4. Risk Engine V2 Features

Implemented in `risk_engine_v2/risk_calculator_v2.py`:

- Multi-factor risk score with cargo-specific weights
- Signals used:
  - temperature deviation
  - exposure time (minutes out of safe range)
  - ETA pressure
  - door event impact
  - compressor status/load
  - drift rate
- Stateful tracking per shipment:
  - `ExposureTracker` (minutes)
  - `DriftAnalyzer` (deg C per min)
  - cumulative degree-hours (new additive extension)
- Logistic mapping to `risk_probability`
- Risk levels:
  - `LOW` if `< 0.35`
  - `MEDIUM` if `< 0.65`
  - `HIGH` otherwise

Risk output contract (`assess_risk_v2`):

```json
{
  "shipment_id": "S001",
  "cargo_type": "vaccines",
  "risk_probability": 0.7123,
  "risk_level": "HIGH",
  "factor_scores": {
    "temp_deviation": 0.8,
    "exposure_time": 0.5,
    "eta_pressure": 0.3,
    "door_events": 0.1,
    "compressor": 0.2,
    "drift_rate": 0.4
  },
  "exposure_minutes": 7.0,
  "exposure_degree_hours": 3.25,
  "spoilage_probability": 0.21,
  "drift_rate_c_min": 0.12,
  "raw_score": 0.61
}
```

New additive helpers:

- `compute_exposure_increment(temp_c, safe_max_c, dt_hours)`
- `compute_spoilage_probability(exposure_degree_hours, a=0.08, b=20.0)`
- `linear_forecast(last_readings, horizon_minutes=30)`

## 5. Decision Engine V2 Features

Implemented in `decision_engine_v2/decision_logic_v2.py` and `economic_model.py`:

- Economic model:
  - expected loss if continue: `risk_probability * cargo_value`
  - diversion cost: fuel + hub handling + residual risk + emissions delta
  - diversion threshold buffer support
- Confidence scoring:
  - based on factor agreement, signal duration, data freshness
- Actions:
  - `CONTINUE`
  - `MONITOR_CLOSELY`
  - `DIVERT`
- Reason generation from strongest factors

New additive diversion selector (`decision_engine_v2/diversion_selector_v2.py`):

- Feasibility filters:
  - `open == true`
  - `certified == true` (if field exists)
  - `capacity >= doses` when provided
- Distance via Haversine
- Chooses candidate with best score (`expected_loss - diversion_cost`)

Decision output contract (`decide_v2`):

```json
{
  "shipment_id": "S001",
  "action": "DIVERT",
  "confidence": "HIGH",
  "confidence_reason": "5/6 factors consistent for 11.0 min",
  "expected_loss_continue": 120000.0,
  "total_diversion_cost": 3500.0,
  "saving": 116500.0,
  "selected_hub": "South Gurgaon Store",
  "selected_store_id": "cs002",
  "selected_store_distance_km": 6.1,
  "hub_eta_min": 9,
  "co2_delta_kg": 1.53,
  "divert_reason": "Temp deviation + exposure time sustained > 7 min",
  "risk_probability": 0.72,
  "risk_level": "HIGH"
}
```

## 6. Forecast + Preemptive Recommendation Path

Use `run_pipeline_v2_enhanced(...)` with `forecast_horizon_min > 0`.

Forecast output:

```json
{
  "horizon_minutes": 30,
  "predicted_temp": 10.25,
  "predicted_exposure_degree_hours": 5.12,
  "predicted_spoilage_probability": 0.27
}
```

Suggested preemptive rule in API/UI layer:

```text
if forecast.predicted_spoilage_probability >= SPOILAGE_THRESHOLD:
    show "Preemptive diversion recommended"
```

## 7. Backward Compatibility Notes

Guaranteed preserved behavior:

- Existing `run_pipeline_v2(...)` signature and return shape unchanged.
- Existing decision behavior unchanged when `stores` is not passed.
- New fields in risk output are additive only.

Optional features activate only when used:

- Store-aware diversion: pass `stores=[...]` to enhanced path (or directly to `decide_v2`).
- Forecast projection: pass `forecast_horizon_min > 0` to enhanced path.

## 8. Integration Guide (Copy-Paste Ready)

### 8.1 Single Shipment Tick

```python
from simulation_v2.telemetry_emitter import TruckSimulator
from pipeline_v2 import run_pipeline_v2

shipment = {
    "shipment_id": "vax_001",
    "product_type": "vaccines",
    "safe_min_temp": 2,
    "safe_max_temp": 8,
    "cargo_value_inr": 500000,
    "nearest_hub_distance_km": 25,
}

sim = TruckSimulator(shipment)
telemetry, risk, decision = run_pipeline_v2(shipment, simulator=sim, delta_t=2.0)
```

### 8.2 Enhanced Tick (Stores + Forecast)

```python
from simulation_v2.telemetry_emitter import TruckSimulator
from pipeline_v2 import run_pipeline_v2_enhanced

stores = [
    {"id": "cs001", "name": "Hub A", "lat": 28.45, "lon": 77.02, "capacity": 1000, "certified": True, "open": True},
    {"id": "cs002", "name": "Hub B", "lat": 28.47, "lon": 77.04, "capacity": 200, "certified": True, "open": False},
]

shipment = {
    "shipment_id": "vax_001",
    "product_type": "vaccines",
    "safe_min_temp": 2,
    "safe_max_temp": 8,
    "cargo_value_inr": 500000,
    "doses": 250,
    "current_lat": 28.4595,
    "current_lon": 77.0266,
}

sim = TruckSimulator(shipment)
telemetry, risk, decision, forecast = run_pipeline_v2_enhanced(
    shipment,
    simulator=sim,
    stores=stores,
    forecast_horizon_min=30,
    delta_t=2.0,
)
```

### 8.3 Batch Processing

```python
from pipeline_v2 import run_pipeline_v2_batch

results = run_pipeline_v2_batch(shipments, simulators=simulators, delta_t=2.0)
for telemetry, risk, decision in results:
    pass
```

## 9. Data Contracts for Store-Aware Diversion

Required shipment fields for best results:

- `shipment_id`
- `cargo_value_inr`
- `doses` (or `needed_capacity`)
- `current_lat` and `current_lon` (or `lat` and `lon`)

Store fields expected:

- `id`
- `name`
- `lat`
- `lon`
- `capacity`
- `open`
- `certified`

## 10. Validation and Tests

Current V2 tests validated successfully:

```bash
python -m pytest risk_engine_v2/tests decision_engine_v2/tests simulation_v2/tests
```

Result at time of writing: `64 passed`.

## 11. Integration Checklist for Developers

1. Keep one persistent `TruckSimulator` per shipment (do not recreate every tick).
2. Feed each shipment tick into `run_pipeline_v2` or `run_pipeline_v2_enhanced`.
3. Pass `delta_t` consistently with actual event interval.
4. If using store-aware diversion, provide shipment location and doses plus valid store data.
5. Use `forecast_horizon_min` from UI slider for predictive behavior.
6. Display decision math fields (`expected_loss_continue`, `total_diversion_cost`, `saving`) for explainability.
7. Use `reset_tracking(shipment_id)` in risk/decision modules when a shipment session is completed.

## 12. Known Integration Limits

- Offline gateway buffering/replay is not part of these engines and should be handled by gateway/API layer.
- Driver ack workflow and SOP/RAG endpoints are integration-layer concerns, not engine internals.
- Forecast currently uses linear regression over rolling history; tune horizon and thresholds in API/UI policy.

## 13. Recommended API Surface

For clean integration, expose these backend endpoints around the V2 core:

1. `POST /api/v2/tick` -> wraps `run_pipeline_v2_enhanced`
2. `GET /api/v2/predict?shipment_id=...&horizon=...` -> returns forecast payload
3. `GET /api/v2/cold_stores` -> store registry for diversion selector
4. `POST /api/v2/mark_store` -> toggles store open/closed for demo and ops

---

Report owner: V2 engine integration

Applies to:

- `simulation_v2/*`
- `risk_engine_v2/*`
- `decision_engine_v2/*`
- `pipeline_v2.py`
