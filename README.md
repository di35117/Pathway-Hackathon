<div align="center">

# ❄️ LiveCold — Real-Time Cold Chain Intelligence Platform

**AI-powered cold chain monitoring, risk prediction, and autonomous diversion — built on [Pathway](https://pathway.com/) streaming framework.**

[![Docker](https://img.shields.io/badge/Docker-tarun1948%2Flivecold%3Av2-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/tarun1948/livecold)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)]()
[![Pathway](https://img.shields.io/badge/Pathway-Streaming-FF6B35?logo=data:image/svg+xml;base64,PHN2Zy8+&logoColor=white)](https://pathway.com/)
[![Gemini](https://img.shields.io/badge/Gemini-LLM-8E75B2?logo=google&logoColor=white)]()

</div>

---

## 🎯 Problem

India loses **₹63,000 crore/year** (~$7.5B) in perishable food waste during transit. Vaccines, dairy, seafood, and frozen goods require precise temperature control — yet most cold chain logistics rely on **manual monitoring** with **delayed reactions**.

**LiveCold** solves this with a **real-time streaming intelligence platform** that:
- 🌡️ Continuously monitors temperature, GPS, reefer status, and door events
- 🧠 Predicts spoilage risk using a cost-benefit decision engine
- 🚚 Autonomously recommends diversions when cargo is at risk
- 📋 Generates SOP-compliant action checklists using RAG + Gemini LLM

---

## 🏗️ System Architecture

```mermaid
flowchart TB
    subgraph SIMULATORS["🚚 IoT Simulators (25 Shipments)"]
        TS["🌡️ Temp Sensor"]
        GPS["📍 GPS Tracker"]
        RF["❄️ Reefer Unit"]
        DR["🚪 Door Sensor"]
    end

    subgraph MQTT["📡 MQTT Broker (Mosquitto)"]
        M1["livecold/temp"]
        M2["livecold/gps"]
        M3["livecold/reefer"]
        M4["livecold/door"]
    end

    subgraph PIPELINE["⚙️ Decision Engine"]
        RISK["Risk Model<br/>P(spoilage)"]
        DIV["Diversion Optimizer<br/>cost vs loss"]
        MET["Metrics Engine<br/>₹ saved, CO₂"]
    end

    subgraph RAG["📚 Pathway RAG Pipeline"]
        FS["pw.io.fs.read<br/>SOP Documents"]
        REST["pw.io.http.rest_connector<br/>REST API :8765"]
        LLM["Gemini LLM<br/>SOP Checklists"]
    end

    subgraph DASH["🌐 Dashboard (:5050)"]
        MAP["Live Map<br/>(Leaflet.js)"]
        ALR["Alert Panel<br/>+ SOP Actions"]
        KPI["KPI Metrics Bar"]
        SSE["Real-time SSE"]
    end

    TS --> M1
    GPS --> M2
    RF --> M3
    DR --> M4

    M1 & M2 --> PIPELINE
    M3 & M4 --> DASH

    PIPELINE --> DASH
    RISK --> DIV --> MET

    FS --> LLM
    REST --> LLM
    LLM --> DASH

    style SIMULATORS fill:#1a2332,stroke:#4fc3f7,color:#e0e6f0
    style MQTT fill:#1a2332,stroke:#ffc107,color:#e0e6f0
    style PIPELINE fill:#1a2332,stroke:#ff5252,color:#e0e6f0
    style RAG fill:#1a2332,stroke:#81d4fa,color:#e0e6f0
    style DASH fill:#1a2332,stroke:#4caf50,color:#e0e6f0
```

---

## 🔄 Data Flow

```mermaid
sequenceDiagram
    participant S as 🚚 Simulator
    participant M as 📡 MQTT
    participant P as ⚙️ Pipeline
    participant R as 📚 Pathway RAG
    participant D as 🌐 Dashboard

    loop Every 2 seconds
        S->>M: Temp, GPS, Reefer, Door events
        M->>P: livecold/temp, livecold/gps
        M->>D: livecold/* (all topics)
        P->>P: Risk Model → Diversion Optimizer
        alt Risk > 60%
            P->>P: 🚨 DIVERT decision
            D->>R: POST /v2/answer (SOP query)
            R->>R: Gemini LLM + SOP context
            R-->>D: SOP checklist (§3.2, §4.1...)
            D->>D: Show alert + SOP in panel
        else Risk ≤ 60%
            P->>P: ✅ CONTINUE
        end
        D->>D: Update map, metrics, shipment list
    end
```

---

## ✨ Key Features

| Feature | Technology | Description |
|---------|-----------|-------------|
| **Streaming RAG** | Pathway + Gemini | Live SOP document monitoring with LLM-powered Q&A |
| **Risk Prediction** | Custom ML model | Real-time P(spoilage) from temp deviation + exposure time |
| **Diversion Engine** | Cost optimizer | Automated divert/continue using `expected_loss vs diversion_cost` |
| **Live Dashboard** | Flask + Leaflet.js + SSE | Real-time map, alerts, KPIs with server-sent events |
| **Multi-stream IoT** | MQTT + Paho | 25 shipments × 4 sensor streams (temp, GPS, reefer, door) |
| **SOP Compliance** | RAG + Prompt Engineering | Auto-generated action checklists citing SOP §sections |
| **Metrics Tracking** | Pathway Tables | ₹ cargo saved, CO₂ delta, diversion rate, latency |

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
# 1. Clone
git clone https://github.com/tarun1948/livecold.git
cd livecold

# 2. Create .env
echo "GOOGLE_API_KEY=your_gemini_key" > .env

# 3. Run
docker-compose up -d

# Dashboard: http://localhost:5050
# RAG API:   http://localhost:8765
```

### Local Development

```bash
# Prerequisites: Python 3.11, Mosquitto MQTT broker

# 1. Create virtual environment
python3.11 -m venv .venv-slim
source .venv-slim/bin/activate
pip install -r requirements-slim.txt

# 2. Start Mosquitto
mosquitto -c mosquitto.conf -d

# 3. Run all components
./replay.sh
# Or individually:
python main.py rag          # Pathway RAG (port 8765)
python main.py dashboard    # Dashboard (port 5050)
python main.py mqtt         # MQTT Decision Pipeline
python main.py sim-all      # All 4 simulators
```

---

## 📂 Project Structure

```
livecold/
├── main.py                      # Unified CLI entry point
├── pathway_rag_pipeline.py      # 📚 Pathway RAG (streaming SOP + REST API)
├── pathway_metrics_pipeline.py  # 📊 Pathway metrics aggregation
├── pathway_integrated_full.py   # 🔗 Full integrated Pathway pipeline
├── pathway_mqtt_bridge.py       # 🌉 Pathway ↔ MQTT bridge
│
├── dashboard/
│   ├── app.py                   # 🌐 Flask dashboard + MQTT subscriber
│   └── templates/index.html     # Live map, alerts, metrics UI
│
├── pipeline/
│   └── livecold_pipeline.py     # ⚙️ MQTT decision pipeline
│
├── decision_engine/
│   ├── evaluator.py             # Main intelligence entry point
│   ├── risk_model.py            # P(spoilage) calculator
│   ├── diversion_optimizer.py   # Cost-benefit diversion logic
│   └── metrics_engine.py        # System-wide metrics tracker
│
├── sim/
│   ├── temp_simulator.py        # 🌡️ Temperature sensor simulator
│   ├── gps_simulator.py         # 📍 GPS tracker simulator
│   ├── reefer_simulator.py      # ❄️ Reefer unit telemetry
│   ├── door_simulator.py        # 🚪 Door open/shock events
│   ├── shipment_factory.py      # Generates 25 diverse shipments
│   └── config.py                # Simulation parameters
│
├── watched_docs/
│   └── cold_chain_SOP.txt       # SOP document (indexed by RAG)
│
├── Dockerfile                   # Multi-component Docker image
├── docker-compose.yml           # Full stack with Mosquitto
├── docker-entrypoint.sh         # Starts all 5 components
├── replay.sh                    # Local demo launcher
├── requirements-slim.txt        # Python dependencies
└── mosquitto.conf               # MQTT broker config
```

---

## 🧠 Decision Engine Logic

```
┌─────────────────────────────────────────────────┐
│              SHIPMENT STATE INPUT                │
│  temp=12.5°C | safe_max=8°C | exposure=15min    │
│  cargo_value=₹8,00,000 | hub_dist=45km          │
└──────────────────┬──────────────────────────────┘
                   ▼
         ┌─────────────────┐
         │   RISK MODEL    │
         │  P(spoilage) =  │
         │  f(deviation,   │
         │    exposure,    │
         │    sensitivity) │
         │  → 0.85 (85%)   │
         └────────┬────────┘
                  ▼
    ┌──────────────────────────┐
    │   DIVERSION OPTIMIZER    │
    │                          │
    │  expected_loss = ₹6,80,000│
    │  diversion_cost = ₹3,600 │
    │  net_saving = ₹6,76,400  │
    │                          │
    │  → DIVERT ✅              │
    └──────────────────────────┘
```

---

## 📡 API Reference

### Pathway RAG — SOP Q&A

```bash
POST http://localhost:8765/v2/answer
Content-Type: application/json

{"prompt": "What to do if temperature exceeds threshold for dairy?"}
```

**Response:** SOP-compliant checklist citing §sections with action items.

### Dashboard APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Live dashboard UI |
| `/api/shipments` | GET | All active shipments with state |
| `/api/alerts` | GET | Recent alerts (last 50) |
| `/api/metrics` | GET | System-wide KPIs |
| `/api/stream` | GET | Server-Sent Events (real-time) |

---

## 🔧 Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `GOOGLE_API_KEY` | — | Gemini API key (required for RAG) |
| `GOOGLE_API_KEY_2` | — | Backup API key (rate-limit rotation) |
| `MQTT_HOST` | `localhost` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |

---

## 📊 Demo Metrics (25 shipments × 5 minutes)

| Metric | Value |
|--------|-------|
| Events Processed | 8,375+ |
| Cargo Value Monitored | ₹9.2 Billion |
| Cargo Value Saved | ₹1.86 Billion |
| Diversions Triggered | 2,115 (25.2%) |
| High-Risk Events | 2,119 |
| CO₂ Delta | 87,686 kg |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Streaming Engine** | Pathway (tables, UDFs, connectors) |
| **LLM** | Google Gemini (via LiteLLM) |
| **Messaging** | MQTT (Eclipse Mosquitto) |
| **Dashboard** | Flask + Leaflet.js + SSE |
| **Embeddings** | Sentence-Transformers (local) |
| **Tokenizer** | tiktoken |
| **Containerization** | Docker + Docker Compose |

---

## 👥 Team

Built for the **Pathway Hackathon** — demonstrating real-time streaming AI for logistics.

---

## 📄 License

MIT
