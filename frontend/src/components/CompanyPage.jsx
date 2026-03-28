/**
 * CompanyPage.jsx
 * 25 trucks live on Leaflet | Analytics tab | CSV report download | Mobile responsive
 * WS: SHIPMENTS_INIT | POSITION_UPDATE | SHIPMENT_UPDATE | ANALYTICS_UPDATE
 */

import { useState, useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import { useNavigate } from "react-router-dom";
import { formatINR } from "../utils/helpers";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
  iconUrl:       "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
  shadowUrl:     "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
});

// ─── palette ──────────────────────────────────────────────────────────────────
const C = {
  bg:    "#07101c", card:  "#0e1d2e", rim:   "#162840",
  cyan:  "#2dd4bf", blue:  "#38bdf8", green: "#4ade80",
  amber: "#fbbf24", rose:  "#f87171", slate: "#94a3b8",
  dim:   "#334155", text:  "#e2e8f0", purple: "#a78bfa",
};
const RISK  = { LOW: "#4ade80", MEDIUM: "#fbbf24", HIGH: "#f87171" };
const CARGO = { Vaccines: "#38bdf8", Seafood: "#4ade80", Dairy: "#fbbf24", "Frozen Meat": "#f97316" };
const CARGO_EMOJI = { Vaccines: "💉", Seafood: "🐟", Dairy: "🥛", "Frozen Meat": "🥩" };

const dotIcon = (col) => L.divIcon({
  className: "",
  html: `<div style="width:14px;height:14px;border-radius:50%;background:${col};border:2.5px solid #07101c;box-shadow:0 0 10px ${col}90"></div>`,
  iconSize: [14, 14], iconAnchor: [7, 7], popupAnchor: [0, -10],
});

// ─── 25 mock trucks ────────────────────────────────────────────────────────────
function mockFleet() {
  const routes = [
    ["Delhi","Mumbai",[27.8,77.4]],["Delhi","Chennai",[25.2,79.1]],
    ["Mumbai","Kolkata",[20.9,82.7]],["Chennai","Hyderabad",[15.3,79.2]],
    ["Bangalore","Mumbai",[16.8,75.1]],["Delhi","Kolkata",[26.5,81.3]],
    ["Ahmedabad","Delhi",[25.8,74.1]],["Pune","Hyderabad",[17.9,76.8]],
    ["Jaipur","Delhi",[27.3,75.9]],["Lucknow","Delhi",[26.8,79.2]],
    ["Nagpur","Mumbai",[21.2,78.1]],["Chandigarh","Delhi",[29.8,76.5]],
    ["Indore","Mumbai",[20.9,74.2]],["Bhopal","Delhi",[24.1,77.2]],
    ["Surat","Delhi",[23.1,73.4]],["Chennai","Kolkata",[16.2,81.9]],
    ["Hyderabad","Mumbai",[18.1,76.5]],["Delhi","Bangalore",[22.3,77.8]],
    ["Ahmedabad","Mumbai",[21.9,72.7]],["Jaipur","Mumbai",[22.8,73.9]],
    ["Pune","Delhi",[20.5,75.1]],["Lucknow","Mumbai",[23.9,79.8]],
    ["Nagpur","Hyderabad",[19.8,79.2]],["Chandigarh","Mumbai",[26.3,75.2]],
    ["Indore","Delhi",[23.4,76.3]],
  ];
  const cargos  = ["Vaccines","Seafood","Dairy","Frozen Meat"];
  const risks   = ["LOW","LOW","LOW","MEDIUM","MEDIUM","HIGH"];
  const drivers = ["Rajesh K.","Sunil M.","Priya S.","Arun T.","Deepak V.","Meena R.","Vikram P.","Anita L.","Mohan D.","Kavya N.","Ravi J.","Sunita G.","Arjun B.","Pooja S.","Kiran T.","Nikhil A.","Rekha M.","Sanjay K.","Leela P.","Bharat R.","Chitra V.","Dinesh N.","Geeta S.","Hari M.","Indira L."];
  const statuses = ["ON ROUTE","ON ROUTE","ON ROUTE","STOPPED","DIVERTING"];

  return routes.map(([from, to, pos], i) => {
    const cargo = cargos[i % 4];
    const risk  = risks[Math.floor(Math.abs(Math.sin(i * 137)) * 6)];
    const temp  = cargo === "Vaccines" ? +(2 + Math.abs(Math.sin(i)) * 6).toFixed(1)
                : cargo === "Seafood"  ? +(-1 + Math.abs(Math.cos(i)) * 5).toFixed(1)
                : cargo === "Dairy"    ? +(1 + Math.abs(Math.sin(i * 2)) * 3).toFixed(1)
                : +(-20 + Math.abs(Math.cos(i * 2)) * 4).toFixed(1);
    const isIdeal = cargo === "Vaccines" ? temp >= 2 && temp <= 8
                  : cargo === "Seafood"  ? temp >= -1 && temp <= 4
                  : cargo === "Dairy"    ? temp >= 0 && temp <= 4
                  : temp >= -20 && temp <= -15;
    return {
      id: `SHP-${String(i + 1).padStart(3, "0")}`,
      from, to,
      lat: pos[0] + (Math.cos(i * 31) * 0.25),
      lng: pos[1] + (Math.sin(i * 31) * 0.25),
      cargo, risk, riskScore: risk === "HIGH" ? 0.75 + Math.abs(Math.sin(i)) * 0.2 : risk === "MEDIUM" ? 0.45 + Math.abs(Math.cos(i)) * 0.15 : Math.abs(Math.sin(i * 3)) * 0.3,
      driver: drivers[i], phone: `+91 98${Math.floor(10 + Math.abs(Math.sin(i * 7)) * 89)}${Math.floor(10000 + Math.abs(Math.cos(i * 11)) * 89999)}`,
      temp, isIdeal, speed: Math.floor(38 + Math.abs(Math.sin(i * 5)) * 38),
      status: statuses[Math.floor(Math.abs(Math.cos(i * 3)) * 5)],
      etaHrs: Math.round((1.5 + Math.abs(Math.sin(i * 2)) * 16) * 10) / 10,
      cargoValue: cargo === "Vaccines" ? (5 + Math.floor(Math.abs(Math.sin(i)) * 15)) * 100000 : (20 + Math.floor(Math.abs(Math.cos(i)) * 80)) * 10000,
      compressor: Math.abs(Math.sin(i * 13)) > 0.12 ? "RUNNING" : "FAULT",
      humidity: Math.floor(60 + Math.abs(Math.cos(i * 7)) * 30),
    };
  });
}

