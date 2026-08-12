"""
Integration tests for the live MQTT pipeline.

Drives the real `on_message` handler with synthetic MQTT payloads across all
four telemetry streams and asserts on what gets published to
livecold/decisions. No broker required — the client is a stub that captures
publishes.
"""
import json
import os
import sys
import time
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

import pipeline.livecold_pipeline as P
from datetime import UTC


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, json.loads(payload)))

    def decisions(self):
        return [p for t, p in self.published if t == P.DECISION_TOPIC]

    def on_topic(self, topic):
        return [p for t, p in self.published if t == topic]


@pytest.fixture
def client():
    c = FakeClient()
    P.pipeline_client = c
    P.ENGINE = "v2"
    P.reset_pipeline_state()
    yield c
    P.reset_pipeline_state()
    P.pipeline_client = None


def send(topic, payload):
    P.on_message(
        None, None,
        types.SimpleNamespace(topic=topic, payload=json.dumps(payload).encode()),
    )


def gps(sid="SHP_1", **kw):
    send(P.GPS_TOPIC, {"shipment_id": sid, "lat": 28.61, "lon": 77.20,
                       "speed_kmph": 50, "origin": "Delhi",
                       "destination": "Jaipur",
                       "eta_minutes_remaining": 240, **kw})


def temp(sid="SHP_1", t=4.0, product="Dairy", value=800_000, **kw):
    send(P.TEMP_TOPIC, {"shipment_id": sid, "temp_c": t, "product_type": product,
                        "cargo_value_inr": value,
                        "nearest_hub_distance_km": 25, **kw})


class TestSynchronisationGate:
    def test_no_decision_without_gps(self, client):
        temp()
        assert client.decisions() == []

    def test_no_decision_without_temperature(self, client):
        gps()
        assert client.decisions() == []

    def test_decision_once_both_streams_present(self, client):
        gps()
        temp()
        assert len(client.decisions()) == 1


class TestAllFourStreamsFeedTheDecision:
    def test_reefer_stream_reaches_the_compressor_factor(self, client):
        gps()
        send(P.REEFER_TOPIC, {"shipment_id": "SHP_1",
                              "compressor_status": "OFF", "power_draw_kw": 0.0})
        temp(t=9.0)
        d = client.decisions()[-1]
        assert d["compressor_status"] == "OFF"
        assert d["factor_scores"]["compressor"] > 0.5

    def test_door_stream_reaches_the_door_factor(self, client):
        gps()
        send(P.DOOR_TOPIC, {"shipment_id": "SHP_1",
                            "event_type": "door_open", "duration_seconds": 300})
        temp(t=9.0)
        d = client.decisions()[-1]
        assert d["door_status"] == "OPEN"
        assert d["factor_scores"]["door_events"] > 0.5

    def test_door_close_clears_the_factor(self, client):
        gps()
        send(P.DOOR_TOPIC, {"shipment_id": "SHP_1",
                            "event_type": "door_open", "duration_seconds": 300})
        temp(t=9.0)
        send(P.DOOR_TOPIC, {"shipment_id": "SHP_1", "event_type": "door_close"})
        temp(t=9.0)
        assert client.decisions()[-1]["factor_scores"]["door_events"] == 0.0

    def test_all_six_factors_are_reported(self, client):
        gps()
        temp(t=9.0)
        scores = client.decisions()[-1]["factor_scores"]
        assert set(scores) == {
            "temp_deviation", "exposure_time", "eta_pressure",
            "door_events", "compressor", "drift_rate",
        }


class TestSopDrivesTheEngine:
    def test_safe_range_comes_from_the_sop(self, client):
        gps()
        temp(product="Dairy")            # SOP says dairy is 2..6
        d = client.decisions()[-1]
        assert (d["safe_min_temp"], d["safe_max_temp"]) == (2.0, 6.0)

    def test_routing_mode_follows_cargo_once_known(self, client):
        # First message is GPS and carries no cargo type; the mode must correct
        # itself as soon as temperature reveals what is on the truck.
        gps()
        temp(product="Vaccines", value=2_500_000)
        assert client.decisions()[-1]["routing_mode"] == "SAFETY"

    def test_operator_override_is_sticky(self, client):
        gps()
        temp(product="Vaccines")
        send(P.ROUTING_MODE_TOPIC, {"shipment_id": "SHP_1", "mode": "ECO"})
        temp(product="Vaccines")
        assert client.decisions()[-1]["routing_mode"] == "ECO"


class TestAnomalyHandling:
    def test_impossible_reading_produces_no_decision(self, client):
        gps()
        temp(t=4.0)
        before = len(client.decisions())
        temp(t=-999.0)
        assert len(client.decisions()) == before

    def test_anomalies_are_published_for_audit(self, client):
        gps()
        temp(t=4.0)
        temp(t=-999.0)
        events = client.on_topic(P.ANOMALY_TOPIC)
        assert events and events[-1]["layer"] == "L1_BOUNDS"
        assert events[-1]["raw_temp"] == -999.0

    def test_rate_anomaly_substitutes_last_good_reading(self, client):
        gps()
        temp(t=4.0)
        temp(t=40.0)   # electrical step, not thermal
        assert client.decisions()[-1]["temp"] == 4.0


