// ── Distance calculation (Haversine formula) ─────────────────
export function distanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ── Indian Rupee formatter ────────────────────────────────────
export function formatINR(n) {
  n = parseFloat(n) || 0;
  if (n >= 1e9) return "₹" + (n / 1e9).toFixed(2) + "B";
  if (n >= 1e7) return "₹" + (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return "₹" + (n / 1e5).toFixed(1) + "L";
  if (n >= 1e3) return "₹" + (n / 1e3).toFixed(1) + "K";
  return "₹" + n.toFixed(0);
}

// ── Risk colour helpers ────────────────────────────────────────
export function riskColor(risk, action) {
  if (action === "DIVERT")
    return {
      bg: "bg-red-100 dark:bg-red-950",
      text: "text-red-700 dark:text-red-400",
      border: "border-red-400",
      hex: "#ef4444",
    };
  if (risk > 0.5)
    return {
      bg: "bg-amber-100 dark:bg-amber-950",
      text: "text-amber-700 dark:text-amber-400",
      border: "border-amber-400",
      hex: "#f59e0b",
    };
  return {
    bg: "bg-emerald-100 dark:bg-emerald-950",
    text: "text-emerald-700 dark:text-emerald-400",
    border: "border-emerald-400",
    hex: "#10b981",
  };
}

export function riskHex(risk, action) {
  return riskColor(risk, action).hex;
}

// ── ETA eta minutes → human string ───────────────────────────
export function etaString(mins) {
  if (mins == null) return "—";
  const m = Math.round(mins);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60),
    r = m % 60;
  return r > 0 ? `${h}h ${r}m` : `${h}h`;
}

// ── Timestamp → HH:MM:SS ──────────────────────────────────────
export function timeStr(ts) {
  if (!ts) return "";
  return ts.split("T")[1]?.substring(0, 8) || "";
}

// ── Cold storage hub locations across India ───────────────────
export const COLD_HUBS = [
  {
    id: "hub_01",
    name: "Gurgaon Cold Hub",
    city: "Gurgaon",
    lat: 28.4595,
    lon: 77.0266,
    phone: "+91-124-456-7890",
    capacity: 82,
    minTemp: -25,
    maxTemp: 8,
    type: "Multi-Temp",
    color: "#0ea5e9",
  },
  {
    id: "hub_02",
    name: "Okhla Cold Storage",
    city: "Delhi",
    lat: 28.5355,
    lon: 77.251,
    phone: "+91-11-2456-7890",
    capacity: 65,
    minTemp: 2,
    maxTemp: 8,
    type: "Pharma",
    color: "#8b5cf6",
  },
  {
    id: "hub_03",
    name: "Azadpur Mandi Hub",
    city: "Delhi",
    lat: 28.7069,
    lon: 77.1763,
    phone: "+91-11-2765-4321",
    capacity: 90,
    minTemp: 0,
    maxTemp: 10,
    type: "General",
    color: "#10b981",
  },
  {
    id: "hub_04",
    name: "Bhiwandi Cold Chain",
    city: "Mumbai",
    lat: 19.2813,
    lon: 73.0633,
    phone: "+91-22-2745-6789",
    capacity: 73,
    minTemp: -20,
    maxTemp: 6,
    type: "Multi-Temp",
    color: "#0ea5e9",
  },
  {
    id: "hub_05",
    name: "Vashi Logistics Hub",
    city: "Navi Mumbai",
    lat: 19.08,
    lon: 73.01,
    phone: "+91-22-2789-0123",
    capacity: 58,
    minTemp: 2,
    maxTemp: 8,
    type: "Pharma",
    color: "#8b5cf6",
  },
  {
    id: "hub_06",
    name: "Pune Hadapsar Hub",
    city: "Pune",
    lat: 18.508,
    lon: 73.94,
    phone: "+91-20-2645-8901",
    capacity: 88,
    minTemp: -15,
    maxTemp: 8,
    type: "Multi-Temp",
    color: "#0ea5e9",
  },
  {
    id: "hub_07",
    name: "Whitefield Cold Store",
    city: "Bangalore",
    lat: 12.9698,
    lon: 77.7499,
    phone: "+91-80-2567-8901",
    capacity: 77,
    minTemp: 2,
    maxTemp: 8,
    type: "Pharma",
    color: "#8b5cf6",
  },
  {
    id: "hub_08",
    name: "Yeshwanthpur Hub",
    city: "Bangalore",
    lat: 13.0252,
    lon: 77.538,
    phone: "+91-80-2890-1234",
    capacity: 91,
    minTemp: -20,
    maxTemp: 6,
    type: "Multi-Temp",
    color: "#0ea5e9",
  },
  {
    id: "hub_09",
    name: "Ambattur Cold Chain",
    city: "Chennai",
    lat: 13.1143,
    lon: 80.1548,
    phone: "+91-44-2645-7890",
    capacity: 69,
    minTemp: 0,
    maxTemp: 8,
    type: "General",
    color: "#10b981",
  },
  {
    id: "hub_10",
    name: "Ennore Port Hub",
    city: "Chennai",
    lat: 13.2164,
    lon: 80.3201,
    phone: "+91-44-2789-5678",
    capacity: 84,
    minTemp: -20,
    maxTemp: 4,
    type: "Seafood",
    color: "#f59e0b",
  },
  {
    id: "hub_11",
    name: "Shamshabad Cold Hub",
    city: "Hyderabad",
    lat: 17.2403,
    lon: 78.4294,
    phone: "+91-40-2678-9012",
    capacity: 76,
    minTemp: 2,
    maxTemp: 8,
    type: "Pharma",
    color: "#8b5cf6",
  },
  {
    id: "hub_12",
    name: "Kolkata Rajpur Hub",
    city: "Kolkata",
    lat: 22.4547,
    lon: 88.3874,
    phone: "+91-33-2545-6789",
    capacity: 62,
    minTemp: -15,
    maxTemp: 8,
    type: "Multi-Temp",
    color: "#0ea5e9",
  },
];
