/**
 * ScanView — single-account scan: form → parallel progress → dashboard results.
 */
import { useCallback, useRef, useState } from "react";
import { ScanForm, type ScanRequest } from "../components/ScanForm";
import { type StepState } from "../components/ProgressCard";
import { SignalProgress } from "../components/SignalProgress";
import { ResultsView } from "../components/ResultsView";
import { DecisionMakers } from "../components/DecisionMakers";
import { runScan, type ScanResult, type StepKey } from "../lib/scan";
import { fetchAccount, type AccountInfo } from "../lib/account";

const INITIAL_STEPS: StepState[] = [
  { key: "edgar", label: "SEC filings", status: "pending" },
  { key: "techstack", label: "Tech stack", status: "pending" },
  { key: "news", label: "News, hiring and Reddit", status: "pending" },
];

export function ScanView({ onScanning }: { onScanning: (b: boolean) => void }) {
  const [scanning, setScanning] = useState(false);
  const [steps, setSteps] = useState<StepState[] | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [accountLoading, setAccountLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastReq = useRef<ScanRequest | null>(null);

  const doScan = useCallback(async (req: ScanRequest, refresh = false) => {
    lastReq.current = req;
    setError(null); setResult(null); setAccount(null); setScanning(true); onScanning(true);
    setSteps(INITIAL_STEPS.map((s) => ({ ...s, status: "pending" })));

    // Account information fetches in parallel with the signal scan.
    setAccountLoading(true);
    void fetchAccount(req.company, req.domain)
      .then(setAccount)
      .finally(() => setAccountLoading(false));

    try {
      const r = await runScan({
        company: req.company, domain: req.domain, refresh,
        onStep: (u) => setSteps((prev) => (prev ?? INITIAL_STEPS).map((s) =>
          s.key === (u.key as StepKey) ? { ...s, status: u.status, foundCount: u.foundCount, label: u.label } : s)),
      });
      setResult(r);
      if (r.cached) setSteps(null);
    } catch (e) {
      setError((e as Error).message || "The scan could not complete. Try again.");
    } finally {
      setScanning(false); onScanning(false);
    }
  }, [onScanning]);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Sales and BD · account intelligence</div>
        <h1 className="h1" style={{ margin: 0, maxWidth: 640 }}>Find accounts <span className="accent">worth</span> a call.</h1>
        <p className="secondary" style={{ marginTop: 12, maxWidth: 620 }}>
          Scan any retailer for buying signals mapped to what Impact Analytics sells. SEC filings, tech stack,
          news, hiring and Reddit — weighted for fit, grouped into key and supporting signals.
        </p>
      </div>

      <section className="card" style={{ padding: 20, marginBottom: 24 }}>
        <ScanForm onScan={(req) => doScan(req)} scanning={scanning} />
      </section>

      {error && (
        <div style={{ padding: "12px 16px", borderRadius: 13, border: "1px solid var(--ia-orange)", background: "var(--ia-white)", marginBottom: 24 }}>
          <strong style={{ color: "var(--ia-orange)" }}>Scan failed.</strong> <span>{error} </span>
          {lastReq.current && (
            <button onClick={() => doScan(lastReq.current!)} style={{ border: "none", background: "none", color: "var(--ia-blue)", fontWeight: 600, padding: 0 }}>Retry</button>
          )}
        </div>
      )}

      {scanning && steps && <div style={{ marginBottom: 24 }}><SignalProgress steps={steps} /></div>}

      {!scanning && result && (
        <div style={{ display: "grid", gap: 16 }}>
          <ResultsView
            result={result}
            account={account}
            accountLoading={accountLoading}
            onRefresh={() => lastReq.current && doScan(lastReq.current, true)}
          />
          <DecisionMakers company={result.company} domain={result.domain} />
        </div>
      )}

      {!scanning && !result && !error && (
        <div style={{ textAlign: "center", padding: "56px 0", color: "var(--ia-gray-3)" }}>
          <p className="serif" style={{ fontSize: 22, color: "var(--ia-black)", margin: 0 }}>No scans yet.</p>
          <p className="secondary" style={{ marginTop: 8 }}>Enter a website to start.</p>
        </div>
      )}
    </div>
  );
}
