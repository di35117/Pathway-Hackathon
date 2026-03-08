/**
 * DriverPage.jsx
 * Real-road routing via OSRM  (no API key)
 * Live hub positions fetched from backend, shown on map with risk-reduction badge
 * WebSocket: POSITION_UPDATE | HUB_UPDATE | ALERT | SHIPMENT_UPDATE
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import { useNavigate } from "react-router-dom";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:       "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:     "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

// ─── palette ──────────────────────────────────────────────────────────────────
const C = {
  bg:     "#07101c",
  card:   "#0e1d2e",
  rim:    "#162840",
  cyan:   "#2dd4bf",
  blue:   "#38bdf8",
  green:  "#4ade80",
  amber:  "#fbbf24",
  rose:   "#f87171",
  slate:  "#94a3b8",
  dim:    "#334155",
  text:   "#e2e8f0",
  purple: "#a78bfa",
};
const RISK = { LOW: C.green, MEDIUM: C.amber, HIGH: C.rose };

// ─── Leaflet icons ─────────────────────────────────────────────────────────────
const truckIcon = (col) => L.divIcon({
  className: "",
  html: `<div style="position:relative;width:32px;height:32px">
    <div style="position:absolute;inset:0;border-radius:50%;background:${col};opacity:.25;animation:lc-ping 1.8s ease-out infinite"></div>
    <div style="position:absolute;inset:5px;border-radius:50%;background:${col};border:2.5px solid #07101c;box-shadow:0 0 12px ${col}90"></div>
  </div>`,
  iconSize: [32, 32], iconAnchor: [16, 16], popupAnchor: [0, -18],
});

// Hub marker with risk-reduction badge visible on map
const hubIcon = (col, rank, riskPct) => L.divIcon({
  className: "",
  html: `<div style="position:relative;display:inline-block">
    <div style="
      width:30px;height:30px;border-radius:8px;
      background:${col}20;border:2px solid ${col};
      display:flex;align-items:center;justify-content:center;
      font-size:12px;font-weight:700;color:${col};
      font-family:monospace;box-shadow:0 0 12px ${col}50;
    ">${rank}</div>
    <div style="
      position:absolute;bottom:-14px;left:50%;transform:translateX(-50%);
      background:#0e1d2e;border:1px solid ${col}80;border-radius:10px;
      padding:1px 5px;white-space:nowrap;
      font-size:9px;font-weight:700;color:${col};font-family:monospace;
    ">↓${riskPct}%</div>
  </div>`,
  iconSize: [30, 44], iconAnchor: [15, 15], popupAnchor: [0, -20],
});

// OSRM
const OSRM = "https://router.project-osrm.org/route/v1/driving";

// ─── mock ──────────────────────────────────────────────────────────────────────
const SEED = {
  shipmentId: "SHP-001", driverId: "DRV-001", driverName: "Rajesh Kumar",
  vehicleId: "MH 12 AB 1234", cargo: "Vaccines", cargoValue: 1500000,
  from: "Mumbai", to: "Delhi",
  lat: 19.076, lng: 72.878,
  destLat: 28.6139, destLng: 77.209,
  speed: 58, temp: 5.2, idealTemp: "2–8°C", isIdeal: true,
  humidity: 71, battery: 84, compressor: "RUNNING",
  etaHrs: 15.2, progress: 0.08, riskScore: 0.19, riskLevel: "LOW",
  status: "ON ROUTE", doorEvents: 1,
};

const SEED_HUBS = [
  { id:"h1", name:"Bhiwandi Cold Chain",  lat:19.2813, lng:73.0633, phone:"+91-22-2745-6789", capacity:73, tempRange:"-20–6°C",  type:"Multi-Temp", riskReduction:41, distKm:31, etaMins:38, color: C.blue   },
  { id:"h2", name:"Vashi Logistics Hub",  lat:19.08,   lng:73.01,   phone:"+91-22-2789-0123", capacity:58, tempRange:"2–8°C",    type:"Pharma",     riskReduction:27, distKm:8,  etaMins:12, color: C.purple },
  { id:"h3", name:"Pune Hadapsar Hub",    lat:18.508,  lng:73.94,   phone:"+91-20-2645-8901", capacity:88, tempRange:"-15–8°C",  type:"Multi-Temp", riskReduction:19, distKm:55, etaMins:62, color: C.cyan   },
];

const SEED_ALERTS = [
  { id:"a1", time:"14:32", level:"WARNING", msg:"Temperature drift — 5.2°C rising toward 6.1°C over last 10 min." },
  { id:"a2", time:"14:18", level:"INFO",    msg:"Door sensor event #1 recorded near Panvel." },
];

// ─── helpers ───────────────────────────────────────────────────────────────────
function FlyTo({ lat, lng }) {
  const map = useMap();
  const prev = useRef(null);
  useEffect(() => {
    if (!lat || !lng) return;
    const k = `${lat.toFixed(3)},${lng.toFixed(3)}`;
    if (k !== prev.current) { map.panTo([lat, lng], { animate: true, duration: 1.4 }); prev.current = k; }
  }, [lat, lng, map]);
  return null;
}

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

// ─── tiny components ───────────────────────────────────────────────────────────
function Pill({ text, color }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      background: `${color}18`, border: `1px solid ${color}45`,
      borderRadius: 20, padding: "2px 9px",
      color, fontSize: 10, fontFamily: "monospace", letterSpacing: 0.5,
    }}>{text}</span>
  );
}

function DataCell({ label, value, color, big }) {
  return (
    <div style={{ background: C.bg, borderRadius: 7, padding: "8px 10px" }}>
      <div style={{ color: C.dim, fontSize: 9, fontFamily: "monospace", marginBottom: 3, textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
      <div style={{ color: color || C.text, fontSize: big ? 18 : 12, fontWeight: big ? 700 : 500, fontFamily: "monospace" }}>{value}</div>
    </div>
  );
}

function RiskMeter({ score }) {
  const pct = Math.round(score * 100);
  const col = score < 0.35 ? C.green : score < 0.65 ? C.amber : C.rose;
  return (
    <div style={{ padding: "10px 14px", background: C.bg, borderRadius: 8, border: `1px solid ${C.rim}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ color: C.slate, fontSize: 11, fontFamily: "monospace" }}>Risk score</span>
        <span style={{ color: col, fontSize: 16, fontWeight: 700, fontFamily: "monospace" }}>{pct}%</span>
      </div>
      <div style={{ height: 5, background: C.rim, borderRadius: 99 }}>
        <div style={{ height: "100%", width: `${pct}%`, background: `linear-gradient(90deg,${col}60,${col})`, borderRadius: 99, transition: "width 1.2s ease" }} />
      </div>
    </div>
  );
}

// ─── main ──────────────────────────────────────────────────────────────────────
export default function DriverPage() {
  const navigate = useNavigate();
  const [ship,        setShip]        = useState(SEED);
  const [hubs,        setHubs]        = useState(SEED_HUBS);
  const [alerts,      setAlerts]      = useState(SEED_ALERTS);
  const [route,       setRoute]       = useState([]);
  const [crumbs,      setCrumbs]      = useState([[SEED.lat, SEED.lng]]);
  const [tab,         setTab]         = useState("map");
  const [drawer,      setDrawer]      = useState(false);
  const [call,        setCall]        = useState({ on: false, hubId: null, name: "", phone: "", t: 0 });
  const [callLog,     setCallLog]     = useState([]);
  const wsRef   = useRef(null);
  const osrmRef = useRef(null);
  const callRef = useRef(null);

  // OSRM
  const fetchRoute = useCallback(async (fLat, fLng, tLat, tLng) => {
    try {
      const r = await fetch(`${OSRM}/${fLng},${fLat};${tLng},${tLat}?overview=full&geometries=geojson`);
      const d = await r.json();
      if (d.code === "Ok") setRoute(d.routes[0].geometry.coordinates.map(([ln, la]) => [la, ln]));
    } catch { /* keep existing */ }
  }, []);

  useEffect(() => {
    clearTimeout(osrmRef.current);
    osrmRef.current = setTimeout(() => {
      if (ship.lat && ship.destLat) fetchRoute(ship.lat, ship.lng, ship.destLat, ship.destLng);
    }, 2500);
    return () => clearTimeout(osrmRef.current);
  }, [ship.lat, ship.lng, fetchRoute]);

  // Hubs from backend
  const loadHubs = useCallback(async (lat, lng) => {
    try {
      const tok = sessionStorage.getItem("livecold_token");
      const r = await fetch(`/api/driver/hubs/nearest?lat=${lat}&lng=${lng}&limit=3`, { headers: { Authorization: `Bearer ${tok}` } });
      if (r.ok) { const d = await r.json(); setHubs(d.hubs); }
    } catch { setHubs(SEED_HUBS); }
  }, []);

  // Initial REST
  useEffect(() => {
    const tok = sessionStorage.getItem("livecold_token");
    const id  = sessionStorage.getItem("livecold_id");
    fetch(`/api/driver/shipment/${id}`, { headers: { Authorization: `Bearer ${tok}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) { setShip(d); loadHubs(d.lat, d.lng); } })
      .catch(() => loadHubs(SEED.lat, SEED.lng));
  }, [loadHubs]);

  // WebSocket
  useEffect(() => {
    const id  = sessionStorage.getItem("livecold_id");
    const url = (import.meta.env?.VITE_WS_URL || "ws://localhost:8080") + `/ws/driver/${id}`;
    let ws;
    try {
      ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onmessage = ({ data }) => {
        try {
          const m = JSON.parse(data);
          if (m.type === "POSITION_UPDATE") {
            setShip(p => ({ ...p, ...m }));
            setCrumbs(p => [...p.slice(-300), [m.lat, m.lng]]);
            loadHubs(m.lat, m.lng);
          } else if (m.type === "HUB_UPDATE")      setHubs(m.hubs);
          else if (m.type === "ALERT")             setAlerts(p => [m.alert, ...p].slice(0, 40));
          else if (m.type === "SHIPMENT_UPDATE")   setShip(p => ({ ...p, ...m }));
        } catch {}
      };
    } catch {}
    return () => ws?.close();
  }, [loadHubs]);

  // Call timer
  useEffect(() => {
    if (call.on) { callRef.current = setInterval(() => setCall(p => ({ ...p, t: p.t + 1 })), 1000); }
    else          clearInterval(callRef.current);
    return ()  => clearInterval(callRef.current);
  }, [call.on]);

  const startCall = (hub) => { setCall({ on: true, hubId: hub.id, name: hub.name, phone: hub.phone, t: 0 }); openTab("calls"); };
  const endCall   = () => {
    setCallLog(p => [{ id: Date.now(), name: call.name, phone: call.phone, dur: call.t, at: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) }, ...p]);
    setCall({ on: false, hubId: null, name: "", phone: "", t: 0 });
  };

  const rc = RISK[ship.riskLevel] || C.green;
  const openTab = (t) => { setTab(t); setDrawer(t !== "map"); };
  const logout  = () => { sessionStorage.clear(); navigate("/"); };

  const unreadAlerts = alerts.filter(a => a.level !== "INFO").length;

  const TABS = [
    { id: "map",      emoji: "◉",  label: "Map"      },
    { id: "shipment", emoji: "⬡",  label: "Cargo"    },
    { id: "hubs",     emoji: "❄",  label: "Hubs"     },
    { id: "alerts",   emoji: "⚡",  label: "Alerts",  badge: unreadAlerts },
    { id: "calls",    emoji: "↗",  label: "Calls"    },
  ];

  // ── Panel content per tab ───────────────────────────────────────────────────
  const PanelContent = () => (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>

      {/* MAP tab */}
      {tab === "map" && <>
        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 10, padding: "14px 15px" }}>
          <div style={{ color: C.slate, fontSize: 10, fontFamily: "monospace", marginBottom: 10, letterSpacing: 1 }}>POSITION</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
            <DataCell label="Speed"  value={`${ship.speed} km/h`} />
            <DataCell label="Status" value={ship.status} color={ship.status === "DIVERTING" ? C.amber : ship.status === "STOPPED" ? C.slate : C.green} />
            <DataCell label="Lat"    value={ship.lat?.toFixed(4)} />
            <DataCell label="Lng"    value={ship.lng?.toFixed(4)} />
          </div>
        </div>
        {hubs[0] && (
          <div style={{ background: C.card, borderLeft: `3px solid ${hubs[0].color}`, border: `1px solid ${C.rim}`, borderRadius: 10, padding: "14px 15px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 10, color: C.slate, fontFamily: "monospace", marginBottom: 3 }}>CLOSEST HUB</div>
                <div style={{ color: C.text, fontSize: 14, fontWeight: 600 }}>{hubs[0].name}</div>
                <div style={{ color: C.slate, fontSize: 11, marginTop: 2 }}>{hubs[0].distKm} km · {hubs[0].etaMins} min away</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ color: C.green, fontSize: 20, fontWeight: 700, fontFamily: "monospace" }}>↓{hubs[0].riskReduction}%</div>
                <div style={{ color: C.slate, fontSize: 9 }}>risk if diverted</div>
              </div>
            </div>
            <button onClick={() => startCall(hubs[0])} style={{ width: "100%", background: `${hubs[0].color}15`, border: `1px solid ${hubs[0].color}50`, borderRadius: 7, color: hubs[0].color, fontSize: 11, fontFamily: "monospace", padding: "8px 0", cursor: "pointer" }}>
              Call hub →
            </button>
          </div>
        )}
        <RiskMeter score={ship.riskScore} />
      </>}

      {/* SHIPMENT tab */}
      {tab === "shipment" && <>
        <div style={{ background: `linear-gradient(135deg,${C.blue}12,transparent)`, border: `1px solid ${C.blue}30`, borderRadius: 12, padding: "16px 17px" }}>
          <div style={{ fontSize: 11, color: C.slate, fontFamily: "monospace", marginBottom: 4 }}>Active shipment</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: C.text, fontFamily: "monospace" }}>{ship.shipmentId}</div>
          <div style={{ color: C.slate, fontSize: 12, marginTop: 3 }}>
            <span style={{ color: C.text }}>{ship.from}</span>
            <span style={{ color: C.dim, margin: "0 8px" }}>→</span>
            <span style={{ color: C.text }}>{ship.to}</span>
          </div>
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
              <span style={{ fontSize: 10, color: C.slate }}>Progress</span>
              <span style={{ fontSize: 10, color: C.blue, fontFamily: "monospace" }}>{Math.round(ship.progress * 100)}%</span>
            </div>
            <div style={{ height: 4, background: C.rim, borderRadius: 99 }}>
              <div style={{ height: "100%", width: `${Math.round(ship.progress * 100)}%`, background: `linear-gradient(90deg,${C.blue},${C.cyan})`, borderRadius: 99 }} />
            </div>
          </div>
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 10, padding: "14px 15px" }}>
          <div style={{ color: C.slate, fontSize: 10, fontFamily: "monospace", marginBottom: 10, letterSpacing: 1 }}>LIVE SENSORS</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
            <DataCell label="Temperature" value={`${ship.temp}°C`}       color={ship.isIdeal ? C.green : C.rose} big />
            <DataCell label="Safe range"  value={ship.idealTemp}          color={C.slate} />
            <DataCell label="Humidity"    value={`${ship.humidity}%`}     color={C.cyan} />
            <DataCell label="Battery"     value={`${ship.battery}%`}      color={ship.battery > 50 ? C.green : C.amber} />
            <DataCell label="Compressor"  value={ship.compressor}         color={ship.compressor === "RUNNING" ? C.green : C.rose} />
            <DataCell label="Door events" value={ship.doorEvents}         color={ship.doorEvents > 3 ? C.amber : C.slate} />
          </div>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <div style={{ flex: 1, background: C.card, border: `1px solid ${C.rim}`, borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ color: C.slate, fontSize: 10, fontFamily: "monospace" }}>Cargo value</div>
            <div style={{ color: C.green, fontSize: 22, fontWeight: 700, fontFamily: "monospace", marginTop: 4 }}>
              ₹{(ship.cargoValue / 100000).toFixed(1)}L
            </div>
          </div>
          <div style={{ flex: 1, background: C.card, border: `1px solid ${C.rim}`, borderRadius: 10, padding: "12px 14px" }}>
            <div style={{ color: C.slate, fontSize: 10, fontFamily: "monospace" }}>ETA</div>
            <div style={{ color: C.text, fontSize: 22, fontWeight: 700, fontFamily: "monospace", marginTop: 4 }}>
              {ship.etaHrs}h
            </div>
          </div>
        </div>
        <RiskMeter score={ship.riskScore} />
      </>}

      {/* HUBS tab */}
      {tab === "hubs" && <>
        <div style={{ fontSize: 11, color: C.slate, marginBottom: 2 }}>
          Nearest cold storages — ranked by how much they'd reduce your risk.
          Data updates as you move.
        </div>
        {hubs.slice(0, 3).map((hub, i) => (
          <div key={hub.id} style={{ background: C.card, border: `1px solid ${C.rim}`, borderLeft: `3px solid ${hub.color}`, borderRadius: 10, padding: "14px 15px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                  <span style={{ background: `${hub.color}20`, color: hub.color, fontSize: 9, padding: "1px 7px", borderRadius: 10, fontFamily: "monospace", fontWeight: 700 }}>#{i + 1}</span>
                  <span style={{ color: C.text, fontWeight: 600, fontSize: 13 }}>{hub.name}</span>
                </div>
                <div style={{ color: C.slate, fontSize: 11 }}>{hub.type} · {hub.tempRange}</div>
              </div>
              <div style={{ textAlign: "right", marginLeft: 8 }}>
                <div style={{ color: C.green, fontSize: 22, fontWeight: 700, fontFamily: "monospace", lineHeight: 1 }}>↓{hub.riskReduction}%</div>
                <div style={{ color: C.slate, fontSize: 9, marginTop: 2 }}>risk drop</div>
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 6, marginBottom: 10 }}>
              <DataCell label="Distance" value={`${hub.distKm} km`} />
              <DataCell label="ETA"      value={`${hub.etaMins}m`}  />
              <DataCell label="Capacity" value={`${hub.capacity}%`} />
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => startCall(hub)} style={{ flex: 1, background: `${hub.color}15`, border: `1px solid ${hub.color}50`, borderRadius: 7, color: hub.color, fontSize: 11, fontFamily: "monospace", padding: 9, cursor: "pointer" }}>
                Call
              </button>
              <button style={{ flex: 1, background: "transparent", border: `1px solid ${C.rim}`, borderRadius: 7, color: C.slate, fontSize: 11, padding: 9, cursor: "pointer" }}>
                Navigate
              </button>
            </div>
          </div>
        ))}
        {hubs.length === 0 && <div style={{ color: C.slate, textAlign: "center", padding: 40, fontSize: 13 }}>Locating nearby cold storage…</div>}
      </>}

      {/* ALERTS tab */}
      {tab === "alerts" && <>
        <div style={{ fontSize: 11, color: C.slate, marginBottom: 2 }}>Real-time feed</div>
        {alerts.length === 0 && <div style={{ textAlign: "center", color: C.slate, padding: 40 }}>All clear — no alerts</div>}
        {alerts.map(a => {
          const col = a.level === "DANGER" ? C.rose : a.level === "WARNING" ? C.amber : C.cyan;
          return (
            <div key={a.id} style={{ background: C.card, borderLeft: `3px solid ${col}`, border: `1px solid ${col}25`, borderRadius: 9, padding: "11px 14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                <span style={{ color: col, fontSize: 9, fontFamily: "monospace", fontWeight: 700, letterSpacing: 1 }}>{a.level}</span>
                <span style={{ color: C.dim, fontSize: 10 }}>{a.time}</span>
              </div>
              <div style={{ color: C.text, fontSize: 12, lineHeight: 1.7 }}>{a.msg}</div>
            </div>
          );
        })}
      </>}

      {/* CALLS tab */}
      {tab === "calls" && <>
        {call.on && (
          <div style={{ background: `${C.green}12`, border: `1px solid ${C.green}40`, borderRadius: 11, padding: "18px 16px", textAlign: "center" }}>
            <div style={{ color: C.green, fontSize: 9, fontFamily: "monospace", letterSpacing: 2, marginBottom: 8 }}>● LIVE CALL</div>
            <div style={{ color: C.text, fontSize: 16, fontWeight: 600, marginBottom: 3 }}>{call.name}</div>
            <div style={{ color: C.slate, fontSize: 11, marginBottom: 14 }}>{call.phone}</div>
            <div style={{ color: C.green, fontSize: 32, fontFamily: "monospace", fontWeight: 700, marginBottom: 16 }}>{fmt(call.t)}</div>
            <button onClick={endCall} style={{ background: `${C.rose}20`, border: `1px solid ${C.rose}`, borderRadius: 8, color: C.rose, padding: "10px 32px", fontSize: 12, fontFamily: "monospace", cursor: "pointer" }}>
              End call
            </button>
          </div>
        )}
        <div style={{ fontSize: 11, color: C.slate }}>Hub contacts</div>
        {hubs.slice(0, 3).map((hub, i) => (
          <div key={hub.id} style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 9, padding: "12px 14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ display: "flex", gap: 7, alignItems: "center", marginBottom: 3 }}>
                <span style={{ color: hub.color, fontSize: 9, fontFamily: "monospace" }}>#{i + 1}</span>
                <span style={{ color: C.text, fontSize: 12, fontWeight: 600 }}>{hub.name}</span>
              </div>
              <div style={{ color: C.slate, fontSize: 10 }}>{hub.phone}</div>
              <div style={{ color: C.green, fontSize: 10, marginTop: 3, fontFamily: "monospace" }}>↓{hub.riskReduction}% · {hub.distKm} km</div>
            </div>
            <button onClick={() => startCall(hub)} disabled={call.on} style={{ background: call.on ? C.dim + "30" : `${hub.color}15`, border: `1px solid ${call.on ? C.dim : hub.color}50`, borderRadius: 7, color: call.on ? C.dim : hub.color, fontSize: 10, padding: "9px 14px", cursor: call.on ? "not-allowed" : "pointer" }}>
              Call
            </button>
          </div>
        ))}
        {callLog.length > 0 && <>
          <div style={{ fontSize: 11, color: C.slate, marginTop: 6 }}>Recent</div>
          {callLog.map(c => (
            <div key={c.id} style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 8, padding: "10px 13px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ color: C.text, fontSize: 12, fontWeight: 500 }}>{c.name}</div>
                <div style={{ color: C.slate, fontSize: 10, marginTop: 2 }}>{c.phone}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ color: C.slate, fontSize: 10 }}>{c.at}</div>
                <div style={{ color: C.cyan, fontSize: 11, fontFamily: "monospace", marginTop: 2 }}>{fmt(c.dur)}</div>
              </div>
            </div>
          ))}
        </>}
      </>}
    </div>
  );

  return (
    <div style={{ width: "100vw", height: "100svh", background: C.bg, display: "flex", flexDirection: "column", fontFamily: "'Outfit', sans-serif", overflow: "hidden" }}>

      {/* Top bar */}
      <div style={{ height: 50, background: C.card, borderBottom: `1px solid ${C.rim}`, display: "flex", alignItems: "center", padding: "0 16px", gap: 10, flexShrink: 0, zIndex: 30 }}>
        <span style={{ color: C.cyan, fontSize: 15, fontWeight: 700, letterSpacing: -0.3 }}>❄ LiveCold</span>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ width: 7, height: 7, borderRadius: "50%", background: rc, boxShadow: `0 0 6px ${rc}` }} />
          <span style={{ color: rc, fontSize: 11, fontFamily: "monospace" }}>{ship.riskLevel}</span>
        </div>
        <div style={{ background: `${ship.isIdeal ? C.green : C.rose}18`, border: `1px solid ${ship.isIdeal ? C.green : C.rose}40`, borderRadius: 6, padding: "3px 10px" }}>
          <span style={{ color: ship.isIdeal ? C.green : C.rose, fontSize: 13, fontWeight: 700, fontFamily: "monospace" }}>{ship.temp}°C</span>
        </div>
        <button onClick={logout} style={{ background: "none", border: `1px solid ${C.rim}`, borderRadius: 6, color: C.slate, fontSize: 10, padding: "4px 10px", cursor: "pointer" }}>
          Sign out
        </button>
      </div>

      {/* Body — desktop: side-by-side | mobile: map + bottom sheet */}
      <div className="dp-body" style={{ flex: 1, display: "flex", overflow: "hidden", position: "relative" }}>

        {/* ── DESKTOP PANEL (left) ── */}
        <div className="dp-desk-panel">
          {/* Nav tabs */}
          <div style={{ display: "flex", background: C.card, borderBottom: `1px solid ${C.rim}`, flexShrink: 0 }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => openTab(t.id)} style={{
                flex: 1, padding: "10px 4px 8px", background: tab === t.id ? `${C.cyan}12` : "transparent",
                borderBottom: tab === t.id ? `2px solid ${C.cyan}` : "2px solid transparent",
                color: tab === t.id ? C.cyan : C.dim, fontSize: 9,
                cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
                position: "relative", transition: "all 0.15s",
              }}>
                <span style={{ fontSize: 15 }}>{t.emoji}</span>
                {t.label}
                {(t.badge || 0) > 0 && <span style={{ position: "absolute", top: 4, right: 6, background: C.rose, color: "#fff", borderRadius: 99, padding: "0 4px", fontSize: 7, fontWeight: 700 }}>{t.badge}</span>}
              </button>
            ))}
          </div>
          <PanelContent />
        </div>

        {/* ── MAP ── */}
        <div className="dp-map" style={{ flex: 1, position: "relative" }}>
          <MapContainer center={[ship.lat, ship.lng]} zoom={7} style={{ width: "100%", height: "100%" }} zoomControl={false}>
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            />
            {crumbs.length > 1 && <Polyline positions={crumbs} pathOptions={{ color: C.slate, weight: 2, opacity: 0.4, dashArray: "4 5" }} />}
            {route.length > 1  && <Polyline positions={route}  pathOptions={{ color: C.cyan,  weight: 3, opacity: 0.8 }} />}

            {/* Truck */}
            <Marker position={[ship.lat, ship.lng]} icon={truckIcon(rc)}>
              <Popup>
                <div style={{ fontFamily: "monospace", fontSize: 12, minWidth: 160 }}>
                  <b>{ship.shipmentId}</b><br />
                  {ship.cargo} · <span style={{ color: ship.isIdeal ? "green" : "red" }}>{ship.temp}°C</span><br />
                  {ship.from} → {ship.to}<br />
                  Risk: {ship.riskLevel} · Speed: {ship.speed} km/h
                </div>
              </Popup>
            </Marker>

            {/* Hub markers — always visible, show risk reduction on marker */}
            {hubs.slice(0, 3).map((hub, i) => (
              <Marker key={hub.id} position={[hub.lat, hub.lng]} icon={hubIcon(hub.color, i + 1, hub.riskReduction)}>
                <Popup>
                  <div style={{ fontFamily: "monospace", fontSize: 12, minWidth: 170 }}>
                    <b>#{i + 1} {hub.name}</b><br />
                    {hub.type} · {hub.tempRange}<br />
                    Risk reduction: <b style={{ color: "green" }}>↓{hub.riskReduction}%</b><br />
                    {hub.distKm} km · {hub.etaMins} min ETA · {hub.capacity}% capacity
                  </div>
                </Popup>
              </Marker>
            ))}

            {/* Diversion lines */}
            {hubs.slice(0, 3).map(hub => (
              <Polyline key={"dl-" + hub.id}
                positions={[[ship.lat, ship.lng], [hub.lat, hub.lng]]}
                pathOptions={{ color: hub.color, weight: 1.5, opacity: 0.35, dashArray: "5 8" }}
              />
            ))}

            <FlyTo lat={ship.lat} lng={ship.lng} />
          </MapContainer>

          {/* Info chip top-right */}
          <div style={{ position: "absolute", top: 12, right: 12, zIndex: 900, background: "rgba(7,16,28,0.88)", backdropFilter: "blur(6px)", border: `1px solid ${rc}40`, borderRadius: 10, padding: "10px 14px", minWidth: 155, pointerEvents: "none" }}>
            <div style={{ display: "flex", gap: 5, alignItems: "center", marginBottom: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: rc, boxShadow: `0 0 6px ${rc}` }} />
              <span style={{ color: rc, fontSize: 9, fontFamily: "monospace", letterSpacing: 1 }}>{ship.riskLevel} RISK</span>
            </div>
            <div style={{ color: C.text, fontWeight: 600, fontSize: 13 }}>{ship.cargo}</div>
            <div style={{ color: C.slate, fontSize: 10, margin: "2px 0 6px" }}>{ship.from} → {ship.to}</div>
            <div style={{ color: ship.isIdeal ? C.green : C.rose, fontSize: 18, fontWeight: 700, fontFamily: "monospace" }}>{ship.temp}°C</div>
            <div style={{ color: C.dim, fontSize: 9, fontFamily: "monospace" }}>safe {ship.idealTemp}</div>
          </div>

          {/* Hub legend bottom-left */}
          <div style={{ position: "absolute", bottom: 12, left: 12, zIndex: 900, background: "rgba(7,16,28,0.85)", backdropFilter: "blur(6px)", border: `1px solid ${C.rim}`, borderRadius: 9, padding: "9px 13px", pointerEvents: "none" }}>
            <div style={{ color: C.slate, fontSize: 8, fontFamily: "monospace", letterSpacing: 2, marginBottom: 7 }}>HUBS</div>
            {hubs.slice(0, 3).map((hub, i) => (
              <div key={hub.id} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <div style={{ width: 10, height: 10, borderRadius: 3, background: hub.color, flexShrink: 0 }} />
                <span style={{ color: C.slate, fontSize: 9 }}>#{i + 1} {hub.name.split(" ")[0]}</span>
                <span style={{ color: C.green, fontSize: 9, fontFamily: "monospace", marginLeft: "auto", paddingLeft: 6 }}>↓{hub.riskReduction}%</span>
              </div>
            ))}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.rim}` }}>
              <div style={{ width: 20, height: 2, background: C.cyan, borderRadius: 1 }} />
              <span style={{ color: C.slate, fontSize: 9 }}>Route ahead</span>
            </div>
          </div>

          {/* Mobile tab bar — floats over map */}
          <div className="dp-mobile-tabs">
            {TABS.map(t => (
              <button key={t.id} onClick={() => openTab(t.id)} style={{
                flex: 1, padding: "7px 4px", background: tab === t.id ? `${C.cyan}20` : C.card,
                borderTop: `2px solid ${tab === t.id ? C.cyan : C.rim}`,
                color: tab === t.id ? C.cyan : C.slate, fontSize: 8,
                cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
                position: "relative",
              }}>
                <span style={{ fontSize: 16 }}>{t.emoji}</span>
                {t.label}
                {(t.badge || 0) > 0 && <span style={{ position: "absolute", top: 3, right: "20%", background: C.rose, color: "#fff", borderRadius: 99, padding: "0 4px", fontSize: 7, fontWeight: 700 }}>{t.badge}</span>}
              </button>
            ))}
          </div>
        </div>

        {/* ── MOBILE BOTTOM DRAWER ── */}
        <div className={`dp-drawer${drawer ? " dp-drawer-open" : ""}`}>
          <div style={{ display: "flex", alignItems: "center", padding: "10px 16px 4px", flexShrink: 0 }}>
            <div style={{ flex: 1, height: 3, width: 40, background: C.rim, borderRadius: 99, margin: "0 auto 4px", maxWidth: 40 }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0 16px 10px" }}>
            <span style={{ color: C.text, fontWeight: 600, fontSize: 14 }}>
              {TABS.find(t => t.id === tab)?.label}
            </span>
            <button onClick={() => setDrawer(false)} style={{ background: "none", border: "none", color: C.slate, fontSize: 18, cursor: "pointer", lineHeight: 1 }}>×</button>
          </div>
          <PanelContent />
        </div>
      </div>

      <style>{`
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: ${C.rim}; border-radius: 2px; }
        .leaflet-container { background: #060e1a !important; }
        .leaflet-tile { filter: brightness(0.78) saturate(0.5) hue-rotate(200deg); }
        .leaflet-control-zoom, .leaflet-control-attribution { display: none; }
        @keyframes lc-ping {
          0%   { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.8); opacity: 0; }
        }

        /* ── Desktop ── */
        .dp-body          { flex-direction: row; }
        .dp-desk-panel    { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; background: ${C.bg}; border-right: 1px solid ${C.rim}; }
        .dp-map           { flex: 1; position: relative; }
        .dp-mobile-tabs   { display: none; }
        .dp-drawer        { display: none; }

        /* ── Mobile ≤ 768 ── */
        @media (max-width: 768px) {
          .dp-body       { flex-direction: column; }
          .dp-desk-panel { display: none; }
          .dp-map        { flex: 1; height: 100%; }

          .dp-mobile-tabs {
            display: flex;
            position: absolute; bottom: 0; left: 0; right: 0;
            z-index: 800; border-top: 1px solid ${C.rim};
          }

          .dp-drawer {
            display: flex; flex-direction: column;
            position: fixed; bottom: 0; left: 0; right: 0;
            height: 66svh; z-index: 1000;
            background: ${C.bg}; border-radius: 16px 16px 0 0;
            border-top: 1px solid ${C.rim};
            transform: translateY(100%);
            transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1);
            overflow: hidden;
          }
          .dp-drawer.dp-drawer-open { transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
