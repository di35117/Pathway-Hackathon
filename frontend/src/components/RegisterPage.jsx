import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Truck, Building, User, Mail, Lock, Phone, Fingerprint,
  MapPin, ChevronRight, CheckCircle,
} from "lucide-react";

const RegisterPage = () => {
  const [role, setRole]       = useState("driver");
  const [step, setStep]       = useState(1); // 1 = role & identity, 2 = details
  const [done, setDone]       = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  // shared
  const [name,     setName]     = useState("");
  const [email,    setEmail]    = useState("");
  const [phone,    setPhone]    = useState("");
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm]  = useState("");

  // driver specific
  const [vehicleId, setVehicleId] = useState("");
  const [licenseNo, setLicenseNo] = useState("");

  // company specific
  const [companyName, setCompanyName] = useState("");
  const [gstNo,       setGstNo]       = useState("");
  const [city,        setCity]        = useState("");

  const navigate = useNavigate();

  const handleNext = (e) => {
    e.preventDefault();
    setError("");
    if (!name.trim() || !email.trim() || !phone.trim()) {
      setError("Please fill all required fields."); return;
    }
    setStep(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) { setError("Passwords do not match."); return; }
    if (password.length < 6)  { setError("Password must be at least 6 characters."); return; }

    setLoading(true);
    // ── FRONTEND TESTING MODE ─────────────────────────────────────────────
    // TODO: replace with real POST /api/auth/register call
    await new Promise((r) => setTimeout(r, 800));
    setLoading(false);
    setDone(true);
    // ─────────────────────────────────────────────────────────────────────
  };

  const Field = ({ label, icon: Icon, ...props }) => (
    <div>
      <label className="block text-xs uppercase tracking-wider text-[#7a90a8] font-mono mb-1.5">{label}</label>
      <div className="relative">
        {Icon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#3d5470]">
            <Icon size={14} />
          </div>
        )}
        <input
          {...props}
          className={`w-full bg-[#070b14] border border-[#1c2d45] text-[#dde6f0] rounded-md py-2.5 text-sm focus:outline-none focus:border-[#22d3ee] transition-colors ${Icon ? "pl-9 pr-3" : "px-3"}`}
        />
      </div>
    </div>
  );

  return (
    <div className="dark">
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#070b14] text-[#dde6f0] p-4">
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#38bdf8] opacity-5 blur-[120px] rounded-full" />
        </div>

        <div className="w-full max-w-md bg-[#0c1220] border border-[#1c2d45] rounded-xl shadow-2xl relative z-10 overflow-hidden">
          {/* Header */}
          <div className="flex flex-col items-center p-7 pb-5 border-b border-[#1c2d45] bg-[#111827]">
            <div className="font-mono text-xl font-bold text-[#38bdf8] tracking-tight mb-1 flex items-center gap-2">
              ❄ Live<span className="text-[#22d3ee]">Cold</span>
            </div>
            <p className="text-[#7a90a8] text-xs uppercase tracking-widest font-mono">
              {done ? "Registration Complete" : `New Account · Step ${step} of 2`}
            </p>
          </div>

          <div className="p-6">
            {done ? (
              /* ── Success state ── */
              <div className="text-center py-6 flex flex-col items-center gap-4">
                <CheckCircle size={48} className="text-[#22d3ee]" />
                <div>
                  <p className="text-[#dde6f0] font-mono font-bold text-lg">Account Created!</p>
                  <p className="text-[#7a90a8] text-xs mt-1">
                    Your {role === "driver" ? "driver" : "company"} account is pending activation.
                  </p>
                </div>
                <button
                  onClick={() => navigate("/")}
                  className="mt-2 bg-[#111827] border border-[#1c2d45] hover:border-[#22d3ee] text-[#22d3ee] font-mono font-bold py-2.5 px-8 rounded-md transition-all text-sm"
                >
                  GO TO LOGIN
                </button>
              </div>
            ) : (
              <>
                {/* Role selector (only step 1) */}
                {step === 1 && (
                  <div className="flex p-1 bg-[#070b14] border border-[#1c2d45] rounded-lg mb-5">
                    {[
                      { id: "driver", label: "Driver",  icon: Truck    },
                      { id: "client", label: "Company", icon: Building },
                    ].map(({ id, label, icon: Icon }) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => setRole(id)}
                        className={`flex-1 flex flex-col items-center justify-center gap-1 py-2.5 text-xs font-semibold rounded-md transition-all ${
                          role === id
                            ? "bg-[#1c2d45] text-[#22d3ee]"
                            : "text-[#3d5470] hover:text-[#7a90a8] hover:bg-[#111827]"
                        }`}
                      >
                        <Icon size={15} /> {label}
                      </button>
                    ))}
                  </div>
                )}

                {error && (
                  <div className="mb-4 p-3 rounded-lg bg-red-950/50 border border-red-500/50 text-red-400 text-xs text-center font-mono">
                    {error}
                  </div>
                )}

                {/* Step 1 – Identity */}
                {step === 1 && (
                  <form onSubmit={handleNext} className="space-y-4">
                    <Field label="Full Name"    icon={User}  type="text"  value={name}  onChange={e => setName(e.target.value)}  placeholder="Rajesh Kumar" required />
                    <Field label="Email"        icon={Mail}  type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" required />
                    <Field label="Phone Number" icon={Phone} type="tel"   value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91 98XXX XXXXX" required />

                    {role === "driver" ? (
                      <Field label="Vehicle / Registration No." icon={Truck} type="text" value={vehicleId} onChange={e => setVehicleId(e.target.value)} placeholder="HR 26DQ5551" required />
                    ) : (
                      <Field label="Company Name" icon={Building} type="text" value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="AgroFreeze Pvt Ltd" required />
                    )}

                    <button
                      type="submit"
                      className="w-full mt-2 bg-[#111827] border border-[#1c2d45] hover:border-[#22d3ee] text-[#22d3ee] font-mono font-bold py-3 rounded-md transition-all flex justify-center items-center gap-2 text-sm"
                    >
                      NEXT <ChevronRight size={14} />
                    </button>
                  </form>
                )}

                {/* Step 2 – Credentials & extras */}
                {step === 2 && (
                  <form onSubmit={handleSubmit} className="space-y-4">
                    {role === "driver" ? (
                      <Field label="Driving Licence No." icon={Fingerprint} type="text" value={licenseNo} onChange={e => setLicenseNo(e.target.value)} placeholder="DL-1234567890123" />
                    ) : (
                      <>
                        <Field label="GST Number (optional)" icon={Building} type="text" value={gstNo} onChange={e => setGstNo(e.target.value)} placeholder="22AAAAA0000A1Z5" />
                        <Field label="City / HQ Location" icon={MapPin} type="text" value={city} onChange={e => setCity(e.target.value)} placeholder="Delhi" />
                      </>
                    )}

                    <Field label="Password"        icon={Lock} type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Min. 6 characters" required />
                    <Field label="Confirm Password" icon={Lock} type="password" value={confirm}  onChange={e => setConfirm(e.target.value)}  placeholder="Repeat password" required />

                    <div className="flex gap-3 mt-2">
                      <button
                        type="button"
                        onClick={() => setStep(1)}
                        className="flex-1 bg-[#0c1220] border border-[#1c2d45] text-[#7a90a8] font-mono font-bold py-3 rounded-md transition-all text-sm hover:border-[#3d5470]"
                      >
                        ← BACK
                      </button>
                      <button
                        type="submit"
                        disabled={loading}
                        className="flex-2 flex-grow-[2] bg-[#111827] border border-[#1c2d45] hover:border-[#22d3ee] text-[#22d3ee] font-mono font-bold py-3 rounded-md transition-all disabled:opacity-50 text-sm"
                      >
                        {loading ? "CREATING..." : "CREATE ACCOUNT"}
                      </button>
                    </div>
                  </form>
                )}

                <div className="mt-5 pt-4 border-t border-[#1c2d45] text-center">
                  <span className="text-[#3d5470] text-xs font-mono">Already registered? </span>
                  <Link to="/" className="text-[#22d3ee] text-xs font-mono hover:underline">
                    Sign in →
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
