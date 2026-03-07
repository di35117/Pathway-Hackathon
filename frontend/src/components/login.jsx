import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Truck, Building, Shield, Mail, Lock, Key, Fingerprint } from "lucide-react";

const LiveColdLogin = () => {
  const [role, setRole]             = useState("driver");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword]     = useState("");
  const [error, setError]           = useState("");
  const [isLoading, setIsLoading]   = useState(false);
  const navigate = useNavigate();

  const roles = [
    { id: "driver", label: "Driver",  icon: Truck    },
    { id: "client", label: "Company", icon: Building },
    { id: "admin",  label: "Admin",   icon: Shield   },
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    // ── FRONTEND TESTING MODE ──────────────────────────────────────────────
    // Pass-through: any non-empty credentials are accepted.
    // TODO: replace the block below with a real /api/auth/login call when
    //       the backend is ready.
    // ──────────────────────────────────────────────────────────────────────
    await new Promise((r) => setTimeout(r, 600)); // simulate network latency

    if (!identifier.trim() || !password.trim()) {
      setError("Please fill in all fields.");
      setIsLoading(false);
      return;
    }

    // Store a fake token + role so RequireRole guard works
    sessionStorage.setItem("livecold_token", "test-token-" + Date.now());
    sessionStorage.setItem("livecold_role",  role);
    sessionStorage.setItem("livecold_id",    identifier);

    if (role === "driver") navigate("/driver");
    else if (role === "client") navigate("/company");
    else { setError("Admin portal coming soon!"); setIsLoading(false); return; }

    setIsLoading(false);

    /* ── PRODUCTION: uncomment and remove the block above ─────────────────
    try {
      const res  = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, identifier, password }),
      });
      const data = await res.json();
      if (res.ok) {
        if (data.token) {
          sessionStorage.setItem("livecold_token", data.token);
          sessionStorage.setItem("livecold_role",  role);
        }
        if (role === "driver") navigate("/driver");
        else if (role === "client") navigate("/company");
        else alert("Admin portal coming soon!");
      } else {
        setError(data.message || "Invalid credentials. Please try again.");
      }
    } catch {
      setError("Cannot connect to server. Please try again later.");
    } finally {
      setIsLoading(false);
    }
    ─────────────────────────────────────────────────────────────────────── */
  };

  return (
    <div className="dark">
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#070b14] text-[#dde6f0] font-sans p-4">
        {/* Background glow */}
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#38bdf8] opacity-5 blur-[120px] rounded-full" />
          <div className="absolute bottom-0 right-1/4 w-[400px] h-[300px] bg-[#00ff88] opacity-3 blur-[100px] rounded-full" />
        </div>

        <div className="w-full max-w-md bg-[#0c1220] border border-[#1c2d45] rounded-xl shadow-2xl relative z-10 overflow-hidden">
          {/* Header */}
          <div className="flex flex-col items-center p-8 pb-6 border-b border-[#1c2d45] bg-[#111827]">
            <div className="font-mono text-2xl font-bold text-[#38bdf8] tracking-tight mb-1 flex items-center gap-2">
              ❄ Live<span className="text-[#22d3ee]">Cold</span>
            </div>
            <p className="text-[#7a90a8] text-xs uppercase tracking-widest font-mono">
              Access Control
            </p>
          </div>

          <div className="p-6">
            {/* Role tabs */}
            <div className="flex p-1 bg-[#070b14] border border-[#1c2d45] rounded-lg mb-5">
              {roles.map((r) => {
                const Icon = r.icon;
                const isActive = role === r.id;
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => { setRole(r.id); setError(""); }}
                    className={`flex-1 flex flex-col items-center justify-center gap-1 py-2.5 text-xs font-semibold rounded-md transition-all ${
                      isActive
                        ? "bg-[#1c2d45] text-[#22d3ee] shadow-sm"
                        : "text-[#3d5470] hover:text-[#7a90a8] hover:bg-[#111827]"
                    }`}
                  >
                    <Icon size={15} />
                    {r.label}
                  </button>
                );
              })}
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-red-950/50 border border-red-500/50 text-red-400 text-xs text-center font-mono">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs uppercase tracking-wider text-[#7a90a8] font-mono mb-1.5">
                  {role === "driver" ? "Driver ID / Vehicle Mark" : "Email"}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#3d5470]">
                    {role === "driver" ? <Fingerprint size={15} /> : <Mail size={15} />}
                  </div>
                  <input
                    type={role === "driver" ? "text" : "email"}
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    className="w-full bg-[#070b14] border border-[#1c2d45] text-[#dde6f0] rounded-md py-2.5 pl-9 pr-3 text-sm focus:outline-none focus:border-[#22d3ee] transition-colors"
                    placeholder={role === "driver" ? "HR 26DQ5551" : "logistics@company.com"}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wider text-[#7a90a8] font-mono mb-1.5">
                  {role === "driver" ? "Access PIN" : "Password"}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#3d5470]">
                    {role === "driver" ? <Key size={15} /> : <Lock size={15} />}
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full bg-[#070b14] border border-[#1c2d45] text-[#dde6f0] rounded-md py-2.5 pl-9 pr-3 text-sm focus:outline-none focus:border-[#22d3ee] transition-colors"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full mt-2 bg-[#111827] border border-[#1c2d45] hover:border-[#22d3ee] text-[#22d3ee] font-mono font-bold py-3 rounded-md transition-all disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2 text-sm"
              >
                {isLoading
                  ? "VERIFYING..."
                  : role === "driver"
                    ? "START SHIFT"
                    : "AUTHENTICATE"}
              </button>
            </form>

            <div className="mt-5 pt-4 border-t border-[#1c2d45] text-center">
              <span className="text-[#3d5470] text-xs font-mono">New here? </span>
              <Link
                to="/register"
                className="text-[#22d3ee] text-xs font-mono hover:underline"
              >
                Create an account →
              </Link>
            </div>
          </div>
        </div>

        <p className="mt-6 text-[#1c2d45] text-xs font-mono">
          LiveCold Cold-Chain Intelligence Platform
        </p>
      </div>
    </div>
  );
};

export default LiveColdLogin;
