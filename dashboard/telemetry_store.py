"""
LiveCold Telemetry Store — SQLite persistence for IoT telemetry and decisions.

Why this exists: dashboard state used to live entirely in Python dicts, so every
restart lost the fleet's history and no shipment could be audited after delivery.
Cold-chain customers need a durable temperature record per consignment — that is
the compliance artefact they actually pay for.

Design notes
------------
Writes are batched on a background thread. Telemetry arrives at roughly 50
events/second across the fleet; committing each one individually would make
SQLite's per-transaction fsync the bottleneck and stall the MQTT callback thread.
Events are queued, then flushed in a single transaction every FLUSH_INTERVAL
seconds or once BATCH_SIZE rows accumulate.

WAL mode lets the Flask read path query while the writer thread commits, which a
default-journal SQLite would serialise.

Retention is enforced by row count per shipment rather than by time, so a demo
left running overnight cannot fill the disk.
"""

import os
import queue
import sqlite3
import threading
import time
from datetime import datetime, UTC

DB_PATH = os.path.join(os.path.dirname(__file__), "livecold.db")

BATCH_SIZE = 200
FLUSH_INTERVAL_SEC = 2.0
QUEUE_MAX = 20_000
MAX_ROWS_PER_SHIPMENT = 5_000
PRUNE_EVERY_SEC = 300

_write_queue = queue.Queue(maxsize=QUEUE_MAX)
_writer_thread = None
_lock = threading.Lock()
_stats = {"queued": 0, "written": 0, "dropped": 0, "batches": 0, "pruned": 0}


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # WAL lets readers proceed during writes; NORMAL sync trades a small
    # durability window for a large throughput gain, which is the right call for
    # telemetry that is already reproducible from the stream.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_telemetry_db():
    """Create telemetry tables and indexes. Idempotent."""
    conn = _connect()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id   TEXT NOT NULL,
            ts            TEXT NOT NULL,
            temp_c        REAL,
            lat           REAL,
            lon           REAL,
            speed_kmph    REAL,
            door_status   TEXT,
            compressor    TEXT,
            product_type  TEXT
        )
    """)
    # Every read path is "latest N for one shipment", so index that directly.
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_telemetry_shipment_ts
        ON telemetry (shipment_id, id DESC)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id          TEXT NOT NULL,
            ts                   TEXT NOT NULL,
            action               TEXT,
            risk_probability     REAL,
            risk_level           TEXT,
            confidence           TEXT,
            temp_c               REAL,
            spoilage_probability REAL,
            expected_loss_inr    REAL,
            diversion_cost_inr   REAL,
            net_saving_inr       REAL,
            co2_delta_kg         REAL,
            routing_mode         TEXT,
            selected_hub         TEXT,
            decision_reason      TEXT,
            engine               TEXT,
            latency_ms           REAL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_shipment_ts
        ON decisions (shipment_id, id DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_action
        ON decisions (action)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS anomalies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id TEXT NOT NULL,
            ts          TEXT NOT NULL,
            layer       TEXT,
            reason      TEXT,
            raw_temp    REAL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_anomalies_shipment
        ON anomalies (shipment_id, id DESC)
    """)

    conn.commit()
    conn.close()


def _enqueue(table, row):
    """Queue a row for the writer thread. Never blocks the caller."""
    try:
        _write_queue.put_nowait((table, row))
        with _lock:
            _stats["queued"] += 1
    except queue.Full:
        # Dropping telemetry beats stalling MQTT ingest. The live view is
        # unaffected; only the durable history loses a sample.
        with _lock:
            _stats["dropped"] += 1


def record_telemetry(shipment_id, state):
    _enqueue("telemetry", (
        shipment_id,
        datetime.now(UTC).isoformat(),
        state.get("temp"),
        state.get("lat"),
        state.get("lon"),
        state.get("speed_kmph"),
        state.get("door_status"),
        state.get("compressor_status"),
        state.get("product_type"),
    ))


