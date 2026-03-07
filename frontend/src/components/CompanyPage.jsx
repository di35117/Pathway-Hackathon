/**
 * CompanyPage.jsx
 *
 * Company operations dashboard.
 * - Left panel: shipment list with search / risk filter
 * - Right: Leaflet live map (same OSM tile approach as DriverPage)
 * - All data arrives via WebSocket from backend
 * - Mock seed data used when WS is unavailable (frontend testing)
 *
 * Install:  npm install leaflet react-leaflet
 * Add to index.html / main.jsx:
 *   import 'leaflet/dist/leaflet.css';
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import { useNavigate } from "react-router-dom";

// Fix Leaflet default icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:       "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:     "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

// ── Theme ────────────────────────────────────────────────────────────────────
const T = {
  bg:        "#060C14",
  surface:   "#0D1825",
  border:    "#1A2D42",
  accent:    "#00D4FF",
  accentDim: "#0A3A4A",
  green:     "#00FF88",
  orange:    "#FF8C00",
  red:       "#FF3355",
  text:      "#E8F4FF",
  muted:     "#5A7A9A",
  dim:       "#2A4A6A",
};

const RISK_COLOR  = { LOW: T.green, MEDIUM: T.orange, HIGH: T.red };
const CARGO_COLOR = { Vaccines: "#00D4FF", Seafood: "#00FF88", Dairy: "#FFD700", "Frozen Meat": "#FF8C00" };
const CARGO_ICON  = { Vaccines: "💉", Seafood: "🐟", Dairy: "🥛", "Frozen Meat": "🥩" };

// ── Custom truck icon ─────────────────────────────────────────────────────────
const makeDot = (color) =>
  L.divIcon({
    className: "",
    html: `<div style="
      width:14px;height:14px;border-radius:50%;
      background:${color};border:2px solid #060C14;
      box-shadow:0 0 8px ${color}80;
    "></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -12],
  });

// ── Mock seed data ────────────────────────────────────────────────────────────
function makeMockShipments() {
  const routes = [
    { from:"Delhi",     to:"Mumbai",    lat:26.5,  lng:76.2  },
    { from:"Delhi",     to:"Chennai",   lat:25.0,  lng:79.0  },
    { from:"Mumbai",    to:"Kolkata",   lat:21.0,  lng:82.0  },
    { from:"Chennai",   to:"Hyderabad", lat:14.5,  lng:80.0  },
    { from:"Bangalore", to:"Mumbai",    lat:16.0,  lng:75.5  },
    { from:"Delhi",     to:"Kolkata",   lat:27.0,  lng:83.0  },
    { from:"Ahmedabad", to:"Delhi",     lat:24.5,  lng:74.0  },
    { from:"Pune",      to:"Hyderabad", lat:18.0,  lng:76.5  },
    { from:"Jaipur",    to:"Delhi",     lat:27.5,  lng:76.5  },
    { from:"Lucknow",   to:"Delhi",     lat:27.2,  lng:79.5  },
  ];
  const cargos  = ["Vaccines","Seafood","Dairy","Frozen Meat"];
  const risks   = ["LOW","LOW","LOW","MEDIUM","MEDIUM","HIGH"];
  const drivers = ["Rajesh K.","Sunil M.","Priya S.","Arun T.","Deepak V.","Meena R.","Vikram P.","Anita L.","Mohan D.","Kavya N."];
  const statuses = ["ON ROUTE","ON ROUTE","ON ROUTE","STOPPED","DIVERTING"];

  return routes.map((r, i) => {
    const cargo = cargos[i % cargos.length];
    const risk  = risks[Math.floor(Math.random() * risks.length)];
    const temp  = cargo==="Vaccines" ? +(2+Math.random()*7).toFixed(1)
                : cargo==="Seafood"  ? +(-1+Math.random()*6).toFixed(1)
                : cargo==="Dairy"    ? +(1+Math.random()*4).toFixed(1)
                : +(-20+Math.random()*6).toFixed(1);
    return {
      id:         `SHP-${String(i+1).padStart(3,"0")}`,
      from:       r.from, to: r.to,
      lat:        r.lat + (Math.random()-0.5)*0.5,
      lng:        r.lng + (Math.random()-0.5)*0.5,
      cargo, risk, driver: drivers[i],
      phone:      `+91 98${Math.floor(10+Math.random()*89)} ${Math.floor(10000+Math.random()*89999)}`,
      temp,
      isIdeal:    cargo==="Vaccines" ? (temp>=2&&temp<=8)
                : cargo==="Seafood"  ? (temp>=0&&temp<=4)
                : cargo==="Dairy"    ? (temp>=1&&temp<=4)
                : (temp>=-18&&temp<=-15),
      speed:       Math.floor(35+Math.random()*40),
      status:      statuses[Math.floor(Math.random()*statuses.length)],
      etaHrs:      Math.round((1+Math.random()*17)*10)/10,
      cargoValue:  cargo==="Vaccines" ? Math.floor(5+Math.random()*16)*100000
                 : cargo==="Seafood"  ? Math.floor(1+Math.random()*4)*100000
                 : cargo==="Dairy"    ? Math.floor(20+Math.random()*60)*1000
                 : Math.floor(50+Math.random()*150)*1000,
      compressor:  Math.random()>0.15 ? "RUNNING" : "FAULT",
      humidity:    Math.floor(60+Math.random()*35),
      riskScore:   risk==="HIGH" ? 0.7+Math.random()*0.3
                 : risk==="MEDIUM" ? 0.4+Math.random()*0.3
                 : Math.random()*0.35,
      progress:    0.05+Math.random()*0.87,
    };
  });
}

const MOCK_SHIPMENTS = makeMockShipments();

// ── Sub-components ────────────────────────────────────────────────────────────
function RiskBadge({ level }) {
  const c = RISK_COLOR[level] || T.muted;
  const bg = level==="LOW" ? "#0A3D22" : level==="MEDIUM" ? "#3D2E00" : "#3D0A14";
  return (
    <span style={{ background:bg, color:c, border:`1px solid ${c}40`, padding:"1px 7px", borderRadius:3, fontSize:9, fontWeight:"bold", letterSpacing:1, fontFamily:"Space Mono" }}>
      {level}
    </span>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ background:T.surface, border:`1px solid ${T.border}`, borderRadius:8, padding:"10px 12px", textAlign:"center" }}>
      <div style={{ color:color||T.text, fontFamily:"Space Mono", fontSize:20, fontWeight:"bold" }}>{value}</div>
      <div style={{ color:T.muted, fontSize:9, letterSpacing:1, marginTop:2 }}>{label}</div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function CompanyPage() {
  const navigate = useNavigate();
  const wsRef    = useRef(null);

  const [shipments,   setShipments]   = useState(MOCK_SHIPMENTS);
  const [selectedId,  setSelectedId]  = useState(MOCK_SHIPMENTS[0]?.id);
  const [filterRisk,  setFilterRisk]  = useState("ALL");
  const [search,      setSearch]      = useState("");

  // ── WebSocket ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const WS_URL = import.meta.env?.VITE_WS_URL || "ws://localhost:8080/ws/company";
    let ws;
    try {
      ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => console.log("[WS] Company connected");
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          /**
           * Expected backend message types:
           *
           * { type:"SHIPMENTS_INIT",  shipments: [...] }   — full initial list
           * { type:"POSITION_UPDATE", id, lat, lng, speed, temp, riskScore, riskLevel, status }
           * { type:"SHIPMENT_UPDATE", id, ...fields }       — any partial update
           */
          switch (msg.type) {
            case "SHIPMENTS_INIT":
              setShipments(msg.shipments);
              break;
            case "POSITION_UPDATE":
            case "SHIPMENT_UPDATE":
              setShipments(prev =>
                prev.map(s => s.id === msg.id ? { ...s, ...msg } : s)
              );
              break;
            default:
              break;
          }
        } catch {}
      };
      ws.onerror = () => console.warn("[WS] Company WS error — using mock data");
    } catch {
      console.warn("[WS] Could not open WebSocket — using mock data");
    }
    return () => ws?.close();
  }, []);

  const logout = () => { sessionStorage.clear(); navigate("/"); };

  // ── Filtering ─────────────────────────────────────────────────────────────
  const filtered = shipments.filter(s => {
    const q = search.toLowerCase();
    const matchQ = !q || s.id.toLowerCase().includes(q)
      || s.from.toLowerCase().includes(q) || s.to.toLowerCase().includes(q)
      || s.cargo.toLowerCase().includes(q) || s.driver.toLowerCase().includes(q);
    const matchR = filterRisk === "ALL" || s.risk === filterRisk;
    return matchQ && matchR;
  });

  const selected = shipments.find(s => s.id === selectedId) || shipments[0];

  // ── Stats ─────────────────────────────────────────────────────────────────
  const stats = {
    total:     shipments.length,
    high:      shipments.filter(s => s.risk==="HIGH").length,
    diverting: shipments.filter(s => s.status==="DIVERTING").length,
    stopped:   shipments.filter(s => s.status==="STOPPED").length,
    totalVal:  shipments.reduce((a,s) => a+s.cargoValue, 0),
  };

  return (
    <div style={{ width:"100vw", height:"100vh", background:T.bg, display:"flex", flexDirection:"column", fontFamily:"'Space Mono',monospace", overflow:"hidden" }}>

      {/* ── Top bar ── */}
      <div style={{ height:48, background:T.surface, borderBottom:`1px solid ${T.border}`, display:"flex", alignItems:"center", padding:"0 20px", gap:14, flexShrink:0, zIndex:20 }}>
        <span style={{ fontSize:16 }}>❄️</span>
        <span style={{ color:T.accent, fontSize:13, fontWeight:"bold", letterSpacing:2 }}>LIVECOLD</span>
        <span style={{ color:T.dim, fontSize:9 }}>COMPANY OPS</span>
        <div style={{ flex:1 }} />

        {/* Live summary chips */}
        <div style={{ display:"flex", gap:6 }}>
          {stats.high > 0 && (
            <span style={{ background:T.red+"20", border:`1px solid ${T.red}50`, borderRadius:16, padding:"3px 10px", color:T.red, fontSize:9 }}>
              {stats.high} HIGH RISK
            </span>
          )}
          {stats.diverting > 0 && (
            <span style={{ background:T.orange+"20", border:`1px solid ${T.orange}50`, borderRadius:16, padding:"3px 10px", color:T.orange, fontSize:9 }}>
              {stats.diverting} DIVERTING
            </span>
          )}
          <span style={{ background:T.green+"15", border:`1px solid ${T.green}30`, borderRadius:16, padding:"3px 10px", color:T.green, fontSize:9, display:"flex", alignItems:"center", gap:5 }}>
            <span style={{ width:5, height:5, borderRadius:"50%", background:T.green, display:"inline-block", animation:"pulse 1.5s infinite" }} />
            {stats.total} ACTIVE
          </span>
        </div>

        <button onClick={logout} style={{ background:"transparent", border:`1px solid ${T.border}`, borderRadius:6, color:T.muted, fontSize:9, padding:"4px 10px", cursor:"pointer" }}>
          SIGN OUT
        </button>
      </div>

      {/* ── Body ── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* ── Left panel ── */}
        <div style={{ width:360, flexShrink:0, borderRight:`1px solid ${T.border}`, display:"flex", flexDirection:"column", overflow:"hidden" }}>

          {/* Stats row */}
          <div style={{ padding:"12px 14px", borderBottom:`1px solid ${T.border}`, flexShrink:0 }}>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:6, marginBottom:10 }}>
              <StatCard label="ACTIVE"    value={stats.total}     color={T.text}  />
              <StatCard label="HIGH RISK" value={stats.high}      color={T.red}   />
              <StatCard label="DIVERTING" value={stats.diverting} color={T.orange}/>
              <StatCard label="STOPPED"   value={stats.stopped}   color={T.muted} />
            </div>

            {/* Total value */}
            <div style={{ background:T.surface, border:`1px solid ${T.border}`, borderRadius:6, padding:"7px 10px", display:"flex", justifyContent:"space-between", marginBottom:10 }}>
              <span style={{ color:T.muted, fontSize:9 }}>TOTAL CARGO VALUE MONITORED</span>
              <span style={{ color:T.green, fontWeight:"bold", fontSize:11 }}>
                ₹{(stats.totalVal/10000000).toFixed(1)} Cr
              </span>
            </div>

            {/* Search */}
            <div style={{ position:"relative", marginBottom:8 }}>
              <span style={{ position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", color:T.muted, fontSize:12 }}>⌕</span>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="ID, city, cargo, driver…"
                style={{ width:"100%", background:T.bg, border:`1px solid ${T.border}`, borderRadius:6, padding:"7px 10px 7px 28px", color:T.text, fontSize:11, fontFamily:"Space Mono", outline:"none", boxSizing:"border-box" }}
              />
            </div>

            {/* Risk filter */}
            <div style={{ display:"flex", gap:5 }}>
              {["ALL","LOW","MEDIUM","HIGH"].map(r => {
                const c = r==="ALL" ? T.accent : RISK_COLOR[r];
                return (
                  <button key={r} onClick={() => setFilterRisk(r)}
                    style={{ flex:1, padding:"4px 0", background:filterRisk===r ? c+"20" : T.bg,
                      border:`1px solid ${filterRisk===r ? c : T.border}`, borderRadius:4,
                      color:filterRisk===r ? c : T.muted, fontSize:9, cursor:"pointer", fontFamily:"Space Mono", letterSpacing:1 }}>
                    {r}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Shipment list */}
          <div style={{ flex:1, overflowY:"auto", padding:"8px 10px" }}>
            {filtered.map(s => {
              const isSelected = s.id === selectedId;
              const cc = CARGO_COLOR[s.cargo] || T.accent;
              return (
                <div key={s.id}
                  onClick={() => setSelectedId(s.id)}
                  style={{ background:isSelected ? `${cc}0E` : T.surface,
                    border:`1px solid ${isSelected ? cc+"50" : T.border}`,
                    borderLeft:`3px solid ${RISK_COLOR[s.risk]}`,
                    borderRadius:8, padding:"9px 11px", marginBottom:5, cursor:"pointer", transition:"all 0.12s" }}>

                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:4 }}>
                    <div style={{ display:"flex", alignItems:"center", gap:7 }}>
                      <span style={{ color:T.accent, fontSize:10, fontWeight:"bold" }}>{s.id}</span>
                      <span style={{ fontSize:11 }}>{CARGO_ICON[s.cargo]}</span>
                      <span style={{ color:cc, fontSize:9 }}>{s.cargo}</span>
                    </div>
                    <RiskBadge level={s.risk} />
                  </div>

                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                    <span style={{ color:T.muted, fontSize:10 }}>
                      <span style={{ color:T.text }}>{s.from}</span>
                      <span style={{ color:T.dim, margin:"0 4px" }}>→</span>
                      <span style={{ color:T.text }}>{s.to}</span>
                    </span>
                    <div style={{ display:"flex", gap:8 }}>
                      <span style={{ color:s.isIdeal ? T.green : T.red, fontSize:10 }}>{s.temp}°C</span>
                      <span style={{ color:T.muted, fontSize:10 }}>{s.etaHrs}h</span>
                      <span style={{ color:s.status==="DIVERTING"?T.orange:s.status==="STOPPED"?T.muted:T.green, fontSize:9 }}>
                        {s.status==="ON ROUTE"?"●":s.status==="STOPPED"?"■":"▲"} {s.status}
                      </span>
                    </div>
                  </div>

                  {/* Expanded detail on selection */}
                  {isSelected && (
                    <div style={{ marginTop:8, paddingTop:8, borderTop:`1px solid ${T.border}`, display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:5 }}>
                      {[
                        { l:"SPEED",      v:`${s.speed} km/h`,    c:T.text   },
                        { l:"HUMIDITY",   v:`${s.humidity}%`,      c:T.accent },
                        { l:"COMPRESSOR", v:s.compressor,          c:s.compressor==="RUNNING"?T.green:T.red },
                        { l:"DRIVER",     v:s.driver,              c:T.muted  },
                        { l:"PHONE",      v:s.phone,               c:T.muted  },
                        { l:"VALUE",      v:`₹${(s.cargoValue/100000).toFixed(1)}L`, c:T.green },
                      ].map(({ l, v, c }) => (
                        <div key={l} style={{ background:T.bg, borderRadius:4, padding:"4px 6px" }}>
                          <div style={{ color:T.dim, fontSize:8, letterSpacing:1 }}>{l}</div>
                          <div style={{ color:c, fontSize:9, marginTop:1 }}>{v}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {filtered.length === 0 && (
              <div style={{ textAlign:"center", color:T.muted, fontSize:12, padding:40 }}>NO SHIPMENTS FOUND</div>
            )}
          </div>
        </div>

        {/* ── Right: Leaflet map ── */}
        <div style={{ flex:1, position:"relative", overflow:"hidden" }}>
          <MapContainer
            center={[22, 80]}
            zoom={5}
            style={{ width:"100%", height:"100%" }}
            zoomControl={true}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* All trucks */}
            {shipments.map(s => (
              <Marker
                key={s.id}
                position={[s.lat, s.lng]}
                icon={makeDot(RISK_COLOR[s.risk])}
                eventHandlers={{ click: () => setSelectedId(s.id) }}
              >
                <Popup>
                  <div style={{ fontFamily:"monospace", fontSize:12, minWidth:130 }}>
                    <strong>{s.id}</strong><br />
                    {CARGO_ICON[s.cargo]} {s.cargo}<br />
                    {s.from} → {s.to}<br />
                    Temp: <span style={{ color: s.isIdeal ? "green" : "red" }}>{s.temp}°C</span><br />
                    Risk: {s.risk} · {s.etaHrs}h ETA<br />
                    Driver: {s.driver}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>

          {/* Selected shipment overlay card */}
          {selected && (
            <div style={{ position:"absolute", top:12, right:12, zIndex:1000, background:"rgba(6,12,20,0.92)", border:`1px solid ${CARGO_COLOR[selected.cargo]}50`, borderRadius:8, padding:"12px 14px", minWidth:180 }}>
              <div style={{ color:T.accent, fontSize:9, letterSpacing:2, marginBottom:6 }}>SELECTED SHIPMENT</div>
              <div style={{ color:T.text, fontSize:14, fontWeight:"bold" }}>{selected.id}</div>
              <div style={{ color:T.muted, fontSize:10, marginTop:2 }}>{CARGO_ICON[selected.cargo]} {selected.cargo}</div>
              <div style={{ color:T.muted, fontSize:10, marginTop:4 }}>{selected.from} → {selected.to}</div>
              <div style={{ display:"flex", gap:8, marginTop:6, alignItems:"center" }}>
                <span style={{ color:selected.isIdeal ? T.green : T.red, fontSize:12, fontWeight:"bold" }}>{selected.temp}°C</span>
                <RiskBadge level={selected.risk} />
              </div>
              <div style={{ color:T.muted, fontSize:9, marginTop:6 }}>Driver: {selected.driver}</div>
            </div>
          )}

          {/* Legend */}
          <div style={{ position:"absolute", bottom:12, left:12, zIndex:1000, background:"rgba(6,12,20,0.85)", border:`1px solid ${T.border}`, borderRadius:8, padding:"9px 13px" }}>
            <div style={{ color:T.muted, fontSize:8, letterSpacing:2, marginBottom:7 }}>RISK LEVEL</div>
            {["LOW","MEDIUM","HIGH"].map(r => (
              <div key={r} style={{ display:"flex", alignItems:"center", gap:6, marginBottom:4 }}>
                <div style={{ width:8, height:8, borderRadius:"50%", background:RISK_COLOR[r] }} />
                <span style={{ color:T.muted, fontSize:9 }}>{r}</span>
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
        .leaflet-tile { filter: brightness(0.82) saturate(0.55) hue-rotate(195deg); }
      `}</style>
    </div>
  );
}
