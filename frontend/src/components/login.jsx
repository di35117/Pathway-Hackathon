import React, { useState } from "react";

import {
  Truck,
  Building,
  Shield,
  Mail,
  Lock,
  Key,
  Fingerprint,
} from "lucide-react";

const LiveColdLogin = () => {
  const [role, setRole] = useState("driver"); // 'driver', 'client', 'admin'

  const roles = [
    { id: "driver", label: "Driver Access", icon: Truck },

    { id: "client", label: "Client Portal", icon: Building },

    { id: "admin", label: "LiveCold Admin", icon: Shield },
  ];

  const handleSubmit = (e) => {
    e.preventDefault();

    // Handle authentication logic here

    console.log(`Authenticating as ${role}`);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[#070b14] text-[#dde6f0] font-sans selection:bg-[#22d3ee] selection:text-[#070b14] p-4">
      {/* Background Decor */}

      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#38bdf8] opacity-5 blur-[120px] rounded-full"></div>
      </div>

      <div className="w-full max-w-md bg-[#0c1220] border border-[#1c2d45] rounded-xl shadow-2xl relative z-10 overflow-hidden">
        {/* Header */}

        <div className="flex flex-col items-center p-8 border-b border-[#1c2d45] bg-[#111827]">
          <div className="font-mono text-2xl font-bold text-[#38bdf8] tracking-tight mb-2 flex items-center gap-2">
            ❄ Live<span className="text-[#22d3ee]">Cold</span>
          </div>

          <p className="text-[#7a90a8] text-sm uppercase tracking-widest font-mono">
            Access Control Interface
          </p>
        </div>

        <div className="p-6">
          {/* Role Selector Tabs */}

          <div className="flex p-1 bg-[#070b14] border border-[#1c2d45] rounded-lg mb-8">
            {roles.map((r) => {
              const Icon = r.icon;

              const isActive = role === r.id;

              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => setRole(r.id)}
                  className={`flex-1 flex flex-col items-center justify-center gap-1 py-3 text-xs font-semibold rounded-md transition-all duration-200 ${
                    isActive
                      ? "bg-[#1c2d45] text-[#22d3ee] shadow-sm"
                      : "text-[#3d5470] hover:text-[#7a90a8] hover:bg-[#111827]"
                  }`}
                >
                  <Icon size={16} />

                  {r.label}
                </button>
              );
            })}
          </div>

          {/* Login Form */}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs uppercase tracking-wider text-[#7a90a8] font-mono mb-2">
                {role === "driver"
                  ? "Registration Mark / Email"
                  : role === "admin"
                    ? "Admin Credential"
                    : "Company Email"}
              </label>

              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#3d5470]">
                  {role === "driver" ? (
                    <Fingerprint size={16} />
                  ) : (
                    <Mail size={16} />
                  )}
                </div>

                <input
                  type={role === "driver" ? "text" : "email"}
                  className="w-full bg-[#070b14] border border-[#1c2d45] text-[#dde6f0] rounded-md py-2.5 pl-10 pr-3 text-sm focus:outline-none focus:border-[#22d3ee] focus:ring-1 focus:ring-[#22d3ee] transition-colors placeholder-[#3d5470]"
                  placeholder={
                    role === "driver"
                      ? "e.g. HR 26DQ5551"
                      : role === "admin"
                        ? "admin@livecold.ai"
                        : "logistics@company.com"
                  }
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs uppercase tracking-wider text-[#7a90a8] font-mono mb-2">
                {role === "driver" ? "Access Pin" : "Password"}
              </label>

              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#3d5470]">
                  {role === "driver" ? <Key size={16} /> : <Lock size={16} />}
                </div>

                <input
                  type="password"
                  className="w-full bg-[#070b14] border border-[#1c2d45] text-[#dde6f0] rounded-md py-2.5 pl-10 pr-3 text-sm focus:outline-none focus:border-[#22d3ee] focus:ring-1 focus:ring-[#22d3ee] transition-colors placeholder-[#3d5470]"
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            {role !== "driver" && (
              <div className="flex items-center justify-between mt-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    className="rounded bg-[#070b14] border-[#1c2d45] text-[#22d3ee] focus:ring-[#22d3ee] focus:ring-offset-[#0c1220]"
                  />

                  <span className="text-xs text-[#7a90a8]">
                    Remember device
                  </span>
                </label>

                <a
                  href="#"
                  className="text-xs text-[#22d3ee] hover:text-[#38bdf8] transition-colors"
                >
                  Forgot password?
                </a>
              </div>
            )}

            <button
              type="submit"
              className="w-full mt-6 bg-[#111827] hover:bg-[#1c2d45] border border-[#1c2d45] hover:border-[#22d3ee] text-[#22d3ee] font-mono font-bold py-3 px-4 rounded-md transition-all duration-200 flex items-center justify-center gap-2"
            >
              {role === "driver" ? "START SHIFT" : "AUTHENTICATE"}
            </button>
          </form>
        </div>

        {/* Status Footer */}

        <div className="bg-[#070b14] border-t border-[#1c2d45] p-3 flex items-center justify-between text-xs font-mono text-[#3d5470]">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-[#34d399] shadow-[0_0_4px_#34d399] animate-pulse"></div>
            System Online
          </div>

          <div>v1.0.4-live</div>
        </div>
      </div>
    </div>
  );
};

export default LiveColdLogin;