def record_decision(shipment_id, decision):
    hub = decision.get("selected_hub") or {}
    _enqueue("decisions", (
        shipment_id,
        datetime.now(UTC).isoformat(),
        decision.get("recommended_action"),
        decision.get("risk_probability"),
        decision.get("risk_level"),
        decision.get("confidence"),
        decision.get("temp"),
        decision.get("spoilage_probability"),
        decision.get("expected_loss_inr"),
        decision.get("diversion_cost_inr"),
        decision.get("net_saving_inr"),
        decision.get("co2_delta_kg"),
        decision.get("routing_mode"),
        hub.get("name") if isinstance(hub, dict) else None,
        decision.get("decision_reason"),
        decision.get("engine"),
        decision.get("pipeline_latency_ms"),
    ))


def record_anomaly(shipment_id, layer, reason, raw_temp=None):
    _enqueue("anomalies", (
        shipment_id,
        datetime.now(UTC).isoformat(),
        layer, reason, raw_temp,
    ))


_INSERTS = {
    "telemetry": (
        "INSERT INTO telemetry "
        "(shipment_id, ts, temp_c, lat, lon, speed_kmph, door_status, "
        " compressor, product_type) VALUES (?,?,?,?,?,?,?,?,?)"
    ),
    "decisions": (
        "INSERT INTO decisions "
        "(shipment_id, ts, action, risk_probability, risk_level, confidence, "
        " temp_c, spoilage_probability, expected_loss_inr, diversion_cost_inr, "
        " net_saving_inr, co2_delta_kg, routing_mode, selected_hub, "
        " decision_reason, engine, latency_ms) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    ),
    "anomalies": (
        "INSERT INTO anomalies (shipment_id, ts, layer, reason, raw_temp) "
        "VALUES (?,?,?,?,?)"
    ),
}


def _flush(conn, batch):
    """Write one batch inside a single transaction."""
    if not batch:
        return 0
    grouped = {}
    for table, row in batch:
        grouped.setdefault(table, []).append(row)

    cur = conn.cursor()
    written = 0
    for table, rows in grouped.items():
        cur.executemany(_INSERTS[table], rows)
        written += len(rows)
    conn.commit()
    return written


def _prune(conn):
    """Keep only the most recent MAX_ROWS_PER_SHIPMENT rows per shipment."""
    cur = conn.cursor()
    removed = 0
    for table in ("telemetry", "decisions"):
        cur.execute(f"""
            DELETE FROM {table}
            WHERE id IN (
                SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (
                        PARTITION BY shipment_id ORDER BY id DESC
                    ) AS rn
                    FROM {table}
                ) WHERE rn > ?
            )
        """, (MAX_ROWS_PER_SHIPMENT,))
        removed += cur.rowcount
    conn.commit()
    return removed


def _writer_loop():
    """Background thread: drain the queue in batches."""
    conn = _connect()
    last_prune = time.time()
    batch = []
    last_flush = time.time()

    while True:
        try:
            timeout = max(0.05, FLUSH_INTERVAL_SEC - (time.time() - last_flush))
            try:
                batch.append(_write_queue.get(timeout=timeout))
            except queue.Empty:
                pass

            due = (len(batch) >= BATCH_SIZE
                   or (batch and time.time() - last_flush >= FLUSH_INTERVAL_SEC))
            if due:
                written = _flush(conn, batch)
                with _lock:
                    _stats["written"] += written
                    _stats["batches"] += 1
                batch = []
                last_flush = time.time()

            if time.time() - last_prune >= PRUNE_EVERY_SEC:
                pruned = _prune(conn)
                with _lock:
                    _stats["pruned"] += pruned
                last_prune = time.time()

        except sqlite3.Error:
            # A failed batch must not kill the writer; drop it and carry on.
            batch = []
            last_flush = time.time()
            try:
                conn.rollback()
            except sqlite3.Error:
                conn = _connect()
        except Exception:
            batch = []


def start_writer():
    """Start the background writer once."""
    global _writer_thread
    if _writer_thread and _writer_thread.is_alive():
        return
    init_telemetry_db()
    _writer_thread = threading.Thread(
        target=_writer_loop, daemon=True, name="TelemetryWriter"
    )
    _writer_thread.start()


def flush_now():
    """Drain and commit synchronously. Used by tests."""
    conn = _connect()
    batch = []
    while True:
        try:
            batch.append(_write_queue.get_nowait())
        except queue.Empty:
            break
    written = _flush(conn, batch)
    with _lock:
        _stats["written"] += written
    conn.close()
    return written


# ── Read paths ──────────────────────────────────────────────────

def get_history(shipment_id, limit=200):
    """Temperature history for one shipment, oldest first."""
    conn = _connect()
    rows = conn.execute("""
        SELECT ts, temp_c, lat, lon, speed_kmph, door_status, compressor
        FROM telemetry WHERE shipment_id = ? ORDER BY id DESC LIMIT ?
    """, (shipment_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_decisions(shipment_id, limit=100):
    conn = _connect()
    rows = conn.execute("""
        SELECT * FROM decisions WHERE shipment_id = ? ORDER BY id DESC LIMIT ?
    """, (shipment_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_shipment_anomalies(shipment_id, limit=50):
    conn = _connect()
    rows = conn.execute("""
        SELECT ts, layer, reason, raw_temp FROM anomalies
        WHERE shipment_id = ? ORDER BY id DESC LIMIT ?
    """, (shipment_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_compliance(shipment_id, safe_min, safe_max):
    """
    Fraction of stored readings inside the safe band.

    Computed in SQL so it scales with row count rather than being pulled into
    Python. This is the number that goes on the customer's delivery report.
    """
    conn = _connect()
    row = conn.execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN temp_c BETWEEN ? AND ? THEN 1 ELSE 0 END) AS in_range,
               MIN(temp_c) AS min_temp,
               MAX(temp_c) AS max_temp,
               AVG(temp_c) AS avg_temp
        FROM telemetry
        WHERE shipment_id = ? AND temp_c IS NOT NULL
    """, (safe_min, safe_max, shipment_id)).fetchone()
    conn.close()

    total = row["total"] or 0
    in_range = row["in_range"] or 0
    return {
        "total_readings": total,
        "readings_in_range": in_range,
        "readings_out_of_range": total - in_range,
        "compliance_pct": round(in_range / total * 100, 2) if total else None,
        "min_temp": row["min_temp"],
        "max_temp": row["max_temp"],
        "avg_temp": round(row["avg_temp"], 2) if row["avg_temp"] is not None else None,
    }


def get_fleet_summary():
    """Aggregate view across all persisted shipments."""
    conn = _connect()
    telem = conn.execute("""
        SELECT COUNT(*) AS rows, COUNT(DISTINCT shipment_id) AS shipments
        FROM telemetry
    """).fetchone()
    decisions = conn.execute("""
        SELECT action, COUNT(*) AS n, SUM(net_saving_inr) AS saved
        FROM decisions GROUP BY action
    """).fetchall()
    anomalies = conn.execute("""
        SELECT layer, COUNT(*) AS n FROM anomalies GROUP BY layer
    """).fetchall()
    conn.close()

    return {
        "telemetry_rows": telem["rows"],
        "shipments_tracked": telem["shipments"],
        "decisions_by_action": {r["action"]: r["n"] for r in decisions},
        "saving_by_action": {r["action"]: r["saved"] for r in decisions},
        "anomalies_by_layer": {r["layer"]: r["n"] for r in anomalies},
    }


def get_stats():
    with _lock:
        s = dict(_stats)
    s["queue_depth"] = _write_queue.qsize()
    return s
