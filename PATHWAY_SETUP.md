# 🚀 LiveCold - Complete Pathway Framework Setup

## Pathway Framework Kya Hai?

**Pathway** ek streaming data processing framework hai jo:
- ✅ Real-time data process karta hai (like Apache Flink/Kafka Streams)
- ✅ SQL-like declarative syntax hai
- ✅ Automatically updates detect karta hai
- ✅ Built-in connectors (MQTT, Kafka, Files, etc.)
- ✅ Document Store for RAG built-in hai

---

## 📁 Project Structure

```
livecold-hackathon/
├── pathway_rag_pipeline.py          # Pure Pathway RAG
├── pathway_metrics_pipeline.py      # Pure Pathway metrics
├── pathway_integrated_full.py       # Complete integrated pipeline
├── requirements.txt
├── watched_docs/                    # SOP documents (auto-monitored)
├── data/                            # Input data
│   ├── temp_events.csv             # Temperature sensor data
│   └── shipments.csv               # Shipment metadata
├── output/                          # Pipeline outputs
│   ├── alerts.csv
│   ├── decisions.csv
│   └── final_decisions_with_rag.csv
└── metrics/                         # Computed metrics
    ├── latencies.csv
    ├── alerts.csv
    ├── decisions.csv
    └── global_metrics.csv
```

---

## Step-by-Step Setup

### Step 1: Folder Banao (1 min)

```bash
cd ~
mkdir livecold-hackathon
cd livecold-hackathon

# Required folders
mkdir -p watched_docs data output metrics
```

### Step 2: Install Pathway (3 min)

```bash
# Main packages
pip install "pathway[all]" google-generativeai --break-system-packages

# Verify
python3 -c "import pathway as pw; print('Pathway version:', pw.__version__)"
```

**Expected output:** `Pathway version: 0.x.x`

### Step 3: API Key Setup (1 min)

```bash
# Get Gemini API key from: https://aistudio.google.com/app/apikey
export GEMINI_API_KEY="AIzaSyAC2GhAjgeunrWB8yF6iYg6zy2ajycqXQ4"

# Verify
echo $GEMINI_API_KEY

# Verify
echo $GEMINI_API_KEY
```

### Step 4: Sample Data Banao (2 min)

**Create shipments.csv:**
```bash
cat > data/shipments.csv << 'EOF'
shipment_id,cargo_type,cargo_value_inr,threshold_c,destination
S001,dairy,250000,6.0,Delhi
S002,vegetables,80000,8.0,Mumbai
S003,meat,500000,0.0,Bangalore
S004,fruits,120000,12.0,Chennai
S005,seafood,350000,2.0,Kolkata
EOF
```

**Create temp_events.csv (sample sensor data):**
```bash
cat > data/temp_events.csv << 'EOF'
timestamp,shipment_id,sensor_id,temp_c
1000.0,S001,SENSOR_001,4.5
1005.0,S001,SENSOR_001,5.2
1010.0,S001,SENSOR_001,7.8
1015.0,S001,SENSOR_001,10.5
1020.0,S001,SENSOR_001,12.3
1025.0,S002,SENSOR_002,8.2
1030.0,S002,SENSOR_002,9.1
1035.0,S003,SENSOR_003,0.5
1040.0,S003,SENSOR_003,1.2
1045.0,S003,SENSOR_003,3.5
EOF
```

**Add SOP document:**
```bash
# Download or create SOP
cp sample_SOP.md watched_docs/cold_chain_SOP.txt
```

---

## 🧪 Testing Individual Components

### Test 1: RAG Pipeline Only (5 min)

```bash
python3 pathway_rag_pipeline.py
```

**Expected output:**
```
Building Pathway RAG pipeline...
✓ Watching documents in: ./watched_docs
✓ Using embedder: sentence-transformers/all-MiniLM-L6-v2
✓ DocumentStore created
✓ Using LLM: gemini/gemini-1.5-flash
✓ REST server configured on 0.0.0.0:8765

==================================================
LiveCold RAG Pipeline Running
==================================================
📁 Watching: ./watched_docs
🤖 LLM: gemini/gemini-1.5-flash
📊 Embedder: sentence-transformers/all-MiniLM-L6-v2
🌐 API: http://0.0.0.0:8765

Endpoints:
  POST /v1/pw_ai_answer - Query with LLM
  POST /v1/retrieve - Retrieve documents only
  POST /v1/inputs - List documents
==================================================
```

**Test API (new terminal):**
```bash
curl -X POST http://localhost:8765/v1/pw_ai_answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What should I do if temperature exceeds threshold?",
    "k": 3
  }'
```

**Expected:** JSON response with answer and citations

✅ **If working:** `Ctrl+C` to stop

---

### Test 2: Metrics Pipeline Only (3 min)

```bash
python3 pathway_metrics_pipeline.py
```

