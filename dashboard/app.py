"""
LiveCold Dashboard - Flask Web Server
Real-time cold-chain monitoring dashboard with live map and metrics.
Subscribes to MQTT for live data and serves a web UI.
"""

import json
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, Response, request
import paho.mqtt.client as mqtt
import queue
import time
import os
import litellm
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dashboard")

app = Flask(__name__, template_folder="templates", static_folder="static")

# ── Global State ────────────────────────────────────────────────
shipments = {}      # shipment_id -> latest state
alerts = []         # recent alerts (last 100)
metrics = {
    "total_events": 0,
    "total_diversions": 0,
    "total_value_monitored": 0,
    "total_value_saved": 0,
    "total_co2_delta": 0,
    "high_risk_events": 0,
}
sse_queue = queue.Queue(maxsize=500)

BROKER = os.getenv("MQTT_HOST", "localhost")
PORT = 1883
# Model fallback list — if one is rate-limited, try the next
GEMINI_MODELS = [
    "gemini/gemini-2.5-flash",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-2.0-flash-lite",
    "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-flash",
]
# Two API keys for rotation
API_KEYS = []
# Track which models are rate-limited (model -> cooldown_until timestamp)
model_cooldowns = {}
# Throttle: only one SOP request at a time
sop_lock = threading.Lock()
sop_in_flight = False

# ── Load SOP document at startup ───────────────────────────────
SOP_CONTEXT = ""
try:
    sop_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watched_docs", "cold_chain_SOP.txt")
    with open(sop_path, "r") as f:
        SOP_CONTEXT = f.read()
    log.info(f"📄 Loaded SOP document ({len(SOP_CONTEXT)} chars)")
except Exception as e:
    log.warning(f"Could not load SOP: {e}")

# Load API keys
for var in ["GOOGLE_API_KEY_imp", "GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GEMINI_API_KEY"]:
    k = os.getenv(var)
    if k and k not in API_KEYS:
        API_KEYS.append(k)
if API_KEYS:
    os.environ["GEMINI_API_KEY"] = API_KEYS[0]
    log.info(f"🔑 Loaded {len(API_KEYS)} API key(s)")

# Cache recent RAG answers to avoid duplicate API calls
import requests as http_requests  # for calling Pathway RAG

rag_cache = {}  # key: alert_type_product_type -> answer

PATHWAY_RAG_URL = "http://localhost:8765/v2/answer"


