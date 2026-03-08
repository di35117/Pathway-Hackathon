/**
 * RegisterPage.jsx
 *
 * BUG FIX: Field is defined at MODULE level — never inside RegisterPage.
 * Defining a component inside its parent causes React to unmount/remount
 * the <input> on every keystroke, losing focus after each character.
 */

import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Truck,
  Building,
  User,
  Mail,
  Lock,
  Phone,
  Fingerprint,
  MapPin,
  ChevronRight,
  Eye,
  EyeOff,
} from "lucide-react";

const C = {
  bg: "#07101c",
  card: "#0e1d2e",
  rim: "#162840",
  cyan: "#2dd4bf",
  text: "#e2e8f0",
  slate: "#94a3b8",
  dim: "#334155",
  green: "#4ade80",
  rose: "#f87171",
};

// ─── Field — module level, never moves ────────────────────────────────────────
function Field({
  label,
  icon: Icon,
  err,
  hint,
  showToggle,
  showPw,
  onToggle,
  ...rest
}) {
  const [focused, setFocused] = React.useState(false);
  const borderCol = err ? C.rose : focused ? C.cyan : C.rim;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label
        style={{
          color: C.slate,
          fontSize: 11,
          fontFamily: "monospace",
          letterSpacing: 0.5,
        }}
      >
        {label}
      </label>
      <div style={{ position: "relative" }}>
        {Icon && (
          <span
            style={{
              position: "absolute",
              left: 11,
              top: "50%",
              transform: "translateY(-50%)",
              color: C.dim,
              display: "flex",
              pointerEvents: "none",
            }}
          >
            <Icon size={14} />
          </span>
        )}
        <input
          {...rest}
          onFocus={(e) => {
            setFocused(true);
            rest.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            rest.onBlur?.(e);
          }}
          style={{
            width: "100%",
            background: "#060e1a",
            border: `1px solid ${borderCol}`,
            borderRadius: 8,
            color: C.text,
            fontSize: 13,
            padding: `10px ${showToggle ? "36px" : "12px"} 10px ${Icon ? "34px" : "12px"}`,
            outline: "none",
            fontFamily: "inherit",
            boxSizing: "border-box",
            transition: "border-color 0.2s",
          }}
        />
        {showToggle && (
          <button
            type="button"
            onClick={onToggle}
            style={{
              position: "absolute",
              right: 10,
              top: "50%",
              transform: "translateY(-50%)",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: C.dim,
              display: "flex",
              padding: 0,
            }}
          >
            {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
      {err && (
        <span style={{ color: C.rose, fontSize: 11, fontFamily: "monospace" }}>
          {err}
        </span>
      )}
      {hint && !err && (
        <span style={{ color: C.dim, fontSize: 10 }}>{hint}</span>
      )}
    </div>
  );
}

// ─── Password strength ─────────────────────────────────────────────────────────
function StrengthBar({ pw }) {
  if (!pw) return null;
  const checks = [
    { ok: pw.length >= 8, label: "8+ chars" },
    { ok: /[A-Z]/.test(pw), label: "uppercase" },
    { ok: /\d/.test(pw), label: "number" },
    { ok: /[^A-Za-z0-9]/.test(pw), label: "symbol" },
  ];
  const score = checks.filter((c) => c.ok).length;
  const col = [C.rose, C.rose, "#f97316", "#facc15", C.green][score];
  const word = ["", "Weak", "Fair", "Good", "Strong"][score];
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: 3,
              borderRadius: 99,
              background: i < score ? col : C.rim,
              transition: "background 0.3s",
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", gap: 10 }}>
          {checks.map((c) => (
            <span
              key={c.label}
              style={{
                fontSize: 9,
                fontFamily: "monospace",
                color: c.ok ? C.green : C.dim,
              }}
            >
              {c.ok ? "✓" : "○"} {c.label}
            </span>
          ))}
        </div>
        {word && (
          <span
            style={{
              fontSize: 10,
              color: col,
              fontFamily: "monospace",
              fontWeight: 700,
            }}
          >
            {word}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Step dots ─────────────────────────────────────────────────────────────────
function StepDots({ step }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        marginBottom: 22,
      }}
    >
      {[1, 2].map((n, i) => (
        <React.Fragment key={n}>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 4,
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: step >= n ? C.cyan : C.rim,
                color: step >= n ? "#07101c" : C.dim,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 700,
                fontFamily: "monospace",
                transition: "all 0.25s",
              }}
            >
              {n}
            </div>
            <div
              style={{
                color: step >= n ? C.cyan : C.dim,
                fontSize: 8,
                fontFamily: "monospace",
              }}
            >
              {n === 1 ? "Identity" : "Credentials"}
            </div>
          </div>
          {i < 1 && (
            <div
              style={{
                flex: 1,
                height: 2,
                background: step > 1 ? C.cyan : C.rim,
                marginBottom: 14,
                transition: "background 0.3s",
                marginLeft: 4,
                marginRight: 4,
              }}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ─── Main ──────────────────────────────────────────────────────────────────────
export default function RegisterPage() {
  const navigate = useNavigate();
  const [role, setRole] = useState("driver");
  const [step, setStep] = useState(1);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [showCf, setShowCf] = useState(false);
  const [errors, setErrors] = useState({});

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [licenseNo, setLicenseNo] = useState("");
  const [gstNo, setGstNo] = useState("");
  const [city, setCity] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  const isPhone = (v) => /^\+?[\d\s()\-]{10,}$/.test(v);
  const isVehicle = (v) =>
    /^[A-Z]{2}\s?\d{2}\s?[A-Z]{1,3}\s?\d{4}$/i.test(v.trim());

  const v1 = () => {
    const e = {};
    if (!name.trim()) e.name = "Name is required";
    if (!isEmail(email)) e.email = "Enter a valid email";
    if (!isPhone(phone)) e.phone = "Enter a valid phone number";
    if (role === "driver") {
      if (!vehicleId.trim()) e.vehicleId = "Vehicle number is required";
      else if (!isVehicle(vehicleId)) e.vehicleId = "Format: HR 26 DQ 5551";
    } else {
      if (!companyName.trim()) e.companyName = "Company name is required";
    }
    setErrors(e);
    return !Object.keys(e).length;
  };

  const v2 = () => {
    const e = {};
    if (password.length < 8) e.password = "At least 8 characters";
    else if (!/[A-Z]/.test(password)) e.password = "Add an uppercase letter";
    else if (!/\d/.test(password)) e.password = "Add a number";
    else if (!/[!@#$%^&*]/.test(password))
      e.password = "Add a special character (!@#$%^&*)";
    if (!e.password && password !== confirm)
      e.confirm = "Passwords don't match";
    setErrors(e);
    return !Object.keys(e).length;
  };

  const next = (e) => {
    e.preventDefault();
    if (v1()) {
      setErrors({});
      setStep(2);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!v2()) return;
    setLoading(true);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role,
          name,
          email,
          phone,
          password,
          ...(role === "driver"
            ? { vehicleId, licenseNo }
            : { companyName, gstNo, city }),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setDone(true);
      } else {
        setErrors({ form: data.message || "Registration failed." });
      }
    } catch (err) {
      setErrors({ form: "Could not reach server." });
    } finally {
      setLoading(false);
    }
  };

  const btnStyle = {
    width: "100%",
    padding: "12px",
    borderRadius: 9,
    cursor: "pointer",
    background: "#0c1825",
    border: `1px solid ${C.rim}`,
    color: C.cyan,
    fontFamily: "monospace",
    fontWeight: 700,
    fontSize: 13,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    transition: "border-color 0.2s",
  };

  return (
    <div
      style={{
        minHeight: "100svh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: C.bg,
        padding: 16,
        fontFamily: "'Outfit', sans-serif",
        position: "relative",
      }}
    >
      {/* Ambient glow */}
      <div
        style={{
          position: "fixed",
          top: "-20%",
          left: "50%",
          transform: "translateX(-50%)",
          width: "80vw",
          height: "50vh",
          background: "#0ea5e9",
          opacity: 0.04,
          filter: "blur(120px)",
          borderRadius: "50%",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      <div
        style={{
          width: "100%",
          maxWidth: 430,
          background: C.card,
          border: `1px solid ${C.rim}`,
          borderRadius: 16,
          overflow: "hidden",
          boxShadow: "0 32px 80px rgba(0,0,0,0.5)",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "22px 28px 18px",
            borderBottom: `1px solid ${C.rim}`,
            background: "#0a1525",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: 20,
              fontWeight: 700,
              color: C.cyan,
              marginBottom: 3,
            }}
          >
            ❄ LiveCold
          </div>
          <div
            style={{
              color: C.dim,
              fontSize: 10,
              fontFamily: "monospace",
              letterSpacing: 3,
            }}
          >
            {done ? "YOU'RE IN" : `CREATE ACCOUNT`}
          </div>
        </div>

        <div style={{ padding: "24px 28px" }}>
          {done ? (
            <div style={{ textAlign: "center", padding: "8px 0 4px" }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
              <div
                style={{
                  color: C.text,
                  fontSize: 18,
                  fontWeight: 700,
                  marginBottom: 8,
                }}
              >
                Account created
              </div>
              <div
                style={{
                  color: C.slate,
                  fontSize: 13,
                  lineHeight: 1.7,
                  marginBottom: 24,
                }}
              >
                Your {role === "driver" ? "driver" : "company"} account is
                pending review.
                <br />
                You'll get access once the admin approves it.
              </div>
              <button
                onClick={() => navigate("/")}
                style={{ ...btnStyle, width: "auto", padding: "11px 28px" }}
              >
                Back to login →
              </button>
            </div>
          ) : (
            <>
              <StepDots step={step} />

              {/* Role picker — step 1 only */}
              {step === 1 && (
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    marginBottom: 20,
                    background: "#060e1a",
                    border: `1px solid ${C.rim}`,
                    borderRadius: 10,
                    padding: 4,
                  }}
                >
                  {[
                    { id: "driver", icon: Truck, label: "Driver" },
                    { id: "client", icon: Building, label: "Company" },
                  ].map(({ id, icon: Icon, label }) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => {
                        setRole(id);
                        setErrors({});
                      }}
                      style={{
                        flex: 1,
                        padding: "10px 0",
                        borderRadius: 7,
                        cursor: "pointer",
                        background: role === id ? C.rim : "transparent",
                        border: `1px solid ${role === id ? C.cyan + "40" : "transparent"}`,
                        color: role === id ? C.cyan : C.dim,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: 5,
                        fontSize: 11,
                        fontFamily: "monospace",
                        transition: "all 0.15s",
                      }}
                    >
                      <Icon size={16} />
                      {label}
                    </button>
                  ))}
                </div>
              )}

              {errors.form && (
                <div
                  style={{
                    background: "#280a0a",
                    border: `1px solid ${C.rose}40`,
                    borderRadius: 8,
                    padding: "10px 14px",
                    color: C.rose,
                    fontSize: 12,
                    fontFamily: "monospace",
                    marginBottom: 16,
                  }}
                >
                  {errors.form}
                </div>
              )}

              {step === 1 && (
                <form
                  onSubmit={next}
                  noValidate
                  style={{ display: "flex", flexDirection: "column", gap: 14 }}
                >
                  <Field
                    label="Full name"
                    icon={User}
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Rajesh Kumar"
                    err={errors.name}
                    autoComplete="name"
                  />
                  <Field
                    label="Email"
                    icon={Mail}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    err={errors.email}
                    autoComplete="email"
                  />
                  <Field
                    label="Phone"
                    icon={Phone}
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    err={errors.phone}
                  />
                  {role === "driver" ? (
                    <Field
                      label="Vehicle registration"
                      icon={Truck}
                      type="text"
                      value={vehicleId}
                      onChange={(e) =>
                        setVehicleId(e.target.value.toUpperCase())
                      }
                      placeholder="HR 26 DQ 5551"
                      err={errors.vehicleId}
                      hint="Format: MH 12 AB 1234"
                    />
                  ) : (
                    <Field
                      label="Company name"
                      icon={Building}
                      type="text"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                      placeholder="AgroFreeze Pvt Ltd"
                      err={errors.companyName}
                    />
                  )}
                  <button
                    type="submit"
                    style={btnStyle}
                    onMouseOver={(e) =>
                      (e.currentTarget.style.borderColor = C.cyan)
                    }
                    onMouseOut={(e) =>
                      (e.currentTarget.style.borderColor = C.rim)
                    }
                  >
                    Continue <ChevronRight size={14} />
                  </button>
                </form>
              )}

              {step === 2 && (
                <form
                  onSubmit={submit}
                  noValidate
                  style={{ display: "flex", flexDirection: "column", gap: 14 }}
                >
                  {role === "driver" ? (
                    <Field
                      label="Licence number (optional)"
                      icon={Fingerprint}
                      type="text"
                      value={licenseNo}
                      onChange={(e) => setLicenseNo(e.target.value)}
                      placeholder="DL-1234567890123"
                    />
                  ) : (
                    <>
                      <Field
                        label="GST number (optional)"
                        icon={Building}
                        type="text"
                        value={gstNo}
                        onChange={(e) => setGstNo(e.target.value)}
                        placeholder="22AAAAA0000A1Z5"
                      />
                      <Field
                        label="City"
                        icon={MapPin}
                        type="text"
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        placeholder="Delhi"
                      />
                    </>
                  )}
                  <div>
                    <Field
                      label="Password"
                      icon={Lock}
                      type={showPw ? "text" : "password"}
                      showToggle
                      showPw={showPw}
                      onToggle={() => setShowPw((p) => !p)}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min. 8 characters"
                      err={errors.password}
                      autoComplete="new-password"
                    />
                    <StrengthBar pw={password} />
                  </div>
                  <Field
                    label="Confirm password"
                    icon={Lock}
                    type={showCf ? "text" : "password"}
                    showToggle
                    showPw={showCf}
                    onToggle={() => setShowCf((p) => !p)}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="Repeat password"
                    err={errors.confirm}
                    autoComplete="new-password"
                  />

                  <div style={{ display: "flex", gap: 10 }}>
                    <button
                      type="button"
                      onClick={() => {
                        setStep(1);
                        setErrors({});
                      }}
                      style={{
                        ...btnStyle,
                        flex: 1,
                        color: C.slate,
                        border: `1px solid ${C.rim}`,
                      }}
                    >
                      ← Back
                    </button>
                    <button
                      type="submit"
                      disabled={loading}
                      style={{
                        ...btnStyle,
                        flex: 2,
                        opacity: loading ? 0.6 : 1,
                        cursor: loading ? "not-allowed" : "pointer",
                      }}
                      onMouseOver={(e) => {
                        if (!loading)
                          e.currentTarget.style.borderColor = C.cyan;
                      }}
                      onMouseOut={(e) =>
                        (e.currentTarget.style.borderColor = C.rim)
                      }
                    >
                      {loading ? "Creating…" : "Create account"}
                    </button>
                  </div>
                </form>
              )}

              <div
                style={{
                  marginTop: 20,
                  paddingTop: 16,
                  borderTop: `1px solid ${C.rim}`,
                  textAlign: "center",
                }}
              >
                <span style={{ color: C.dim, fontSize: 12 }}>
                  Already have an account?{" "}
                </span>
                <Link
                  to="/"
                  style={{
                    color: C.cyan,
                    fontSize: 12,
                    textDecoration: "none",
                  }}
                >
                  Sign in →
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
