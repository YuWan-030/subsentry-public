import { useEffect, useState, useCallback } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { App as AntdApp, Spin } from "antd";
import api from "./api/http";
import { AuthContext, type CurrentUser } from "./api/auth";
import ShellLayout from "./layouts/ShellLayout";
import LoginPage from "./pages/LoginPage";
import InstallPage from "./pages/InstallPage";
import DashboardPage from "./pages/DashboardPage";
import CustomersPage from "./pages/CustomersPage";
import CustomerDetailPage from "./pages/CustomerDetailPage";
import SettingsPage from "./pages/SettingsPage";
import UsersPage from "./pages/UsersPage";
import NodesPage from "./pages/NodesPage";
import LogsPage from "./pages/LogsPage";
import FinancePage from "./pages/FinancePage";
import SystemHealthPage from "./pages/SystemHealthPage";
import ProfilePage from "./pages/ProfilePage";
import OnAuthCallbackPage from "./pages/OnAuthCallbackPage";
import NotFoundPage from "./pages/NotFoundPage";
import AccountDisabledPage from "./pages/AccountDisabledPage";
import { bindFeedbackMessage } from "./utils/feedback";
import { fetchInstallStatus, type InstallStatus } from "./api/install";

function AppShell() {
  const { message } = AntdApp.useApp();
  const navigate = useNavigate();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [installStatus, setInstallStatus] = useState<InstallStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    bindFeedbackMessage(message);
  }, [message]);

  const refreshUser = useCallback(async () => {
    try {
      const response = await api.get("/api/v1/auth/me");
      const data = response.data?.data;
      const nextUser = data?.username
        ? {
            username: data.username,
            nickname: data.nickname || "",
            role: data.role || "user",
            onauth_bound: Boolean(data.onauth_bound),
            onauth_username: data.onauth_username || "",
            onauth_bound_at: data.onauth_bound_at || "",
          }
        : null;
      setCurrentUser(nextUser);
      return nextUser;
    } catch (error: any) {
      setCurrentUser(null);
      if (error?.response?.status === 403 && String(error?.response?.data?.detail || error?.message || "").includes("禁用")) {
        navigate("/login/disabled", {
          replace: true,
          state: { message: error?.response?.data?.detail || "当前账号已被禁用，请联系管理员处理。" },
        });
      }
      return null;
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  const refreshInstallStatus = useCallback(async () => {
    try {
      const status = await fetchInstallStatus();
      setInstallStatus(status);
      return status;
    } catch {
      setInstallStatus(null);
      return null;
    }
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/v1/auth/logout");
    setCurrentUser(null);
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      const status = await refreshInstallStatus();
      if (status?.required) {
        setCurrentUser(null);
        setLoading(false);
        return;
      }
      await refreshUser();
    };
    void bootstrap();
  }, [refreshInstallStatus, refreshUser]);

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user: currentUser, loading, refreshUser, logout }}>
      <Routes>
        <Route
          path="/install"
          element={
            installStatus?.required ? (
              <InstallPage
                onFinished={async () => {
                  await refreshInstallStatus();
                  await refreshUser();
                  navigate("/");
                }}
              />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/login"
          element={
            currentUser ? (
              <Navigate to="/" replace />
            ) : (
              <LoginPage
                onSuccess={async () => {
                  const user = await refreshUser();
                  if (user) {
                    navigate("/");
                  }
                }}
              />
            )
          }
        />
        <Route path="/login/disabled" element={<AccountDisabledPage />} />
        <Route path="/onauth/callback" element={<OnAuthCallbackPage />} />
        <Route path="/" element={installStatus?.required ? <Navigate to="/install" replace /> : currentUser ? <ShellLayout /> : <Navigate to="/login" replace />}>
          <Route index element={<DashboardPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="customers/:id" element={<CustomerDetailPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="settings" element={currentUser?.role === "admin" ? <SettingsPage /> : <Navigate to="/" replace />} />
          <Route path="settings/users" element={currentUser?.role === "admin" ? <UsersPage /> : <Navigate to="/" replace />} />
          <Route path="settings/nodes" element={currentUser?.role === "admin" ? <NodesPage /> : <Navigate to="/" replace />} />
          <Route path="system/health" element={currentUser?.role === "admin" ? <SystemHealthPage /> : <Navigate to="/" replace />} />
          <Route path="finance" element={currentUser?.role === "admin" ? <FinancePage /> : <Navigate to="/" replace />} />
          <Route path="logs" element={currentUser?.role === "admin" ? <LogsPage /> : <Navigate to="/" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AuthContext.Provider>
  );
}

export default AppShell;