def get_sop_recommendation(alert_type, product_type, shipment_id, temp):
    """Get SOP recommendation — tries Pathway RAG first, falls back to direct LLM."""
    global sop_in_flight

    # Check cache first
    cache_key = f"{alert_type}_{product_type}".lower()
    if cache_key in rag_cache:
        return rag_cache[cache_key]

    # Throttle: skip if another SOP request is already in-flight
    with sop_lock:
        if sop_in_flight:
            return "Consulting SOP..."
        sop_in_flight = True

    try:
        query = f"What should I do for a {alert_type} alert on {product_type} shipment {shipment_id} at {temp}°C? Give 3-4 action items citing SOP sections."

        # ── PRIMARY: Call Pathway RAG service (DocumentStore + LLM xPack) ──
        try:
            log.info(f"📚 Querying Pathway RAG for {alert_type}/{product_type}")
            resp = http_requests.post(
                PATHWAY_RAG_URL,
                json={"prompt": query},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                # Pathway rest_connector returns result as plain string
                if isinstance(data, str):
                    answer = data.strip()
                elif isinstance(data, dict):
                    answer = (data.get("result") or data.get("response") or "").strip()
                else:
                    answer = ""
                if answer and len(answer) > 20:
                    rag_cache[cache_key] = answer
                    log.info(f"✅ SOP via Pathway RAG for {alert_type}/{product_type}")
                    return answer
        except Exception as e:
            log.warning(f"Pathway RAG unavailable: {str(e)[:60]}, falling back to direct LLM")

        # ── FALLBACK: Direct LLM call with SOP context ──
        if not SOP_CONTEXT or not API_KEYS:
            return "SOP service starting up..."

        prompt = f"""You are a cold chain SOP assistant. Based on the following SOP document, provide a brief numbered checklist (max 4 items) for this alert.

SOP Document:
{SOP_CONTEXT}

ALERT TYPE: {alert_type}
PRODUCT: {product_type}
SHIPMENT: {shipment_id}
TEMPERATURE: {temp}°C

Provide only the most critical 3-4 action items citing SOP sections. Be very concise (one line per item)."""

        now = time.time()
        for api_key in API_KEYS:
            os.environ["GEMINI_API_KEY"] = api_key
            for model in GEMINI_MODELS:
                cooldown_key = f"{model}_{api_key[:8]}"
                if cooldown_key in model_cooldowns and now < model_cooldowns[cooldown_key]:
                    continue
                try:
                    log.info(f"🤖 Fallback: {model}")
                    response = litellm.completion(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        api_key=api_key,
                        timeout=30
                    )
                    answer = response.choices[0].message.content.strip()
                    rag_cache[cache_key] = answer
                    log.info(f"✅ SOP via direct LLM ({model}) for {alert_type}/{product_type}")
                    return answer
                except Exception as e:
                    err = str(e)
                    if "rate" in err.lower() or "429" in err:
                        model_cooldowns[cooldown_key] = now + 60
                        continue
                    elif "404" in err or "not found" in err.lower():
                        model_cooldowns[cooldown_key] = now + 3600
                        continue
                    else:
                        continue

        return "SOP temporarily unavailable. Retrying soon..."
    finally:
        with sop_lock:
            sop_in_flight = False


# ── MQTT Callbacks ──────────────────────────────────────────────

def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode())
    except Exception:
        return

    shipment_id = data.get("shipment_id", "")
    if not shipment_id:
        return

    # Initialize shipment state
    if shipment_id not in shipments:
        shipments[shipment_id] = {
            "shipment_id": shipment_id,
            "lat": None, "lon": None,
            "temp": None, "product_type": "",
            "safe_min_temp": 2, "safe_max_temp": 8,
            "compressor_status": "ON",
            "risk_probability": 0.05,
            "recommended_action": "CONTINUE",
            "origin": "", "destination": "",
            "last_update": "",
            "cargo_value_inr": 0,
            "speed_kmph": 0,
        }

    s = shipments[shipment_id]
    s["last_update"] = datetime.now().isoformat()

    if topic == "livecold/temp":
        s["temp"] = data.get("temp_c")
        s["product_type"] = data.get("product_type", s["product_type"])
        s["safe_min_temp"] = data.get("safe_min_temp", s["safe_min_temp"])
        s["safe_max_temp"] = data.get("safe_max_temp", s["safe_max_temp"])
        s["cargo_value_inr"] = data.get("cargo_value_inr", s["cargo_value_inr"])
        metrics["total_events"] += 1

        # Simple risk calculation for dashboard
        temp = s["temp"]
        safe_max = s["safe_max_temp"]
        safe_min = s["safe_min_temp"]
        if temp is not None:
            if temp > safe_max:
                deviation = temp - safe_max
                risk = min(0.99, 0.5 + deviation * 0.1)
            elif temp < safe_min:
                deviation = safe_min - temp
                risk = min(0.99, 0.5 + deviation * 0.1)
            else:
                risk = 0.05
            s["risk_probability"] = round(risk, 3)

            if risk > 0.6:
                s["recommended_action"] = "DIVERT"
                metrics["high_risk_events"] += 1
                alert = {
                    "shipment_id": shipment_id,
                    "temp": temp,
                    "risk": risk,
                    "action": "DIVERT",
                    "product_type": s["product_type"],
                    "timestamp": s["last_update"],
                    "sop_recommendation": "Consulting SOP..."
                }
                
                # Fetch RAG recommendation in background thread
                def fetch_sop(alert_ref, at, pt, sid, t):
                    answer = get_sop_recommendation(at, pt, sid, t)
                    alert_ref["sop_recommendation"] = answer
                
                threading.Thread(
                    target=fetch_sop,
                    args=(alert, "DIVERT", s["product_type"], shipment_id, temp),
                    daemon=True
                ).start()

                alerts.append(alert)
                if len(alerts) > 100:
                    alerts.pop(0)

                # Push to SSE
                try:
                    sse_queue.put_nowait(json.dumps({"type": "alert", "data": alert}))
                except queue.Full:
                    pass
            else:
                s["recommended_action"] = "CONTINUE"

        metrics["total_value_monitored"] += s.get("cargo_value_inr", 0)

    elif topic == "livecold/gps":
        s["lat"] = data.get("lat")
        s["lon"] = data.get("lon")
        s["speed_kmph"] = data.get("speed_kmph", 0)
        s["origin"] = data.get("origin", s["origin"])
        s["destination"] = data.get("destination", s["destination"])

    elif topic == "livecold/reefer":
        s["compressor_status"] = data.get("compressor_status", "ON")

    elif topic == "livecold/door":
        event_type = data.get("event_type", "")
        if event_type == "door_open":
            alert = {
                "shipment_id": shipment_id,
                "temp": s.get("temp"),
                "risk": s.get("risk_probability", 0),
                "action": f"DOOR OPEN ({data.get('duration_seconds', 0)}s)",
                "product_type": s.get("product_type", ""),
                "timestamp": s["last_update"],
                "sop_recommendation": "Consulting SOP..."
            }
            
            # Fetch SOP for door events too
            def fetch_door_sop(alert_ref, pt, sid, t):
                answer = get_sop_recommendation("DOOR_OPEN", pt, sid, t)
                alert_ref["sop_recommendation"] = answer
            
            threading.Thread(
                target=fetch_door_sop,
                args=(alert, s.get("product_type", ""), shipment_id, s.get("temp", 0)),
                daemon=True
            ).start()
            
            alerts.append(alert)
            if len(alerts) > 100:
                alerts.pop(0)

    # Push state update via SSE
    try:
        sse_queue.put_nowait(json.dumps({"type": "update", "data": s}))
    except queue.Full:
        pass