const FLEET = mockFleet();

// ─── mock analytics ────────────────────────────────────────────────────────────
const MOCK_ANA = {
  carbonCredits: 760000, co2Avoided: 756.9,
  cargoSaved: 11000000, roi: 191408,
  activeShipments: 25, events: 4900,
  anomalies: 458, sensorReliability: 90.7,
  byProduct: [
    { name: "Dairy",       co2: 48.0,  val: 48000,  div: 3, color: CARGO["Dairy"]        },
    { name: "Frozen Meat", co2: 404.9, val: 404000, div: 3, color: CARGO["Frozen Meat"]  },
    { name: "Seafood",     co2: 54.0,  val: 54000,  div: 2, color: CARGO["Seafood"]       },
    { name: "Vaccines",    co2: 250.0, val: 250000, div: 1, color: CARGO["Vaccines"]      },
  ],
  anomalyRows: [
    { label: "L1: Bounds",  n: 159, col: C.rose   },
    { label: "L2: Rate",    n: 249, col: C.amber   },
    { label: "L3: Z-Score", n: 49,  col: C.cyan    },
    { label: "L4: Stuck",   n: 0,   col: C.purple  },
  ],
  fin: { saved: 1100000, divert: 85000, co2cost: 42000 },
  pipe: { events: 4900, highRisk: 11, diversions: 11, uptime: "6m 33s" },
};

// ─── components ────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, color }) {
  return (
    <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "16px 18px", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span style={{ color: C.slate, fontSize: 9, fontFamily: "monospace", letterSpacing: 1.5, textTransform: "uppercase" }}>{label}</span>
      </div>
      <div style={{ color: color || C.text, fontSize: 26, fontWeight: 700, fontFamily: "monospace", lineHeight: 1, marginBottom: 5 }}>{value}</div>
      <div style={{ color: C.dim, fontSize: 11 }}>{sub}</div>
    </div>
  );
}

