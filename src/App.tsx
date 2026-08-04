/**
 * App — the shell: IA-branded header with tabs, routing to the four surfaces.
 */
import { useState } from "react";
import { Header, type TabKey } from "./components/Header";
import { ScanView } from "./views/ScanView";
import { AskView } from "./views/AskView";
import { BulkView } from "./views/BulkView";

export function App() {
  const [tab, setTab] = useState<TabKey>("scan");
  const [scanning, setScanning] = useState(false);

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 24px 96px" }}>
      <Header tab={tab} onTab={setTab} status={scanning ? "scanning" : "ready"} />
      {tab === "scan" && <ScanView onScanning={setScanning} />}
      {tab === "ask" && <AskView />}
      {tab === "bulk" && <BulkView />}
    </div>
  );
}