class TestDiversionLifecycle:
    @staticmethod
    def _drive_to_divert(client):
        gps()
        send(P.REEFER_TOPIC, {"shipment_id": "SHP_1",
                              "compressor_status": "OFF", "power_draw_kw": 0.0})
        send(P.DOOR_TOPIC, {"shipment_id": "SHP_1",
                            "event_type": "door_open", "duration_seconds": 300})
        for i in range(30):
            temp(t=6.0 + i * 0.5, product="Vaccines", value=2_500_000)
            time.sleep(0.002)
        return [d for d in client.decisions() if d["recommended_action"] == "DIVERT"]

    def test_diversion_is_reached(self, client):
        assert self._drive_to_divert(client)

    def test_pipeline_selects_the_hub(self, client):
        """Hub selection lives in the pipeline so the driver notification and
        the dashboard proposal can never name different facilities."""
        first = self._drive_to_divert(client)[0]
        hub = first["selected_hub"]
        assert hub["name"] and hub["lat"] and hub["lon"]
        assert hub["distance_km"] >= 0
        assert "eta_minutes" in hub

    def test_diversion_counted_exactly_once(self, client):
        """Regression: a truck above threshold emits DIVERT on every message.
        Counting each tick is what inflated the headline savings figure past the
        total value of cargo on the road."""
        self._drive_to_divert(client)
        assert P.get_metrics()["total_diversions"] == 1

    def test_repeat_diverts_become_monitoring(self, client):
        self._drive_to_divert(client)
        actions = [d["recommended_action"] for d in client.decisions()]
        assert actions.count("DIVERT") == 1
        assert "MONITORING" in actions

    def test_saving_never_exceeds_cargo_value(self, client):
        self._drive_to_divert(client)
        assert P.get_metrics()["cargo_value_saved_inr"] <= 2_500_000


class TestPredictiveOutput:
    def test_forecast_is_guarded_against_short_windows(self, client):
        """Extrapolating 30 minutes from a 2-second window produced 1.8 million
        degrees. The guard must refuse instead of inventing a number."""
        gps()
        for _ in range(5):
            temp(t=9.0)
        f = client.decisions()[-1]["forecast"]
        assert f["predicted_temp"] is None
        assert f["reason"] == "insufficient history"

    def test_forecast_is_bounded_when_it_does_fire(self, client):
        from datetime import datetime, timedelta, timezone
        gps()
        temp(t=6.0)

        # Inject a realistic history: 20 readings over 10 simulated minutes.
        base = datetime.now(UTC) - timedelta(minutes=10)
        P._temp_history["SHP_1"].clear()
        for i in range(20):
            P._temp_history["SHP_1"].append(
                (base + timedelta(seconds=i * 30), 6.0 + i * 0.4)
            )

        telemetry = P._build_telemetry(P.shipment_state["SHP_1"])
        risk = {"exposure_degree_hours": 0.0, "spoilage_probability": 0.0}
        f = P._forecast("SHP_1", telemetry, risk)

        assert f["predicted_temp"] is not None
        current = float(telemetry["temperature"])
        max_delta = P.MAX_FORECAST_RATE_C_MIN * P.FORECAST_HORIZON_MIN
        assert abs(f["predicted_temp"] - current) <= max_delta + 1e-6
        assert f["trend"] in ("rising", "falling", "stable")

    def test_spoilage_probability_is_reported(self, client):
        gps()
        temp(t=9.0)
        d = client.decisions()[-1]
        assert 0.0 <= d["spoilage_probability"] <= 1.0
        assert d["exposure_degree_hours"] >= 0.0


class TestLatency:
    def test_latency_is_measured_per_decision(self, client):
        gps()
        temp()
        d = client.decisions()[-1]
        assert d["pipeline_latency_ms"] >= 0
        assert d["decision_compute_ms"] >= 0

    def test_decisions_are_sub_second(self, client):
        gps()
        for _ in range(30):
            temp(t=5.0)
        m = P.get_metrics()
        assert m["latency_p95_ms"] < 1000, "pipeline latency exceeded 1s"


class TestEngineSelection:
    def test_v2_is_the_default_engine(self, client):
        gps()
        temp()
        assert client.decisions()[-1]["engine"] == "v2"

    def test_v1_engine_still_runs(self, client):
        P.ENGINE = "v1"
        gps()
        temp(t=12.0)
        d = client.decisions()[-1]
        assert d["engine"] == "v1"
        assert 0.0 <= d["risk_probability"] <= 1.0
        assert d["recommended_action"] in ("CONTINUE", "DIVERT", "MONITORING")


class TestMultipleShipments:
    def test_shipments_are_tracked_independently(self, client):
        for sid in ("SHP_1", "SHP_2", "SHP_3"):
            gps(sid=sid)
            temp(sid=sid, t=4.0)
        assert len(P.shipment_state) == 3
        ids = {d["shipment_id"] for d in client.decisions()}
        assert ids == {"SHP_1", "SHP_2", "SHP_3"}

    def test_twenty_five_concurrent_shipments(self, client):
        """The resume claims 25+ concurrent shipments; this pins it."""
        for i in range(1, 26):
            sid = f"SHP_{i}"
            gps(sid=sid)
            temp(sid=sid, t=4.0 + (i % 5))
        assert len(P.shipment_state) == 25
        assert P.get_metrics()["total_events"] == 25