function AnomalyBar({ label, n, col, max }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
        <span style={{ color: C.slate, fontSize: 12 }}>{label}</span>
        <span style={{ color: C.text, fontFamily: "monospace", fontSize: 13, fontWeight: 600 }}>{n}</span>
      </div>
      <div style={{ height: 7, background: C.rim, borderRadius: 99, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${max > 0 ? (n / max) * 100 : 0}%`, background: col, borderRadius: 99, minWidth: n > 0 ? 6 : 0, transition: "width 0.7s ease" }} />
      </div>
    </div>
  );
}

// Simple SVG donut
function Donut({ slices, size = 140 }) {
  const r = size * 0.35, cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  const total = slices.reduce((s, d) => s + d.val, 0);
  let offset = circ * 0.25;
  return (
    <svg width={size} height={size}>
      {slices.map((d, i) => {
        const dash = total > 0 ? (d.val / total) * circ : 0;
        const el = (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none"
            stroke={d.color} strokeWidth={size * 0.13}
            strokeDasharray={`${dash} ${circ - dash}`}
            strokeDashoffset={offset} strokeLinecap="butt"
          />
        );
        offset -= dash;
        return el;
      })}
      <circle cx={cx} cy={cy} r={r * 0.58} fill={C.card} />
    </svg>
  );
}

function RiskTag({ risk }) {
  const col = RISK[risk] || C.slate;
  const bg  = risk === "LOW" ? "#0c2a1a" : risk === "MEDIUM" ? "#2a1f00" : "#2a0d10";
  return (
    <span style={{ background: bg, color: col, border: `1px solid ${col}40`, borderRadius: 10, padding: "1px 8px", fontSize: 9, fontFamily: "monospace", fontWeight: 700, letterSpacing: 0.5 }}>
      {risk}
    </span>
  );
}

// ─── analytics view ────────────────────────────────────────────────────────────
function Analytics({ data, date, setDate, onDownload, dlLoading }) {
  const max = Math.max(...data.anomalyRows.map(r => r.n), 1);
  const donutData = [
    { val: data.fin.saved,  color: C.green  },
    { val: data.fin.divert, color: C.amber  },
    { val: data.fin.co2cost, color: C.rose  },
  ];
  return (
    <div className="cp-analytics" style={{ flex: 1, overflowY: "auto", padding: 20 }}>

      {/* KPI row */}
      <div className="cp-grid-4" style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12, marginBottom: 16 }}>
        <StatCard icon="🌿" label="Carbon credits" value={`₹${(data.carbonCredits / 100000).toFixed(1)}L`} sub={`${data.co2Avoided}t CO₂ avoided`}       color={C.green} />
        <StatCard icon="💰" label="Cargo saved"    value={`₹${(data.cargoSaved / 10000000).toFixed(1)}Cr`} sub={`ROI ${data.roi.toLocaleString()}%`}        color={C.amber} />
        <StatCard icon="🚛" label="Active trucks"  value={data.activeShipments}                             sub={`${data.events.toLocaleString()} events`}   color={C.text}  />
        <StatCard icon="🛡" label="Anomalies"      value={data.anomalies}                                   sub={`${data.sensorReliability}% reliability`}   color={C.rose}  />
      </div>

      {/* Mid row */}
      <div className="cp-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>

        {/* Carbon by product */}
        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "18px 18px" }}>
          <div style={{ color: C.green, fontSize: 9, fontFamily: "monospace", letterSpacing: 2, marginBottom: 14 }}>CARBON BY PRODUCT</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
            {data.byProduct.map(p => (
              <div key={p.name} style={{ background: C.bg, borderRadius: 9, padding: "11px 13px", borderTop: `3px solid ${p.color}` }}>
                <div style={{ color: C.slate, fontSize: 10, marginBottom: 4 }}>{p.name}</div>
                <div style={{ color: C.text, fontSize: 20, fontWeight: 700, fontFamily: "monospace" }}>{p.co2}t</div>
                <div style={{ color: C.dim, fontSize: 10, marginTop: 3 }}>₹{(p.val / 1000).toFixed(0)}K · {p.div} diversions</div>
              </div>
            ))}
          </div>
        </div>

        {/* Anomaly breakdown */}
        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "18px 18px" }}>
          <div style={{ color: C.rose, fontSize: 9, fontFamily: "monospace", letterSpacing: 2, marginBottom: 16 }}>ANOMALY DETECTION</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {data.anomalyRows.map(r => <AnomalyBar key={r.label} {...r} max={max} />)}
          </div>
        </div>
      </div>

      {/* Bottom row */}
      <div className="cp-grid-2" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>

        {/* Donut */}
        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "18px 18px" }}>
          <div style={{ color: C.blue, fontSize: 9, fontFamily: "monospace", letterSpacing: 2, marginBottom: 16 }}>FINANCIAL OVERVIEW</div>
          <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
            <Donut slices={donutData} size={140} />
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { label: "Cargo saved",     val: data.fin.saved,   color: C.green },
                { label: "Diversion costs", val: data.fin.divert,  color: C.amber },
                { label: "CO₂ costs",       val: data.fin.co2cost, color: C.rose  },
              ].map(d => (
                <div key={d.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 10, height: 10, borderRadius: 3, background: d.color, flexShrink: 0 }} />
                  <div>
                    <div style={{ color: C.text, fontSize: 12, fontFamily: "monospace", fontWeight: 600 }}>₹{(d.val / 1000).toFixed(0)}K</div>
                    <div style={{ color: C.slate, fontSize: 9 }}>{d.label}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pipeline */}
        <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "18px 18px" }}>
          <div style={{ color: C.amber, fontSize: 9, fontFamily: "monospace", letterSpacing: 2, marginBottom: 16 }}>PIPELINE PERFORMANCE</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 18 }}>
            {[
              { l: "Events",     v: data.pipe.events.toLocaleString(), c: C.text  },
              { l: "High risk",  v: data.pipe.highRisk,                c: C.rose  },
              { l: "Diversions", v: data.pipe.diversions,               c: C.amber },
              { l: "Uptime",     v: data.pipe.uptime,                   c: C.green },
            ].map(d => (
              <div key={d.l}>
                <div style={{ color: C.slate, fontSize: 10, marginBottom: 3 }}>{d.l}</div>
                <div style={{ color: d.c, fontSize: 22, fontWeight: 700, fontFamily: "monospace", lineHeight: 1 }}>{d.v}</div>
              </div>
            ))}
          </div>
          {/* Architecture */}
          <div style={{ borderTop: `1px solid ${C.rim}`, paddingTop: 12 }}>
            <div style={{ color: C.dim, fontSize: 9, fontFamily: "monospace", marginBottom: 7 }}>Architecture</div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
              {["Sensors","MQTT","Pipeline","MQTT decisions","Dashboard"].map((s, i, a) => (
                <span key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ background: s === "Pipeline" ? `${C.cyan}20` : C.bg, border: `1px solid ${s === "Pipeline" ? C.cyan : C.rim}`, color: s === "Pipeline" ? C.cyan : C.slate, borderRadius: 4, padding: "2px 7px", fontSize: 9, fontFamily: "monospace" }}>{s}</span>
                  {i < a.length - 1 && <span style={{ color: C.dim }}>→</span>}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Download report */}
      <div style={{ background: C.card, border: `1px solid ${C.rim}`, borderRadius: 11, padding: "16px 20px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
        <div>
          <div style={{ color: C.text, fontSize: 14, fontWeight: 600, marginBottom: 3 }}>Daily operations report</div>
          <div style={{ color: C.slate, fontSize: 12 }}>Download a full CSV for any date — shipments, alerts, and analytics.</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <input type="date" value={date} onChange={e => setDate(e.target.value)}
            style={{ background: C.bg, border: `1px solid ${C.rim}`, borderRadius: 7, color: C.text, padding: "8px 12px", fontSize: 12, fontFamily: "monospace", outline: "none", cursor: "pointer" }}
          />
          <button onClick={onDownload} disabled={dlLoading} style={{
            background: dlLoading ? C.dim + "30" : `${C.cyan}15`, border: `1px solid ${dlLoading ? C.dim : C.cyan}`,
            borderRadius: 7, color: dlLoading ? C.dim : C.cyan,
            padding: "8px 20px", fontSize: 12, fontFamily: "monospace", cursor: dlLoading ? "not-allowed" : "pointer",
          }}>
            {dlLoading ? "Generating…" : "⬇ Download CSV"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── main ──────────────────────────────────────────────────────────────────────
export default function CompanyPage() {
  const navigate = useNavigate();
  const [view,      setView]      = useState("map");
  const [ships,     setShips]     = useState(FLEET);
  const [selId,     setSelId]     = useState(FLEET[0]?.id);
  const [filter,    setFilter]    = useState("ALL");
  const [search,    setSearch]    = useState("");
  const [ana,       setAna]       = useState(MOCK_ANA);
  const [date,      setDate]      = useState(new Date().toISOString().split("T")[0]);
  const [dlLoading, setDlLoading] = useState(false);
  const [listOpen,  setListOpen]  = useState(false); // mobile
  const wsRef = useRef(null);

  // WebSocket
  useEffect(() => {
    const url = (import.meta.env?.VITE_WS_URL || "ws://localhost:8080") + "/ws/company";
    let ws;
    try {
      ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onmessage = ({ data }) => {
        try {
          const m = JSON.parse(data);
          if      (m.type === "SHIPMENTS_INIT")   setShips(m.shipments);
          else if (m.type === "POSITION_UPDATE" || m.type === "SHIPMENT_UPDATE")
            setShips(p => p.map(s => s.id === m.id ? { ...s, ...m } : s));
          else if (m.type === "ANALYTICS_UPDATE") setAna(p => ({ ...p, ...m }));
        } catch {}
      };
    } catch {}
    return () => ws?.close();
  }, []);

  // Initial REST
  useEffect(() => {
    const tok = sessionStorage.getItem("livecold_token");
    fetch("/api/company/shipments", { headers: { Authorization: `Bearer ${tok}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.shipments) setShips(d.shipments); })
      .catch(() => {});
  }, []);

  // Analytics on date change
  useEffect(() => {
    if (view !== "analytics") return;
    const tok = sessionStorage.getItem("livecold_token");
    fetch(`/api/company/analytics?date=${date}`, { headers: { Authorization: `Bearer ${tok}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setAna(d); })
      .catch(() => {});
  }, [date, view]);

  const downloadCSV = async () => {
    setDlLoading(true);
    try {
      const tok = sessionStorage.getItem("livecold_token");
      const res = await fetch(`/api/company/report/download?date=${date}&format=csv`, { headers: { Authorization: `Bearer ${tok}` } });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a"); a.href = url; a.download = `livecold-${date}.csv`; a.click();
        URL.revokeObjectURL(url);
      } else {
        // client-side fallback
        const rows = ["ID,From,To,Cargo,Driver,Status,Temp,Risk,Value",
          ...ships.map(s => `${s.id},${s.from},${s.to},${s.cargo},${s.driver},${s.status},${s.temp},${s.risk},${s.cargoValue}`)].join("\n");
        const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([rows], { type: "text/csv" }));
        a.download = `livecold-${date}.csv`; a.click();
      }
    } catch {}
    setDlLoading(false);
  };

  const logout  = () => { sessionStorage.clear(); navigate("/"); };
  const sel     = ships.find(s => s.id === selId) || ships[0];
  const totVal  = ships.reduce((a, s) => a + s.cargoValue, 0);
  const counts  = { total: ships.length, high: ships.filter(s => s.risk === "HIGH").length, diverting: ships.filter(s => s.status === "DIVERTING").length, stopped: ships.filter(s => s.status === "STOPPED").length };

  const filtered = ships.filter(s => {
    const q = search.toLowerCase();
    return (!q || [s.id, s.from, s.to, s.cargo, s.driver].some(f => f.toLowerCase().includes(q)))
      && (filter === "ALL" || s.risk === filter);
  });

  return (
    <div style={{ width: "100vw", height: "100svh", background: C.bg, display: "flex", flexDirection: "column", fontFamily: "'Outfit', sans-serif", overflow: "hidden" }}>

      {/* Top bar */}
      <div style={{ height: 50, background: C.card, borderBottom: `1px solid ${C.rim}`, display: "flex", alignItems: "center", padding: "0 16px", gap: 12, flexShrink: 0, zIndex: 30, flexWrap: "nowrap" }}>
        <span style={{ color: C.cyan, fontSize: 15, fontWeight: 700, flexShrink: 0 }}>❄ LiveCold</span>
        {/* View switcher */}
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {[{ id: "map", label: "Operations" }, { id: "analytics", label: "Analytics" }].map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              background: view === v.id ? `${C.cyan}18` : "transparent",
              border: `1px solid ${view === v.id ? C.cyan : C.rim}`,
              borderRadius: 7, color: view === v.id ? C.cyan : C.slate,
              fontSize: 11, padding: "4px 12px", cursor: "pointer", fontFamily: "inherit",
            }}>{v.label}</button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {counts.high > 0 && <span style={{ background: `${C.rose}18`, border: `1px solid ${C.rose}40`, borderRadius: 14, padding: "2px 9px", color: C.rose, fontSize: 9, fontFamily: "monospace" }}>{counts.high} HIGH</span>}
          <span style={{ background: `${C.green}12`, border: `1px solid ${C.green}30`, borderRadius: 14, padding: "2px 9px", color: C.green, fontSize: 9, fontFamily: "monospace", display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 5, height: 5, borderRadius: "50%", background: C.green, display: "inline-block", animation: "cpPulse 1.8s ease-in-out infinite" }} />
            {counts.total} live
          </span>
        </div>
        <button onClick={logout} style={{ background: "none", border: `1px solid ${C.rim}`, borderRadius: 6, color: C.slate, fontSize: 10, padding: "4px 10px", cursor: "pointer", flexShrink: 0 }}>
          Sign out
        </button>
      </div>

      {/* Analytics view */}
      {view === "analytics" && (
        <Analytics data={ana} date={date} setDate={setDate} onDownload={downloadCSV} dlLoading={dlLoading} />
      )}

      {/* Map view */}
      {view === "map" && (
        <div className="cp-map-body" style={{ flex: 1, display: "flex", overflow: "hidden", position: "relative" }}>

          {/* ── LEFT PANEL ── */}
          <div className="cp-list-panel">
            {/* Stats row */}
            <div style={{ padding: "11px 13px", borderBottom: `1px solid ${C.rim}`, flexShrink: 0 }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 6, marginBottom: 9 }}>
                {[
                  { l: "Active",    v: counts.total,     c: C.text  },
                  { l: "High risk", v: counts.high,      c: C.rose  },
                  { l: "Diverting", v: counts.diverting, c: C.amber },
                  { l: "Stopped",   v: counts.stopped,   c: C.slate },
                ].map(({ l, v, c }) => (
                  <div key={l} style={{ background: C.bg, border: `1px solid ${C.rim}`, borderRadius: 8, padding: "7px 5px", textAlign: "center" }}>
                    <div style={{ color: c, fontSize: 18, fontWeight: 700, fontFamily: "monospace" }}>{v}</div>
                    <div style={{ color: C.dim, fontSize: 8, marginTop: 1 }}>{l}</div>
                  </div>
                ))}
              </div>
              <div style={{ background: C.bg, border: `1px solid ${C.rim}`, borderRadius: 6, padding: "5px 10px", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 9 }}>
                <span style={{ color: C.slate, fontSize: 10 }}>Total value monitored</span>
                <span style={{ color: C.green, fontWeight: 700, fontSize: 12, fontFamily: "monospace" }}>₹{(totVal / 10000000).toFixed(1)} Cr</span>
              </div>
              {/* Search */}
              <div style={{ position: "relative", marginBottom: 7 }}>
                <span style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", color: C.dim, fontSize: 14, pointerEvents: "none" }}>⌕</span>
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search ID, city, cargo…"
                  style={{ width: "100%", background: C.bg, border: `1px solid ${C.rim}`, borderRadius: 7, padding: "7px 10px 7px 28px", color: C.text, fontSize: 11, fontFamily: "inherit", outline: "none", boxSizing: "border-box" }} />
              </div>
              {/* Risk filter */}
              <div style={{ display: "flex", gap: 4 }}>
                {["ALL","LOW","MEDIUM","HIGH"].map(r => {
                  const col = r === "ALL" ? C.cyan : RISK[r];
                  return (
                    <button key={r} onClick={() => setFilter(r)} style={{
                      flex: 1, padding: "5px 0",
                      background: filter === r ? `${col}18` : C.bg,
                      border: `1px solid ${filter === r ? col : C.rim}`,
                      borderRadius: 6, color: filter === r ? col : C.dim,
                      fontSize: 9, cursor: "pointer", fontFamily: "monospace",
                    }}>{r}</button>
                  );
                })}
              </div>
            </div>

            {/* Shipment list */}
            <div style={{ flex: 1, overflowY: "auto" }}>
              {filtered.map(s => {
                const isSel = s.id === selId;
                const rc    = RISK[s.risk];
                const cc    = CARGO[s.cargo] || C.cyan;
                return (
                  <div key={s.id} onClick={() => setSelId(s.id)} style={{
                    padding: "10px 13px", cursor: "pointer",
                    background: isSel ? `${cc}0a` : "transparent",
                    borderBottom: `1px solid ${C.rim}`,
                    borderLeft: `3px solid ${isSel ? cc : rc}`,
                    transition: "background 0.15s",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ color: C.blue, fontFamily: "monospace", fontSize: 11, fontWeight: 600 }}>{s.id}</span>
                        <span style={{ fontSize: 12 }}>{CARGO_EMOJI[s.cargo]}</span>
                        <span style={{ color: cc, fontSize: 10 }}>{s.cargo}</span>
                      </div>
                      <RiskTag risk={s.risk} />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ color: C.slate, fontSize: 11 }}>
                        <span style={{ color: C.text }}>{s.from}</span>
                        <span style={{ color: C.dim, margin: "0 5px" }}>→</span>
                        <span style={{ color: C.text }}>{s.to}</span>
                      </span>
                      <div style={{ display: "flex", gap: 9, alignItems: "center" }}>
                        <span style={{ color: s.isIdeal ? C.green : C.rose, fontFamily: "monospace", fontSize: 11 }}>{s.temp}°C</span>
                        <span style={{ color: s.status === "DIVERTING" ? C.amber : s.status === "STOPPED" ? C.slate : C.green, fontSize: 9, fontFamily: "monospace" }}>
                          {s.status === "ON ROUTE" ? "● MOVING" : s.status}
                        </span>
                      </div>
                    </div>

                    {/* Expanded when selected */}
                    {isSel && (
                      <div style={{ marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.rim}`, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 6 }}>
                        {[
                          { l: "Speed",      v: `${s.speed} km/h`,               c: C.text  },
                          { l: "Humidity",   v: `${s.humidity}%`,                c: C.cyan  },
                          { l: "Compressor", v: s.compressor,                    c: s.compressor === "RUNNING" ? C.green : C.rose },
                          { l: "Driver",     v: s.driver,                        c: C.slate },
                          { l: "ETA",        v: `${s.etaHrs}h`,                  c: C.text  },
                          { l: "Value",      v: formatINR(s.cargoValue),          c: C.green },
                        ].map(({ l, v, c }) => (
                          <div key={l} style={{ background: C.bg, borderRadius: 5, padding: "5px 7px" }}>
                            <div style={{ color: C.dim, fontSize: 8, fontFamily: "monospace" }}>{l}</div>
                            <div style={{ color: c, fontSize: 10, marginTop: 2, fontFamily: "monospace" }}>{v}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
              {filtered.length === 0 && <div style={{ textAlign: "center", color: C.slate, padding: 40 }}>Nothing matches that filter</div>}
            </div>
          </div>

          {/* ── MAP ── */}
          <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
            <MapContainer center={[22, 80]} zoom={5} style={{ width: "100%", height: "100%" }} zoomControl>
              <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
              />
              {ships.map(s => (
                <Marker key={s.id} position={[s.lat, s.lng]} icon={dotIcon(RISK[s.risk])}
                  eventHandlers={{ click: () => setSelId(s.id) }}>
                  <Popup>
                    <div style={{ fontFamily: "monospace", fontSize: 12, minWidth: 150, lineHeight: 1.7 }}>
                      <b>{s.id}</b><br />
                      {CARGO_EMOJI[s.cargo]} {s.cargo}<br />
                      {s.from} → {s.to}<br />
                      <span style={{ color: s.isIdeal ? "green" : "red" }}>{s.temp}°C</span> · {s.risk} risk<br />
                      {s.driver}
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>

            {/* Selected overlay */}
            {sel && (
              <div style={{ position: "absolute", top: 12, right: 12, zIndex: 900, background: "rgba(7,16,28,0.9)", backdropFilter: "blur(6px)", border: `1px solid ${CARGO[sel.cargo]}40`, borderRadius: 10, padding: "12px 15px", minWidth: 165, pointerEvents: "none" }}>
                <div style={{ color: C.slate, fontSize: 9, fontFamily: "monospace", marginBottom: 5 }}>SELECTED</div>
                <div style={{ color: C.text, fontSize: 14, fontWeight: 600, marginBottom: 2 }}>{sel.id}</div>
                <div style={{ color: C.slate, fontSize: 11 }}>{CARGO_EMOJI[sel.cargo]} {sel.cargo}</div>
                <div style={{ color: C.slate, fontSize: 11, margin: "4px 0" }}>{sel.from} → {sel.to}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ color: sel.isIdeal ? C.green : C.rose, fontSize: 16, fontWeight: 700, fontFamily: "monospace" }}>{sel.temp}°C</span>
                  <RiskTag risk={sel.risk} />
                </div>
                <div style={{ color: C.dim, fontSize: 10, marginTop: 5 }}>👤 {sel.driver}</div>
              </div>
            )}

            {/* Legend */}
            <div style={{ position: "absolute", bottom: 12, left: 12, zIndex: 900, background: "rgba(7,16,28,0.85)", backdropFilter: "blur(4px)", border: `1px solid ${C.rim}`, borderRadius: 9, padding: "9px 13px", pointerEvents: "none" }}>
              {["LOW","MEDIUM","HIGH"].map(r => (
                <div key={r} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: RISK[r] }} />
                  <span style={{ color: C.slate, fontSize: 9 }}>{r}</span>
                </div>
              ))}
            </div>

            {/* Mobile: open list button */}
            <button className="cp-list-btn" onClick={() => setListOpen(true)} style={{
              position: "absolute", bottom: 14, right: 14, zIndex: 900,
              background: C.card, border: `1px solid ${C.rim}`, borderRadius: 10,
              color: C.text, fontSize: 12, padding: "10px 16px", cursor: "pointer",
              boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
            }}>
              ☰ Shipments ({ships.length})
            </button>
          </div>

          {/* Mobile bottom drawer for shipment list */}
          <div className={`cp-mobile-list${listOpen ? " cp-list-open" : ""}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", borderBottom: `1px solid ${C.rim}`, flexShrink: 0 }}>
              <span style={{ color: C.text, fontWeight: 600, fontSize: 14 }}>Shipments</span>
              <button onClick={() => setListOpen(false)} style={{ background: "none", border: "none", color: C.slate, fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
            </div>
            <div style={{ padding: "8px 12px", borderBottom: `1px solid ${C.rim}`, flexShrink: 0 }}>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
                style={{ width: "100%", background: C.bg, border: `1px solid ${C.rim}`, borderRadius: 7, padding: "7px 12px", color: C.text, fontSize: 12, fontFamily: "inherit", outline: "none", boxSizing: "border-box" }} />
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {filtered.slice(0, 30).map(s => (
                <div key={s.id} onClick={() => { setSelId(s.id); setListOpen(false); }} style={{
                  padding: "11px 14px", borderBottom: `1px solid ${C.rim}`, cursor: "pointer",
                  borderLeft: `3px solid ${RISK[s.risk]}`,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <span style={{ color: C.blue, fontFamily: "monospace", fontSize: 12, fontWeight: 600 }}>{s.id} · {CARGO_EMOJI[s.cargo]} {s.cargo}</span>
                    <RiskTag risk={s.risk} />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: C.slate, fontSize: 11 }}>{s.from} → {s.to}</span>
                    <span style={{ color: s.isIdeal ? C.green : C.rose, fontFamily: "monospace", fontSize: 11 }}>{s.temp}°C</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <style>{`
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 3px; }
        ::-webkit-scrollbar-thumb { background: ${C.rim}; border-radius: 2px; }
        .leaflet-container { background: #060e1a !important; }
        .leaflet-tile { filter: brightness(0.78) saturate(0.5) hue-rotate(200deg); }
        @keyframes cpPulse {
          0%,100% { opacity:1; box-shadow:0 0 4px currentColor; }
          50%      { opacity:0.4; box-shadow:0 0 10px currentColor; }
        }
        input[type="date"]::-webkit-calendar-picker-indicator { filter: invert(0.6); cursor: pointer; }

        /* Desktop */
        .cp-list-panel  { width: 320px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid ${C.rim}; background: ${C.bg}; }
        .cp-list-btn    { display: none; }
        .cp-mobile-list { display: none; }

        /* Analytics responsive */
        @media (max-width: 1100px) { .cp-grid-4 { grid-template-columns: repeat(2,1fr) !important; } }

        /* Mobile */
        @media (max-width: 768px) {
          .cp-map-body   { flex-direction: column; }
          .cp-list-panel { display: none; }
          .cp-list-btn   { display: block; }

          .cp-mobile-list {
            display: flex; flex-direction: column;
            position: fixed; bottom: 0; left: 0; right: 0;
            height: 70svh; background: ${C.bg};
            border-top: 1px solid ${C.rim}; border-radius: 16px 16px 0 0;
            z-index: 1000; transform: translateY(100%);
            transition: transform 0.3s cubic-bezier(0.32,0.72,0,1);
            overflow: hidden;
          }
          .cp-mobile-list.cp-list-open { transform: translateY(0); }
          .cp-analytics { padding: 12px !important; }
          .cp-grid-2    { grid-template-columns: 1fr !important; }
          .cp-grid-4    { grid-template-columns: 1fr 1fr !important; }
        }
      `}</style>
    </div>
  );
}