def start_mqtt():
    client = mqtt.Client()
    client.on_message = on_message
    try:
        client.connect(BROKER, PORT)
        client.subscribe("livecold/#")
        log.info("📡 Dashboard connected to MQTT broker")
        client.loop_forever()
    except Exception as e:
        log.error(f"MQTT connection failed: {e}")


# ── Flask Routes ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/shipments")
def api_shipments():
    return jsonify(list(shipments.values()))


@app.route("/api/alerts")
def api_alerts():
    return jsonify(alerts[-50:])


@app.route("/api/metrics")
def api_metrics():
    m = dict(metrics)
    m["total_shipments"] = len(shipments)
    m["active_diversions"] = sum(1 for s in shipments.values() if s.get("recommended_action") == "DIVERT")
    return jsonify(m)


@app.route("/api/stream")
def api_stream():
    """Server-Sent Events for real-time updates"""
    def generate():
        while True:
            try:
                data = sse_queue.get(timeout=5)
                yield f"data: {data}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
    return Response(generate(), mimetype="text/event-stream")


# ── Entry Point ─────────────────────────────────────────────────

def main():
    # Start MQTT listener in background
    mqtt_thread = threading.Thread(target=start_mqtt, daemon=True)
    mqtt_thread.start()

    print("\n" + "=" * 60)
    print("🌐 LiveCold Dashboard")
    print("=" * 60)
    print("📊 Dashboard: http://localhost:5050")
    print("📡 MQTT: localhost:1883")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=5050, debug=False)


if __name__ == "__main__":
    main()
