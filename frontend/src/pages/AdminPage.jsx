import React from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Building2 } from "lucide-react";

export default function AdminPage() {
  const navigate = useNavigate();

  const handleLogout = () => {
    sessionStorage.clear();
    navigate("/");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#07101c", color: "#e2e8f0", fontFamily: "sans-serif" }}>
      {/* Header */}
      <div style={{ background: "#0e1d2e", borderBottom: "1px solid #162840", padding: "20px" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: "24px", fontWeight: "bold", color: "#2dd4bf" }}>
            ❄ LiveCold Admin
          </div>
          <button
            onClick={handleLogout}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "#162840",
              border: "1px solid #2dd4bf",
              color: "#2dd4bf",
              padding: "10px 16px",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "600",
            }}
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "40px 20px" }}>
        <div
          style={{
            background: "#0c1220",
            border: "1px solid #162840",
            borderRadius: "12px",
            padding: "60px 40px",
            textAlign: "center",
          }}
        >
          <div style={{ display: "flex", justifyContent: "center", marginBottom: "24px" }}>
            <Building2 size={64} style={{ color: "#2dd4bf", opacity: 0.8 }} />
          </div>
          <h1 style={{ fontSize: "28px", fontWeight: "700", marginBottom: "12px", color: "#2dd4bf" }}>
            Admin Dashboard
          </h1>
          <p style={{ fontSize: "16px", color: "#94a3b8", lineHeight: "1.6", maxWidth: "600px", margin: "0 auto" }}>
            This page is under construction. Your friend will implement company and Pathway data visualization here.
          </p>
          <p style={{ fontSize: "14px", color: "#64748b", marginTop: "20px" }}>
            📊 Coming soon: Company metrics · Pathway data · Real-time monitoring
          </p>
        </div>
      </div>
    </div>
  );
}