**Expected output:**
```
Building Pathway metrics pipeline...
✓ Metrics pipeline built
Writing metrics to ./metrics/...
✓ Metric outputs configured

==================================================
Pathway Metrics Pipeline Running
==================================================
📊 Processing alerts and decisions...
📁 Output: ./metrics/
==================================================
```

**Check output:**
```bash
ls -lh metrics/
# Should show: alerts.csv, decisions.csv, global_metrics.csv, etc.
```

✅ **If files created:** Metrics working!

---

### Test 3: Full Integrated Pipeline (10 min)

```bash
python3 pathway_integrated_full.py
```

**Expected output:**
```
==================================================
Building LiveCold Integrated Pipeline
==================================================

[1/7] Setting up input streams...
  ✓ Input streams configured
[2/7] Computing rolling windows...
  ✓ Rolling windows computed
[3/7] Enriching with metadata...
  ✓ Data enriched
[4/7] Computing risk scores...
  ✓ Risk scores computed
[5/7] Detecting alerts...
  ✓ Alert detection configured
[6/7] Building decision optimizer...
  ✓ Decision optimizer configured
[7/7] Integrating RAG...
Building RAG component...
✓ RAG component ready
  ✓ RAG integrated

[Output] Configuring outputs...
  ✓ Outputs configured
[Metrics] Building metrics...
  ✓ Metrics configured

==================================================
Pipeline Build Complete!
==================================================

==================================================
LiveCold Integrated Pipeline Starting
==================================================
📡 Inputs: ./data/temp_events.csv, ./data/shipments.csv
📁 Documents: ./watched_docs/
📊 Outputs: ./output/
📈 Metrics: ./metrics/
🤖 LLM: gemini/gemini-1.5-flash
==================================================
```

**Check outputs:**
```bash
# Outputs
ls -lh output/
# Should show: alerts.csv, decisions.csv, final_decisions_with_rag.csv

# Metrics
ls -lh metrics/
# Should show: latencies.csv, alerts.csv, decisions.csv, etc.

# View final output
head output/final_decisions_with_rag.csv
```

✅ **If all files created:** Pipeline working!

---

## 🎯 Kaise Kaam Karta Hai?

### 1. RAG Pipeline (`pathway_rag_pipeline.py`)

```python
# Document monitoring (real-time)
documents = pw.io.fs.read(
    path="./watched_docs",
    mode="streaming"  # Auto-detects file changes!
)

# Parser + Splitter
parser = parsers.UnstructuredParser()
splitter = splitters.TokenCountSplitter()

# Embedder (local, free)
embedder = embedders.SentenceTransformerEmbedder(
    model="sentence-transformers/all-MiniLM-L6-v2"
)

# DocumentStore (handles everything!)
doc_store = DocumentStore(
    docs=documents,
    retriever_factory=retriever_factory,
    parser=parser,
    splitter=splitter
)
```

**Key Features:**
- ✅ Automatically reindexes when you edit SOPs
- ✅ REST API for queries
- ✅ Uses Gemini via LiteLLM wrapper
- ✅ Local embeddings (free, fast)

---

### 2. Metrics Pipeline (`pathway_metrics_pipeline.py`)

```python
# Calculate latencies (streaming)
latencies = alerts.select(
    latency_ms=(pw.this.timestamp - pw.this.event_timestamp) * 1000
)

# Aggregate per shipment
shipment_metrics = decisions.groupby(pw.this.shipment_id).reduce(
    total_waste_avoided=pw.reducers.sum(pw.this.waste_avoided_kg),
    total_co2_avoided=pw.reducers.sum(pw.this.net_co2_impact_kg)
)

# Write to CSV (real-time)
pw.io.csv.write(latencies, "./metrics/latencies.csv")
```

**Key Features:**
- ✅ Real-time aggregations
- ✅ Automatic updates
- ✅ Multiple output formats

---

### 3. Integrated Pipeline (`pathway_integrated_full.py`)

**Complete flow:**
```
Sensor Data (CSV/MQTT)
    ↓
Rolling Windows (10 min windows, 30s hop)
    ↓
Join with Metadata
    ↓
Risk Scoring (exponential curve)
    ↓
Alert Trigger (risk > 0.5)
    ↓
Decision Optimizer (divert vs continue)
    ↓
RAG Query → DocumentStore → Gemini LLM
    ↓
Final Output (decisions + RAG recommendations)
    ↓
Outputs: CSV / Kafka
Metrics: Aggregated stats
```

---

## 🔧 Customization

### Change Risk Threshold

In `pathway_integrated_full.py`:
```python
RISK_THRESHOLD = 0.5  # Change this (0.0 to 1.0)
```

### Use MQTT Instead of CSV

Replace:
```python
temp_events = pw.io.csv.read(
    "./data/temp_events.csv",
    schema=TempEventSchema,
    mode="streaming"
)
```

