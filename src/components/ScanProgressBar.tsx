/**
 * ScanProgressBar — a compact, pulsating, gradually-increasing progress bar shown
 * inline while a dashboard row is being scanned. The fill eases toward ~92% (never
 * completing until the real scan lands and the bar unmounts), a shimmer sweeps
 * across it, and the caption cycles through the signals being scanned.
 */
import { useEffect, useState } from "react";
import { CATALOG, KEY_SIGNALS, SUPPORTING_SIGNALS, type CatalogId } from "../lib/scan-contract";

const ALL: CatalogId[] = [...KEY_SIGNALS, ...SUPPORTING_SIGNALS];
const CEILING = 0.92;

export function ScanProgressBar({ company }: { company: string }) {
  const [pct, setPct] = useState(0.04);
  const [step, setStep] = useState(0);

  // Ease the fill toward the ceiling — fast at first, slowing as it approaches.
  useEffect(() => {
    const t = setInterval(() => setPct((p) => p + (CEILING - p) * 0.08), 350);
    return () => clearInterval(t);
  }, []);

  // Cycle the "scanning <signal>…" caption so it feels alive and gradual.
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % ALL.length), 1600);
    return () => clearInterval(t);
  }, []);

  const current = CATALOG[ALL[step]];

  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 12 }}>
        <span className="card-title" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          Scanning {company}…
        </span>
        <span className="tnum secondary" style={{ flexShrink: 0 }}>{Math.round(pct * 100)}%</span>
      </div>

      {/* Pulsing gradient fill with a sweeping shimmer. */}
      <div style={{ position: "relative", height: 8, borderRadius: 999, background: "var(--ia-offwhite)", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute", inset: 0, width: `${pct * 100}%`, borderRadius: 999, overflow: "hidden",
            background: "linear-gradient(90deg, var(--ia-blue), var(--ia-blue-dark))",
            transition: "width 600ms cubic-bezier(.22,.61,.36,1)",
            animation: "pulse 1.4s ease-in-out infinite",
          }}
        >
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)", animation: "bar-shimmer 1.4s linear infinite" }} />
        </div>
      </div>

      {/* Current-signal callout. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, minHeight: 20 }}>
        <span aria-hidden style={{ width: 8, height: 8, borderRadius: 999, background: "var(--ia-blue)", animation: "pulse 1s ease-in-out infinite", flexShrink: 0 }} />
        <span className="secondary">Scanning <strong style={{ color: "var(--ia-black)" }}>{current.label}</strong>…</span>
      </div>
    </div>
  );
}
