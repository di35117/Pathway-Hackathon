import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LiveColdLogin from "./components/login";
import RegisterPage from "./components/RegisterPage";
import CompanyPage from "./components/CompanyPage";
import DriverPage from "./components/DriverPage";
import AdminPage from "./pages/AdminPage";

// Simple role guard — reads role stored at login
function RequireRole({ role, children }) {
  const stored = sessionStorage.getItem("livecold_role");
  const token = sessionStorage.getItem("livecold_token");
  if (!token || stored !== role) return <Navigate to="/" replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LiveColdLogin />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/company"
          element={
            <RequireRole role="client">
              <CompanyPage />
            </RequireRole>
          }
        />
        <Route
          path="/driver"
          element={
            <RequireRole role="driver">
              <DriverPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireRole role="admin">
              <AdminPage />
            </RequireRole>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