With:
```python
temp_events = pw.io.mqtt.read(
    host="localhost",
    port=1883,
    topic="sensors/temp",
    format="json",
    schema=TempEventSchema
)
```

### Add Kafka Output

In `pathway_integrated_full.py`, uncomment:
```python
pw.io.kafka.write(
    final_output,
    topic="livecold-alerts",
    broker="localhost:9092",
    format="json"
)
```

### Use Different LLM

Change in both files:
```python
# For OpenAI
GEMINI_MODEL = "gpt-4o-mini"
os.environ["OPENAI_API_KEY"] = "sk-..."

# For other providers (via LiteLLM)
GEMINI_MODEL = "anthropic/claude-3-sonnet"
os.environ["ANTHROPIC_API_KEY"] = "..."
```

---

## 📊 Understanding Pathway Concepts

### 1. Streaming Mode
```python
pw.io.fs.read(..., mode="streaming")
```
- Continuously monitors for changes
- Real-time updates
- No need to restart

### 2. Windows
```python
.windowby(
    pw.this.shipment_id,
    window=pw.temporal.sliding(hop=30s, duration=10min)
)
```
- Process time-based chunks
- Sliding windows for continuous updates

### 3. Reducers
```python
.reduce(
    avg_temp=pw.reducers.avg(pw.this.temp),
    max_temp=pw.reducers.max(pw.this.temp)
)
```
- Aggregate functions
- Automatically update with new data

### 4. UDFs (User Defined Functions)
```python
@pw.udf
def compute_risk(temp: float, threshold: float) -> float:
    return 1.0 - exp(-k * (temp - threshold)**2)
```
- Custom logic
- Applied to Pathway tables

---

## 🚨 Troubleshooting

### Error: "GEMINI_API_KEY not set"
```bash
export GEMINI_API_KEY="your-key"
```

### Error: "No module named 'pathway'"
```bash
pip install "pathway[all]" --break-system-packages
```

### Error: "Port 8765 already in use"
```bash
# Kill existing process
lsof -ti:8765 | xargs kill -9

# Or change port
server = DocumentStoreServer(port=8766)
```

### Pipeline not updating
- Check `mode="streaming"` in connectors
- Verify files exist in watched directories
- Check Pathway logs

### Slow first run
- Normal! Models download first time (~90MB)
- Cached for future runs

---

## 🎬 Demo for Judges

### Preparation (5 min before)
```bash
# Start pipeline
python3 pathway_integrated_full.py &
PIPELINE_PID=$!

# Wait for initialization
sleep 10
```

### During Demo (3 min)

**[0:00-0:15] Problem + Impact**
```
"Cold-chain failures waste 40% of food globally.
LiveCold prevents this using real-time AI monitoring."
```

**[0:15-1:15] Live Demo**
1. Show `output/alerts.csv` updating in real-time
2. Add new temperature event to `data/temp_events.csv`
3. Show new alert appears
4. Show RAG recommendation in `final_decisions_with_rag.csv`
5. Display metrics in `metrics/global_metrics.csv`

**[1:15-1:45] Live Document Update**
1. Edit `watched_docs/cold_chain_SOP.txt`
2. Query RAG API again
3. Show response updated with new SOP

**[1:45-2:30] Metrics**
Show:
- Latency: <500ms
- Waste avoided: X kg
- CO₂ saved: Y kg
- Value saved: ₹Z

**[2:30-3:00] Reproducibility**
```bash
# Show can replay
./run_demo.sh
```

---

## 📝 Quick Reference

| Task | Command |
|------|---------|
| Run RAG only | `python3 pathway_rag_pipeline.py` |
| Run Metrics only | `python3 pathway_metrics_pipeline.py` |
| Run Full Pipeline | `python3 pathway_integrated_full.py` |
| Test RAG API | `curl -X POST http://localhost:8765/v1/pw_ai_answer -d '{"query":"test"}'` |
| Check outputs | `ls -lh output/ metrics/` |
| View logs | Check terminal output |

---

## ✅ Success Criteria

- [ ] Pathway installed: `python3 -c "import pathway as pw"`
- [ ] API key set: `echo $GEMINI_API_KEY`
- [ ] Data files created: `ls data/`
- [ ] SOP document added: `ls watched_docs/`
- [ ] RAG pipeline runs: `python3 pathway_rag_pipeline.py`
- [ ] Metrics pipeline runs: `python3 pathway_metrics_pipeline.py`
- [ ] Full pipeline runs: `python3 pathway_integrated_full.py`
- [ ] Outputs generated: `ls output/ metrics/`

---

## 🎯 Next Steps

1. **Add more sensors:** GPS, door, reefer telemetry
2. **Build UI:** Flask/Streamlit dashboard
3. **Add alerts:** Email/SMS notifications
4. **Scale up:** Kafka, distributed Pathway
5. **ML models:** Better risk prediction

---

**Pathway Framework = Real-time + Declarative + Built-in RAG** 🚀

Happy hacking!
