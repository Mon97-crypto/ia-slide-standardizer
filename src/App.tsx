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

interface Auth {
  loading: boolean;
  authenticated: boolean;
  email?: string;
}

export interface PendingScan {
  company: string;
  domain: string;
}

export function App() {
  const [tab, setTab] = useState<TabKey>("dashboard");
  const [scanning, setScanning] = useState(false);
  const [pendingScan, setPendingScan] = useState<PendingScan | null>(null);
  const [auth, setAuth] = useState<Auth>({ loading: true, authenticated: false });

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => r.json())
      .then((d: { authenticated: boolean; email?: string }) => setAuth({ loading: false, authenticated: d.authenticated, email: d.email }))
      .catch(() => setAuth({ loading: false, authenticated: false }));
  }, []);

  // Fired from the dashboard's per-row "Scan" button: switch to Scan and run it.
  function scanFromDashboard(req: PendingScan) {
    setPendingScan(req);
    setTab("scan");
  }

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
      <Header tab={tab} onTab={setTab} status={scanning ? "scanning" : "ready"} email={auth.email} />
      {tab === "dashboard" && <DashboardView email={auth.email} onScan={scanFromDashboard} />}
      {tab === "scan" && (
        <ScanView
          onScanning={setScanning}
          pending={pendingScan}
          onConsumePending={() => setPendingScan(null)}
        />
      )}
      {tab === "ask" && <AskView />}
      {tab === "bulk" && <BulkView />}
    </div>
  );
}
