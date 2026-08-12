"""
Tests for the SQLite telemetry store — the durable compliance record.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from dashboard import telemetry_store as store


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the store at a throwaway database for each test."""
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "test.db"))
    store.init_telemetry_db()
    # Drain anything a previous test left queued.
    while True:
        try:
            store._write_queue.get_nowait()
        except Exception:
            break
    yield


def _telemetry(sid, temp, **kw):
    store.record_telemetry(sid, {
        "temp": temp, "lat": 28.6, "lon": 77.2, "speed_kmph": 50,
        "door_status": "CLOSED", "compressor_status": "RUNNING",
        "product_type": "Dairy", **kw,
    })


class TestSchema:
    def test_tables_created(self):
        conn = store._connect()
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        conn.close()
        assert {"telemetry", "decisions", "anomalies"} <= names

    def test_indexes_created(self):
        conn = store._connect()
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        conn.close()
        assert "idx_telemetry_shipment_ts" in idx
        assert "idx_decisions_shipment_ts" in idx

    def test_init_is_idempotent(self):
        store.init_telemetry_db()
        store.init_telemetry_db()  # must not raise


class TestPersistence:
    def test_telemetry_round_trip(self):
        for i in range(50):
            _telemetry("SHP_1", 3.0 + i * 0.1)
        assert store.flush_now() == 50

        history = store.get_history("SHP_1")
        assert len(history) == 50
        # Oldest first, so charts can plot straight through.
        assert history[0]["temp_c"] < history[-1]["temp_c"]

    def test_history_limit_returns_most_recent(self):
        for i in range(100):
            _telemetry("SHP_1", float(i))
        store.flush_now()

        recent = store.get_history("SHP_1", limit=10)
        assert len(recent) == 10
        assert recent[-1]["temp_c"] == 99.0

    def test_shipments_are_isolated(self):
        _telemetry("SHP_1", 4.0)
        _telemetry("SHP_2", 9.0)
        store.flush_now()

        assert len(store.get_history("SHP_1")) == 1
        assert store.get_history("SHP_2")[0]["temp_c"] == 9.0

    def test_decision_round_trip(self):
        store.record_decision("SHP_1", {
            "recommended_action": "DIVERT", "risk_probability": 0.81,
            "risk_level": "HIGH", "confidence": "HIGH", "temp": 12.0,
            "spoilage_probability": 0.4, "expected_loss_inr": 500_000,
            "diversion_cost_inr": 30_000, "net_saving_inr": 470_000,
            "co2_delta_kg": 7.5, "routing_mode": "SAFETY",
            "selected_hub": {"name": "FrostLine Delhi"},
            "decision_reason": "Compressor + drift", "engine": "v2",
            "pipeline_latency_ms": 2.1,
        })
        store.flush_now()

        d = store.get_decisions("SHP_1")[0]
        assert d["action"] == "DIVERT"
        assert d["selected_hub"] == "FrostLine Delhi"
        assert d["routing_mode"] == "SAFETY"
        assert d["engine"] == "v2"

    def test_anomaly_round_trip(self):
        store.record_anomaly("SHP_1", "L1_BOUNDS", "Temp -999C impossible", -999.0)
        store.flush_now()

        a = store.get_shipment_anomalies("SHP_1")[0]
        assert a["layer"] == "L1_BOUNDS"
        assert a["raw_temp"] == -999.0

    def test_survives_a_reconnect(self):
        """The point of persistence: a restart must not lose the record."""
        _telemetry("SHP_1", 4.0)
        store.flush_now()
        # A fresh connection stands in for a process restart.
        assert len(store.get_history("SHP_1")) == 1


class TestCompliance:
    def test_counts_in_range_not_merely_present(self):
        """Regression: compliance used to count readings that existed, so a
        truck at 30C the whole way reported 100% compliant."""
        for _ in range(7):
            _telemetry("SHP_1", 4.0)     # inside 2..6
        for _ in range(3):
            _telemetry("SHP_1", 30.0)    # far outside
        store.flush_now()

        c = store.get_compliance("SHP_1", 2, 6)
        assert c["total_readings"] == 10
        assert c["readings_in_range"] == 7
        assert c["readings_out_of_range"] == 3
        assert c["compliance_pct"] == 70.0

    def test_fully_breached_shipment_reports_zero(self):
        for _ in range(5):
            _telemetry("SHP_1", 30.0)
        store.flush_now()
        assert store.get_compliance("SHP_1", 2, 6)["compliance_pct"] == 0.0

    def test_boundary_values_count_as_in_range(self):
        _telemetry("SHP_1", 2.0)
        _telemetry("SHP_1", 6.0)
        store.flush_now()
        assert store.get_compliance("SHP_1", 2, 6)["compliance_pct"] == 100.0

    def test_reports_min_max_avg(self):
        for t in (2.0, 4.0, 6.0):
            _telemetry("SHP_1", t)
        store.flush_now()

        c = store.get_compliance("SHP_1", 2, 6)
        assert c["min_temp"] == 2.0
        assert c["max_temp"] == 6.0
        assert c["avg_temp"] == 4.0

    def test_no_data_reports_none(self):
        c = store.get_compliance("GHOST", 2, 6)
        assert c["total_readings"] == 0
        assert c["compliance_pct"] is None


class TestFleetSummary:
    def test_aggregates_across_shipments(self):
        for sid in ("SHP_1", "SHP_2"):
            for _ in range(5):
                _telemetry(sid, 4.0)
        store.record_decision("SHP_1", {
            "recommended_action": "DIVERT", "net_saving_inr": 100_000,
        })
        store.record_anomaly("SHP_2", "L2_RATE", "spike", 40.0)
        store.flush_now()

        s = store.get_fleet_summary()
        assert s["telemetry_rows"] == 10
        assert s["shipments_tracked"] == 2
        assert s["decisions_by_action"]["DIVERT"] == 1
        assert s["anomalies_by_layer"]["L2_RATE"] == 1


class TestBackpressure:
    def test_queue_overflow_drops_rather_than_blocking(self, monkeypatch):
        """Dropping a telemetry sample beats stalling the MQTT ingest thread."""
        import queue as _q
        monkeypatch.setattr(store, "_write_queue", _q.Queue(maxsize=5))

        for i in range(50):
            _telemetry("SHP_1", float(i))

        assert store.get_stats()["dropped"] > 0

    def test_stats_report_queue_depth(self):
        _telemetry("SHP_1", 4.0)
        assert "queue_depth" in store.get_stats()
