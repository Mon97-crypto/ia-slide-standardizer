/**
 * App — the shell: auth gate, IA-branded header with tabs, routing to the surfaces.
 */
import { useEffect, useState } from "react";
import { Header, type TabKey } from "./components/Header";
import { LoginScreen } from "./components/LoginScreen";
import { DashboardView } from "./views/DashboardView";
import { ScanView } from "./views/ScanView";
import { AskView } from "./views/AskView";
import { BulkView } from "./views/BulkView";
import { AdminView } from "./views/AdminView";

interface Auth {
  loading: boolean;
  authenticated: boolean;
  email?: string;
  isAdmin?: boolean;
}

// Browser-tab title per surface, so the tab reads e.g. "Scan · Account Intelligence".
const TAB_TITLE: Record<TabKey, string> = {
  scan: "Scan",
  dashboard: "My Dashboard",
  bulk: "Bulk upload",
  ask: "Ask IAsense",
  admin: "Admin",
};

export function App() {
  const [tab, setTab] = useState<TabKey>("scan");
  const [scanning, setScanning] = useState(false);
  const [auth, setAuth] = useState<Auth>({ loading: true, authenticated: false });

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => r.json())
      .then((d: { authenticated: boolean; email?: string; isAdmin?: boolean }) => setAuth({ loading: false, authenticated: d.authenticated, email: d.email, isAdmin: d.isAdmin }))
      .catch(() => setAuth({ loading: false, authenticated: false }));
  }, []);

  // Keep the browser tab title in sync with the active tab.
  useEffect(() => {
    document.title = auth.authenticated
      ? `${TAB_TITLE[tab]} · Account Intelligence`
      : "IA Sense · Account Intelligence";
  }, [tab, auth.authenticated]);

  if (auth.loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span className="secondary">Loading…</span>
      </div>
    );
  }

  if (!auth.authenticated) return <LoginScreen />;

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 24px 96px" }}>
      <Header tab={tab} onTab={setTab} status={scanning ? "scanning" : "ready"} email={auth.email} isAdmin={auth.isAdmin} />
      {tab === "dashboard" && <DashboardView email={auth.email} onBell={auth.isAdmin ? () => setTab("admin") : undefined} />}
      {tab === "scan" && <ScanView onScanning={setScanning} email={auth.email} />}
      {tab === "ask" && <AskView />}
      {tab === "bulk" && <BulkView />}
      {tab === "admin" && auth.isAdmin && <AdminView />}
    </div>
  );
}
