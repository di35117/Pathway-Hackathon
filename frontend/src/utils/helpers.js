// ── Indian Rupee formatter (lakh/crore aware) ─────────────────
// 1L = 1e5, 1Cr = 1e7 — the units Indian logistics operators read in.
export function formatINR(n) {
  n = parseFloat(n) || 0;
  if (n >= 1e9) return "₹" + (n / 1e9).toFixed(2) + "B";
  if (n >= 1e7) return "₹" + (n / 1e7).toFixed(1) + "Cr";
  if (n >= 1e5) return "₹" + (n / 1e5).toFixed(1) + "L";
  if (n >= 1e3) return "₹" + (n / 1e3).toFixed(1) + "K";
  return "₹" + n.toFixed(0);
}
