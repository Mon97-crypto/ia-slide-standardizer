/**
 * App — the shell. Header with the status pill, the scan form, an orchestrated
 * progress card, and the results view. Keeps the interface quiet until you act
 * (Linear), communicates state with a dot and a word (Vercel), and keeps detail
 * one click down (Notion). Cmd/Ctrl+K opens a small command palette.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ScanForm, type ScanRequest } from "./components/ScanForm";
import { ProgressCard, type StepState } from "./components/ProgressCard";
import { ResultsView } from "./components/ResultsView";
import { StatusPill } from "./components/StatusPill";
import { runScan, type ScanResult, type StepKey } from "./lib/scan";

const INITIAL_STEPS: StepState[] = [
  { key: "edgar", label: "SEC filings", status: "pending" },
  { key: "techstack", label: "Tech stack", status: "pending" },
  { key: "news", label: "News and hiring", status: "pending" },
];

export function App() {
  const [scanning, setScanning] = useState(false);
  const [steps, setSteps] = useState<StepState[] | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const lastReq = useRef<ScanRequest | null>(null);

  const doScan = useCallback(async (req: ScanRequest, refresh = false) => {
    lastReq.current = req;
    setError(null);
    setResult(null);
    setScanning(true);
    setSteps(INITIAL_STEPS.map((s) => ({ ...s, status: "pending" })));
    try {
      const r = await runScan({
        company: req.company,
        domain: req.domain,
        refresh,
        onStep: (u) =>
          setSteps((prev) =>
            (prev ?? INITIAL_STEPS).map((s) =>
              s.key === (u.key as StepKey)
                ? { ...s, status: u.status, foundCount: u.foundCount, label: u.label }
                : s,
            ),
          ),
      });
      setResult(r);
      if (r.cached) setSteps(null);
    } catch (e) {
      setError((e as Error).message || "The scan could not complete. Try again.");
    } finally {
      setScanning(false);
    }
  }, []);

  // Cmd/Ctrl+K command palette.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);

  const status = scanning ? "scanning" : "ready";

  return (
    <div style={{ maxWidth: 1120, margin: "0 auto", padding: "32px 24px 96px" }}>
      <header style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 32 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Impact Analytics · Sales and BD</div>
          <h1 className="h1" style={{ margin: 0, maxWidth: 640 }}>
            Find accounts <span className="accent">worth</span> a call.
          </h1>
          <p className="secondary" style={{ marginTop: 12, maxWidth: 560 }}>
            Scan any retailer for buying signals mapped to what Impact Analytics sells. SEC
            filings, tech stack, and news, weighted for fit.
          </p>
        </div>
        <StatusPill status={status} />
      </header>

      <section
        className="card"
        style={{
          background: "var(--ia-white)",
          border: "1px solid var(--ia-gray-1)",
          borderRadius: 20,
          boxShadow: "0 2px 10px rgba(20,20,30,.05)",
          padding: 20,
          marginBottom: 24,
        }}
      >
        <ScanForm onScan={(req) => doScan(req)} scanning={scanning} />
      </section>

      {error && (
        <div style={{ padding: "12px 16px", borderRadius: 13, border: "1px solid var(--ia-orange)", background: "var(--ia-white)", marginBottom: 24 }}>
          <strong style={{ color: "var(--ia-orange)" }}>Scan failed.</strong>{" "}
          <span>{error} </span>
          {lastReq.current && (
            <button onClick={() => doScan(lastReq.current!)} style={{ border: "none", background: "none", color: "var(--ia-blue)", fontWeight: 600, padding: 0 }}>
              Retry
            </button>
          )}
        </div>
      )}

      {scanning && steps && (
        <div style={{ marginBottom: 24 }}>
          <ProgressCard steps={steps} />
          <SkeletonRows />
        </div>
      )}

      {!scanning && result && (
        <ResultsView result={result} onRefresh={() => lastReq.current && doScan(lastReq.current, true)} />
      )}

      {!scanning && !result && !error && <EmptyState />}

      {paletteOpen && (
        <CommandPalette
          onClose={() => setPaletteOpen(false)}
          canRerun={!!lastReq.current}
          onRerun={() => {
            setPaletteOpen(false);
            if (lastReq.current) doScan(lastReq.current, true);
          }}
          onCopy={() => {
            setPaletteOpen(false);
            if (result) {
              void navigator.clipboard?.writeText(
                `${result.company} (${result.domain}) — ${result.intent}, score ${result.total}`,
              );
            }
          }}
          hasResult={!!result}
        />
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: "64px 0", color: "var(--ia-gray-3)" }}>
      <p className="serif" style={{ fontSize: 22, color: "var(--ia-black)", margin: 0 }}>
        No scans yet.
      </p>
      <p className="secondary" style={{ marginTop: 8 }}>
        Enter a website to start. Press Cmd or Ctrl + K for shortcuts.
      </p>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div style={{ marginTop: 16, background: "var(--ia-white)", border: "1px solid var(--ia-gray-1)", borderRadius: 20, overflow: "hidden" }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{ height: 44, display: "flex", alignItems: "center", gap: 12, padding: "0 14px", borderTop: i === 0 ? "none" : "1px solid var(--ia-gray-1)" }}>
          <span style={{ width: 16, height: 8, borderRadius: 4, background: "var(--ia-offwhite)" }} />
          <span style={{ width: 180, height: 10, borderRadius: 4, background: "var(--ia-offwhite)" }} />
          <span style={{ flex: 1, height: 10, borderRadius: 4, background: "var(--ia-offwhite)", opacity: 0.6 }} />
        </div>
      ))}
    </div>
  );
}

function CommandPalette({
  onClose,
  onRerun,
  onCopy,
  canRerun,
  hasResult,
}: {
  onClose: () => void;
  onRerun: () => void;
  onCopy: () => void;
  canRerun: boolean;
  hasResult: boolean;
}) {
  const items = useMemo(
    () =>
      [
        { label: "Start a new scan", action: () => { onClose(); document.querySelector<HTMLInputElement>("input")?.focus(); } },
        canRerun ? { label: "Rerun the last scan", action: onRerun } : null,
        hasResult ? { label: "Copy the result", action: onCopy } : null,
      ].filter(Boolean) as { label: string; action: () => void }[],
    [canRerun, hasResult, onRerun, onCopy, onClose],
  );

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(28,27,27,.25)", display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: "18vh", zIndex: 50 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(520px, 92vw)", background: "var(--ia-white)", border: "1px solid var(--ia-gray-1)", borderRadius: 20, boxShadow: "0 12px 40px rgba(20,20,30,.18)", overflow: "hidden" }}
      >
        <div className="eyebrow" style={{ padding: "14px 16px 8px" }}>Command palette</div>
        {items.map((it) => (
          <button
            key={it.label}
            onClick={it.action}
            style={{ display: "block", width: "100%", textAlign: "left", padding: "12px 16px", border: "none", background: "transparent", fontSize: 15, borderTop: "1px solid var(--ia-gray-1)" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ia-blue-soft)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            {it.label}
          </button>
        ))}
      </div>
    </div>
  );
}
