/**
 * DriverPage.jsx
 *
 * Live map uses Leaflet + OpenStreetMap (free, no API key).
 * All dynamic data comes from the backend WebSocket/MQTT bridge.
 * For frontend testing, a mock data layer seeds initial state and
 * simulates position updates when no WS connection is available.
 *
 * Install:  npm install leaflet react-leaflet
 * Add to index.html / main.jsx:
 *   import 'leaflet/dist/leaflet.css';
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import { useNavigate } from "react-router-dom";

// Fix Leaflet default icon paths (Vite / webpack issue)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:       "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:     "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

// ── Custom SVG marker icons ──────────────────────────────────────────────────
const makeTruckIcon = (color) =>
  L.divIcon({
    className: "",
    html: `<div style="
      width:32px;height:32px;border-radius:50% 50% 50% 0;
      background:${color};border:2px solid #070b14;
      transform:rotate(-45deg);
      box-shadow:0 0 12px ${color}90;
    "></div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -36],
  });

const makeHubIcon = (color) =>
  L.divIcon({
    className: "",
    html: `<div style="
      width:20px;height:20px;border-radius:4px;
      background:${color}30;border:2px solid ${color};
      display:flex;align-items:center;justify-content:center;
      font-size:11px;
    ">❄</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -14],
  });

// ── Theme ────────────────────────────────────────────────────────────────────
const T = {
  bg:         "#060C14",
  surface:    "#0D1825",
  border:     "#1A2D42",
  accent:     "#00D4FF",
  accentDim:  "#0A3A4A",
  green:      "#00FF88",
  orange:     "#FF8C00",
  red:        "#FF3355",
  text:       "#E8F4FF",
  muted:      "#5A7A9A",
  dim:        "#2A4A6A",
};

const RISK_COLOR = { LOW: T.green, MEDIUM: T.orange, HIGH: T.red };

// ── Mock seed data (used in testing when WS is unavailable) ──────────────────
const MOCK_SHIPMENT = {
  id:          sessionStorage.getItem("livecold_id") || "DRV-001",
  driverName:  "Rajesh Kumar",
  vehicleId:   "HR 26DQ5551",
  from:        "Delhi",
  to:          "Mumbai",
  cargo:       "Vaccines",
  cargoValue:  1500000,
  lat:         28.6139,
  lng:         77.209,
  speed:       62,
  temp:        5.2,
  idealTemp:   "2–8°C",
  isIdeal:     true,
  humidity:    74,
  battery:     88,
  compressor:  "RUNNING",
  etaHrs:      14.5,
  progress:    0.18,
  riskScore:   0.22,
  riskLevel:   "LOW",
  status:      "ON ROUTE",
  doorEvents:  1,
  routePath:   [
    [28.6139, 77.209], [27.18, 77.44], [26.0, 76.6],
    [24.58, 74.63],    [23.02, 72.57], [21.17, 72.83],
    [20.0, 73.2],      [19.076, 72.878],
  ],
};

const MOCK_HUBS = [
  { id:"hub_01", name:"Gurgaon Cold Hub",    lat:28.4595, lng:77.0266, phone:"+91-124-456-7890", capacity:82, tempRange:"-25 to 8°C",  type:"Multi-Temp", riskReduction:38, distKm:22, etaMins:28, color:"#00D4FF" },
  { id:"hub_02", name:"Okhla Cold Storage",  lat:28.5355, lng:77.251,  phone:"+91-11-2456-7890", capacity:65, tempRange:"2 to 8°C",    type:"Pharma",     riskReduction:31, distKm:18, etaMins:24, color:"#8b5cf6" },
  { id:"hub_03", name:"Azadpur Mandi Hub",   lat:28.7069, lng:77.1763, phone:"+91-11-2765-4321", capacity:90, tempRange:"0 to 10°C",   type:"General",    riskReduction:22, distKm:34, etaMins:42, color:"#00FF88" },
];

const MOCK_ALERTS = [
  { id:"a1", time:"14:32", level:"WARNING", msg:"Temperature drift detected: 5.2°C → 6.1°C over 10 min." },
  { id:"a2", time:"14:18", level:"INFO",    msg:"Door sensor event #1 logged at Mathura bypass." },
];

// ── Map fly-to helper ────────────────────────────────────────────────────────
function FlyTo({ lat, lng }) {
  const map = useMap();
  useEffect(() => {
    if (lat && lng) map.flyTo([lat, lng], map.getZoom(), { duration: 1.2 });
  }, [lat, lng, map]);
  return null;
}

// ── Risk bar ─────────────────────────────────────────────────────────────────
function RiskBar({ score }) {
  const pct = Math.round(score * 100);
  const color = score < 0.4 ? T.green : score < 0.7 ? T.orange : T.red;
  return (
    <div>
      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
        <span style={{ color:T.muted, fontSize:10, fontFamily:"Space Mono" }}>RISK SCORE</span>
        <span style={{ color, fontSize:10, fontFamily:"Space Mono", fontWeight:"bold" }}>{pct}%</span>
      </div>
      <div style={{ height:6, background:T.border, borderRadius:3, overflow:"hidden" }}>
        <div style={{ height:"100%", width:`${pct}%`, background:`linear-gradient(90deg,${color}80,${color})`, borderRadius:3, transition:"width 1s ease" }} />
      </div>
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────
const SectionHead = ({ label, icon }) => (
  <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:12 }}>
    <span style={{ fontSize:14 }}>{icon}</span>
    <span style={{ color:T.accent, fontFamily:"Space Mono", fontSize:10, letterSpacing:3, fontWeight:"bold" }}>{label}</span>
  </div>
);

// ── Card wrapper ──────────────────────────────────────────────────────────────
const Card = ({ children, style = {} }) => (
  <div style={{ background:T.surface, border:`1px solid ${T.border}`, borderRadius:10, padding:"14px 16px", ...style }}>
    {children}
  </div>
);

// ── Main DriverPage ───────────────────────────────────────────────────────────
export default function DriverPage() {
  const navigate       = useNavigate();
  const wsRef          = useRef(null);
  const [tab, setTab]  = useState("map");   // "map" | "shipment" | "hubs" | "alerts" | "calls"

  const [shipment,  setShipment]  = useState(MOCK_SHIPMENT);
  const [hubs,      setHubs]      = useState(MOCK_HUBS);
  const [alerts,    setAlerts]    = useState(MOCK_ALERTS);
  const [callState, setCallState] = useState({ active:false, hubId:null, elapsed:0 });
  const [callLog,   setCallLog]   = useState([]);
  const timerRef = useRef(null);

  // ── WebSocket connection ──────────────────────────────────────────────────
  useEffect(() => {
    // TODO: replace URL with real WS endpoint
    const WS_URL = import.meta.env?.VITE_WS_URL || "ws://localhost:8080/ws/driver";
    let ws;
    try {
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => console.log("[WS] Driver connected");

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          /**
           * Expected message types from backend:
           *
           * { type: "POSITION",   lat, lng, speed, temp, humidity, battery, riskScore, riskLevel, status, compressor, doorEvents }
           * { type: "HUBS",       hubs: [ { id, name, lat, lng, phone, capacity, tempRange, type, riskReduction, distKm, etaMins, color } ] }
           * { type: "ALERT",      alert: { id, time, level, msg } }
           * { type: "SHIPMENT",   ...shipment fields }
           */
          switch (msg.type) {
            case "POSITION":
              setShipment(prev => ({ ...prev, ...msg }));
              break;
            case "HUBS":
              setHubs(msg.hubs);
              break;
            case "ALERT":
              setAlerts(prev => [msg.alert, ...prev].slice(0, 20));
              break;
            case "SHIPMENT":
              setShipment(prev => ({ ...prev, ...msg }));
              break;
            default:
              break;
          }
        } catch {}
      };

      ws.onerror = () => console.warn("[WS] Driver WS error — using mock data");
      ws.onclose = () => console.log("[WS] Driver WS closed");
    } catch {
      console.warn("[WS] Could not open WebSocket — using mock data");
    }

    return () => { ws?.close(); };
  }, []);

  // ── Call timer ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (callState.active) {
      timerRef.current = setInterval(() => {
        setCallState(prev => ({ ...prev, elapsed: prev.elapsed + 1 }));
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [callState.active]);

  const startCall = (hub) => {
    setCallState({ active:true, hubId:hub.id, hubName:hub.name, phone:hub.phone, elapsed:0 });
    setTab("calls");
  };

  const endCall = () => {
    const hub = hubs.find(h => h.id === callState.hubId);
    setCallLog(prev => [{
      id:    Date.now(),
      name:  callState.hubName,
      phone: callState.phone,
      dur:   callState.elapsed,
      time:  new Date().toLocaleTimeString("en-IN", { hour:"2-digit", minute:"2-digit" }),
    }, ...prev]);
    setCallState({ active:false, hubId:null, elapsed:0 });
  };

  const fmtDur = (s) => `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;

  const logout = () => {
    sessionStorage.clear();
    navigate("/");
  };

  // ── Derived ──────────────────────────────────────────────────────────────
  const riskColor  = RISK_COLOR[shipment.riskLevel] || T.green;
  const topHub     = hubs[0];

  // ── Truck + hub icons ────────────────────────────────────────────────────
  const truckIcon = makeTruckIcon(riskColor);

  return (
    <div style={{ width:"100vw", height:"100vh", background:T.bg, display:"flex", flexDirection:"column", fontFamily:"'Space Mono',monospace", overflow:"hidden" }}>
      {/* ── Top bar ── */}
      <div style={{ height:48, background:T.surface, borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", padding:"0 16px", gap:12, flexShrink:0, zIndex:20 }}>
        <span style={{ fontSize:16 }}>❄️</span>
        <span style={{ color:T.accent, fontSize:13, fontWeight:"bold", letterSpacing:2 }}>LIVECOLD</span>
        <span style={{ color:T.dim, fontSize:9 }}>DRIVER</span>

        <div style={{ flex:1 }} />

        {/* Live risk pill */}
        <div style={{ background:riskColor+"20", border:`1px solid ${riskColor}50`, borderRadius:20, padding:"3px 12px", display:"flex", alignItems:"center", gap:6 }}>
          <div style={{ width:6, height:6, borderRadius:"50%", background:riskColor, animation:"pulse 1.5s infinite" }} />
          <span style={{ color:riskColor, fontSize:9, letterSpacing:2 }}>
            {shipment.riskLevel} RISK · {Math.round(shipment.riskScore * 100)}%
          </span>
        </div>

        {/* Temp */}
        <div style={{ background:T.surface, border:`1px solid ${shipment.isIdeal ? T.green+"40" : T.red+"40"}`, borderRadius:6, padding:"3px 10px" }}>
          <span style={{ color:shipment.isIdeal ? T.green : T.red, fontSize:11, fontWeight:"bold" }}>{shipment.temp}°C</span>
        </div>

        <button onClick={logout} style={{ background:"transparent", border:`1px solid ${T.border}`, borderRadius:6, color:T.muted, fontSize:9, padding:"4px 10px", cursor:"pointer" }}>
          SIGN OUT
        </button>
      </div>

      {/* ── Body ── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* ── Left: nav + panels ── */}
        <div style={{ width:340, flexShrink:0, borderRight:`1px solid ${T.border}`, display:"flex", flexDirection:"column", overflow:"hidden" }}>
          {/* Nav tabs */}
          <div style={{ display:"flex", borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
            {[
              { id:"map",      icon:"🗺", label:"Map"      },
              { id:"shipment", icon:"📦", label:"Shipment" },
              { id:"hubs",     icon:"🏭", label:"Hubs"     },
              { id:"alerts",   icon:"⚡", label:"Alerts"   },
              { id:"calls",    icon:"📞", label:"Calls"    },
            ].map(t => (
              <button key={t.id} onClick={() => setTab(t.id)}
                style={{ flex:1, padding:"10px 4px", background:tab===t.id ? T.accentDim : "transparent",
                  borderBottom:tab===t.id ? `2px solid ${T.accent}` : "2px solid transparent",
                  color:tab===t.id ? T.accent : T.muted, fontSize:8, fontFamily:"Space Mono",
                  cursor:"pointer", display:"flex", flexDirection:"column", alignItems:"center", gap:3 }}>
                <span style={{ fontSize:13 }}>{t.icon}</span>
                {t.label}
                {t.id === "alerts" && alerts.filter(a => a.level !== "INFO").length > 0 && (
                  <span style={{ background:T.red, color:"#fff", borderRadius:8, padding:"0 4px", fontSize:8 }}>
                    {alerts.filter(a => a.level !== "INFO").length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div style={{ flex:1, overflowY:"auto", padding:14 }}>

            {/* ── MAP tab ─ placeholder; full map on right ── */}
            {tab === "map" && (
              <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                <Card>
                  <SectionHead label="YOUR POSITION" icon="📍" />
                  <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                    {[
                      { l:"LAT",    v: shipment.lat?.toFixed(4) },
                      { l:"LNG",    v: shipment.lng?.toFixed(4) },
                      { l:"SPEED",  v: `${shipment.speed} km/h` },
                      { l:"STATUS", v: shipment.status, c: shipment.status==="DIVERTING" ? T.orange : shipment.status==="STOPPED" ? T.muted : T.green },
                    ].map(({ l, v, c }) => (
                      <div key={l}>
                        <div style={{ color:T.muted, fontSize:8, letterSpacing:1 }}>{l}</div>
                        <div style={{ color:c||T.text, fontSize:11, marginTop:2 }}>{v}</div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card>
                  <SectionHead label="NEAREST HUB" icon="🏭" />
                  {topHub ? (
                    <div>
                      <div style={{ color:T.text, fontSize:12, fontWeight:"bold", marginBottom:4 }}>{topHub.name}</div>
                      <div style={{ color:T.muted, fontSize:10, marginBottom:8 }}>{topHub.distKm} km · {topHub.etaMins} min ETA</div>
                      <div style={{ background:`${T.green}20`, border:`1px solid ${T.green}40`, borderRadius:6, padding:"6px 10px", marginBottom:8 }}>
                        <span style={{ color:T.green, fontSize:10 }}>↓ {topHub.riskReduction}% risk reduction if diverted</span>
                      </div>
                      <button onClick={() => startCall(topHub)}
                        style={{ width:"100%", background:T.accentDim, border:`1px solid ${T.accent}`, borderRadius:6, color:T.accent, fontSize:10, padding:"7px", cursor:"pointer" }}>
                        📞 CALL HUB
                      </button>
                    </div>
                  ) : <div style={{ color:T.muted, fontSize:11 }}>Fetching hubs…</div>}
                </Card>

                <RiskBar score={shipment.riskScore} />
              </div>
            )}

            {/* ── SHIPMENT tab ── */}
            {tab === "shipment" && (
              <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                {/* ID card */}
                <div style={{ background:`linear-gradient(135deg,#00D4FF18,transparent)`, border:`1px solid #00D4FF30`, borderRadius:10, padding:"14px 16px" }}>
                  <div style={{ fontSize:18, fontWeight:"bold", color:T.text }}>{shipment.id}</div>
                  <div style={{ color:T.muted, fontSize:10, marginTop:2 }}>💉 {shipment.cargo}</div>
                  <div style={{ color:T.muted, fontSize:10, marginTop:6 }}>
                    <span style={{ color:T.text }}>{shipment.from}</span>
                    <span style={{ color:T.dim, margin:"0 6px" }}>━▶</span>
                    <span style={{ color:T.text }}>{shipment.to}</span>
                  </div>
                  {/* Progress */}
                  <div style={{ marginTop:12 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                      <span style={{ color:T.muted, fontSize:9 }}>JOURNEY PROGRESS</span>
                      <span style={{ color:T.accent, fontSize:9 }}>{Math.round(shipment.progress*100)}%</span>
                    </div>
                    <div style={{ height:5, background:T.border, borderRadius:3, overflow:"hidden" }}>
                      <div style={{ height:"100%", width:`${Math.round(shipment.progress*100)}%`, background:`linear-gradient(90deg,#00D4FF,${T.green})`, borderRadius:3 }} />
                    </div>
                  </div>
                </div>

                <Card>
                  <SectionHead label="LIVE SENSORS" icon="📡" />
                  <div style={{ display:"grid", gridTemplateColumns:"repeat(2,1fr)", gap:10 }}>
                    {[
                      { l:"TEMP",        v:`${shipment.temp}°C`,       c: shipment.isIdeal ? T.green : T.red },
                      { l:"IDEAL RANGE", v: shipment.idealTemp,         c: T.muted },
                      { l:"HUMIDITY",    v:`${shipment.humidity}%`,     c: T.accent },
                      { l:"BATTERY",     v:`${shipment.battery}%`,      c: shipment.battery>50 ? T.green : T.orange },
                      { l:"COMPRESSOR",  v: shipment.compressor,        c: shipment.compressor==="RUNNING" ? T.green : T.red },
                      { l:"DOOR EVENTS", v: shipment.doorEvents,        c: shipment.doorEvents > 3 ? T.orange : T.text },
                    ].map(({ l, v, c }) => (
                      <div key={l} style={{ background:T.bg, borderRadius:6, padding:"8px 10px" }}>
                        <div style={{ color:T.muted, fontSize:8, letterSpacing:1 }}>{l}</div>
                        <div style={{ color:c, fontSize:11, marginTop:2 }}>{v}</div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card>
                  <SectionHead label="CARGO VALUE" icon="💰" />
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                    <span style={{ color:T.green, fontSize:20, fontWeight:"bold" }}>
                      ₹{(shipment.cargoValue/100000).toFixed(1)}L
                    </span>
                    <span style={{ color: shipment.riskLevel==="LOW" ? T.green : T.orange, fontSize:10, border:`1px solid currentColor`, borderRadius:4, padding:"3px 8px" }}>
                      {shipment.riskLevel==="LOW" ? "✓ SECURED" : "⚡ MONITOR"}
                    </span>
                  </div>
                </Card>

                <RiskBar score={shipment.riskScore} />
              </div>
            )}

            {/* ── HUBS tab ── */}
            {tab === "hubs" && (
              <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                <div style={{ color:T.muted, fontSize:9, letterSpacing:2, marginBottom:4 }}>TOP 3 NEARBY COLD STORAGE · BY RISK REDUCTION</div>
                {hubs.slice(0,3).map((hub, i) => (
                  <Card key={hub.id} style={{ borderLeft:`3px solid ${hub.color}` }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
                      <div>
                        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                          <span style={{ background:hub.color+"30", color:hub.color, fontFamily:"Space Mono", fontSize:9, padding:"2px 6px", borderRadius:3, fontWeight:"bold" }}>
                            #{i+1}
                          </span>
                          <span style={{ color:T.text, fontSize:12, fontWeight:"bold" }}>{hub.name}</span>
                        </div>
                        <div style={{ color:T.muted, fontSize:10, marginTop:3 }}>{hub.type} · {hub.tempRange}</div>
                      </div>
                      <div style={{ textAlign:"right" }}>
                        <div style={{ color:T.green, fontSize:13, fontWeight:"bold" }}>↓{hub.riskReduction}%</div>
                        <div style={{ color:T.muted, fontSize:9 }}>risk reduction</div>
                      </div>
                    </div>

                    <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:6, marginBottom:10 }}>
                      {[
                        { l:"DISTANCE",  v:`${hub.distKm} km`   },
                        { l:"ETA",       v:`${hub.etaMins} min`  },
                        { l:"CAPACITY",  v:`${hub.capacity}%`    },
                      ].map(({ l, v }) => (
                        <div key={l} style={{ background:T.bg, borderRadius:4, padding:"5px 7px" }}>
                          <div style={{ color:T.muted, fontSize:8 }}>{l}</div>
                          <div style={{ color:T.text, fontSize:10, marginTop:1 }}>{v}</div>
                        </div>
                      ))}
                    </div>

                    <div style={{ display:"flex", gap:8 }}>
                      <button
                        onClick={() => startCall(hub)}
                        style={{ flex:1, background:T.accentDim, border:`1px solid ${T.accent}`, borderRadius:6, color:T.accent, fontSize:10, padding:"7px", cursor:"pointer" }}>
                        📞 CALL
                      </button>
                      <button
                        style={{ flex:1, background:"transparent", border:`1px solid ${T.border}`, borderRadius:6, color:T.muted, fontSize:10, padding:"7px", cursor:"pointer" }}>
                        🗺 NAVIGATE
                      </button>
                    </div>
                  </Card>
                ))}
                {hubs.length === 0 && (
                  <div style={{ color:T.muted, fontSize:11, textAlign:"center", padding:40 }}>Fetching nearby hubs…</div>
                )}
              </div>
            )}

            {/* ── ALERTS tab ── */}
            {tab === "alerts" && (
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                <div style={{ color:T.muted, fontSize:9, letterSpacing:2, marginBottom:4 }}>LIVE ALERTS · REAL-TIME UPDATES</div>
                {alerts.length === 0 && (
                  <div style={{ color:T.muted, textAlign:"center", padding:40, fontSize:11 }}>
                    ✅ No active alerts
                  </div>
                )}
                {alerts.map(a => {
                  const levelColor = a.level === "DANGER" ? T.red : a.level === "WARNING" ? T.orange : T.accent;
                  return (
                    <div key={a.id} style={{ background:T.surface, border:`1px solid ${levelColor}40`, borderLeft:`3px solid ${levelColor}`, borderRadius:8, padding:"10px 12px" }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                        <span style={{ color:levelColor, fontSize:9, fontWeight:"bold", letterSpacing:1 }}>{a.level}</span>
                        <span style={{ color:T.muted, fontSize:9 }}>{a.time}</span>
                      </div>
                      <div style={{ color:T.text, fontSize:11, lineHeight:1.5 }}>{a.msg}</div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ── CALLS tab ── */}
            {tab === "calls" && (
              <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                <SectionHead label="COLD STORAGE CONTACTS" icon="📞" />

                {/* Active call */}
                {callState.active && (
                  <div style={{ background:T.green+"15", border:`1px solid ${T.green}40`, borderRadius:10, padding:"16px" }}>
                    <div style={{ color:T.green, fontSize:9, letterSpacing:2, marginBottom:6 }}>● CALL IN PROGRESS</div>
                    <div style={{ color:T.text, fontSize:14, fontWeight:"bold" }}>{callState.hubName}</div>
                    <div style={{ color:T.muted, fontSize:10, marginTop:2 }}>{callState.phone}</div>
                    <div style={{ color:T.green, fontSize:22, fontFamily:"Space Mono", margin:"10px 0", textAlign:"center" }}>
                      {fmtDur(callState.elapsed)}
                    </div>
                    <button onClick={endCall}
                      style={{ width:"100%", background:T.red+"30", border:`1px solid ${T.red}`, borderRadius:6, color:T.red, fontSize:11, fontWeight:"bold", padding:"9px", cursor:"pointer" }}>
                      END CALL
                    </button>
                  </div>
                )}

                {/* Top 3 hubs dial pad */}
                <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                  {hubs.slice(0,3).map((hub, i) => (
                    <div key={hub.id} style={{ background:T.surface, border:`1px solid ${T.border}`, borderRadius:8, padding:"10px 14px", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                      <div>
                        <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                          <span style={{ color:hub.color, fontSize:9, background:hub.color+"20", padding:"1px 6px", borderRadius:3 }}>#{i+1}</span>
                          <span style={{ color:T.text, fontSize:11, fontWeight:"bold" }}>{hub.name}</span>
                        </div>
                        <div style={{ color:T.muted, fontSize:9, marginTop:2 }}>{hub.phone}</div>
                        <div style={{ color:T.green, fontSize:9, marginTop:2 }}>↓{hub.riskReduction}% risk · {hub.distKm} km</div>
                      </div>
                      <button
                        onClick={() => startCall(hub)}
                        disabled={callState.active}
                        style={{ background:callState.active ? T.dim : T.accentDim, border:`1px solid ${callState.active ? T.dim : T.accent}`, borderRadius:6, color:callState.active ? T.muted : T.accent, fontSize:9, padding:"8px 12px", cursor:callState.active ? "not-allowed" : "pointer" }}>
                        📞 CALL
                      </button>
                    </div>
                  ))}
                </div>

                {/* Call log */}
                {callLog.length > 0 && (
                  <>
                    <div style={{ color:T.muted, fontSize:9, letterSpacing:2, marginTop:4 }}>RECENT CALLS</div>
                    {callLog.map(c => (
                      <div key={c.id} style={{ background:T.surface, border:`1px solid ${T.border}`, borderRadius:6, padding:"8px 12px", display:"flex", justifyContent:"space-between" }}>
                        <div>
                          <div style={{ color:T.text, fontSize:11 }}>{c.name}</div>
                          <div style={{ color:T.muted, fontSize:9 }}>{c.phone}</div>
                        </div>
                        <div style={{ textAlign:"right" }}>
                          <div style={{ color:T.muted, fontSize:9 }}>{c.time}</div>
                          <div style={{ color:T.accent, fontSize:9 }}>{fmtDur(c.dur)}</div>
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>
            )}

          </div>
        </div>

        {/* ── Right: Live Leaflet Map ── */}
        <div style={{ flex:1, position:"relative", overflow:"hidden" }}>
          <MapContainer
            center={[shipment.lat, shipment.lng]}
            zoom={6}
            style={{ width:"100%", height:"100%" }}
            zoomControl={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* Planned route polyline */}
            {shipment.routePath && shipment.routePath.length > 1 && (
              <Polyline
                positions={shipment.routePath}
                pathOptions={{ color: "#00D4FF", weight: 3, opacity: 0.5, dashArray: "8 6" }}
              />
            )}

            {/* Truck position */}
            <Marker position={[shipment.lat, shipment.lng]} icon={truckIcon}>
              <Popup>
                <div style={{ fontFamily:"monospace", fontSize:12 }}>
                  <strong>{shipment.id}</strong><br />
                  {shipment.cargo} · {shipment.temp}°C<br />
                  Risk: {shipment.riskLevel}<br />
                  Speed: {shipment.speed} km/h
                </div>
              </Popup>
            </Marker>

            {/* Cold hub markers */}
            {hubs.slice(0,3).map((hub, i) => (
              <Marker key={hub.id} position={[hub.lat, hub.lng]} icon={makeHubIcon(hub.color)}>
                <Popup>
                  <div style={{ fontFamily:"monospace", fontSize:12 }}>
                    <strong>#{i+1} {hub.name}</strong><br />
                    {hub.type} · {hub.tempRange}<br />
                    ↓{hub.riskReduction}% risk reduction<br />
                    {hub.distKm} km · {hub.etaMins} min ETA<br />
                    Capacity: {hub.capacity}%
                  </div>
                </Popup>
              </Marker>
            ))}

            {/* Diversion lines: truck → each hub */}
            {hubs.slice(0,3).map((hub) => (
              <Polyline
                key={"line-" + hub.id}
                positions={[[shipment.lat, shipment.lng], [hub.lat, hub.lng]]}
                pathOptions={{ color: hub.color, weight: 1.5, opacity: 0.35, dashArray: "4 6" }}
              />
            ))}

            {/* Auto-pan as truck moves */}
            <FlyTo lat={shipment.lat} lng={shipment.lng} />
          </MapContainer>

          {/* Map overlay: risk info */}
          <div style={{ position:"absolute", top:12, right:12, zIndex:1000, background:"rgba(6,12,20,0.88)", border:`1px solid ${riskColor}50`, borderRadius:8, padding:"10px 14px", minWidth:160 }}>
            <div style={{ color:riskColor, fontSize:9, letterSpacing:2, marginBottom:6 }}>● {shipment.riskLevel} RISK</div>
            <div style={{ color:T.text, fontSize:12, fontWeight:"bold" }}>{shipment.cargo}</div>
            <div style={{ color:T.muted, fontSize:10, marginTop:2 }}>{shipment.from} → {shipment.to}</div>
            <div style={{ color: shipment.isIdeal ? T.green : T.red, fontSize:13, fontWeight:"bold", marginTop:6 }}>
              {shipment.temp}°C
            </div>
            <div style={{ color:T.muted, fontSize:9 }}>Safe: {shipment.idealTemp}</div>
          </div>

          {/* Legend */}
          <div style={{ position:"absolute", bottom:12, left:12, zIndex:1000, background:"rgba(6,12,20,0.85)", border:`1px solid ${T.border}`, borderRadius:8, padding:"8px 12px" }}>
            <div style={{ color:T.muted, fontSize:8, letterSpacing:2, marginBottom:6 }}>LEGEND</div>
            {[
              { c:T.green,  l:"LOW RISK TRUCK"   },
              { c:T.orange, l:"MED RISK TRUCK"   },
              { c:T.red,    l:"HIGH RISK TRUCK"  },
              { c:"#00D4FF",l:"HUB #1 (BEST)"    },
              { c:"#8b5cf6",l:"HUB #2"           },
              { c:"#00FF88",l:"HUB #3"           },
            ].map(({ c, l }) => (
              <div key={l} style={{ display:"flex", alignItems:"center", gap:6, marginBottom:3 }}>
                <div style={{ width:8, height:8, borderRadius:"50%", background:c }} />
                <span style={{ color:T.muted, fontSize:8 }}>{l}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
        * { box-sizing:border-box; }
        ::-webkit-scrollbar { width:4px; }
        ::-webkit-scrollbar-track { background:${T.bg}; }
        ::-webkit-scrollbar-thumb { background:${T.border}; border-radius:2px; }
        @keyframes pulse {
          0%,100% { opacity:1; box-shadow:0 0 4px currentColor; }
          50%      { opacity:0.4; box-shadow:0 0 14px currentColor; }
        }
        .leaflet-container { background:#070F1A !important; }
        .leaflet-tile { filter: brightness(0.85) saturate(0.6) hue-rotate(190deg); }
      `}</style>
    </div>
  );
}
