/**
 * SignalProgress — live scan progress. The backend scans in batches, so instead of
 * jumping when a batch finishes, we reveal the 19 signals gradually one at a time
 * on a timer: a pulsing progress bar advances signal by signal, the signal being
 * scanned is called out and pulses, revealed ones check off, the rest queue. When
 * the real scan actually finishes, it snaps to 100%.
 */
import { useEffect, useState } from "react";
import type { StepKey } from "../lib/scan";
import { FUNCTION_SIGNALS } from "../lib/scan";
import { CATALOG, KEY_SIGNALS, SUPPORTING_SIGNALS, type CatalogId } from "../lib/scan-contract";
import type { StepState } from "./ProgressCard";

const ALL: CatalogId[] = [...KEY_SIGNALS, ...SUPPORTING_SIGNALS];
const INDEX_OF = new Map(ALL.map((id, i) => [id, i]));
const REVEAL_MS = 3000; // ~one signal every 3s; holds near the end until the scan lands

type SigStatus = "done" | "scanning" | "queued";

function allStepsResolved(steps: StepState[]): boolean {
  const covered = new Set<StepKey>();
  (Object.keys(FUNCTION_SIGNALS) as StepKey[]).forEach((k) => covered.add(k));
  for (const k of covered) {
    const st = steps.find((s) => s.key === k)?.status ?? "pending";
    if (st === "pending") return false;
  }
  return true;
}

export function SignalProgress({ steps }: { steps: StepState[] }) {
  const done = allStepsResolved(steps);

  // Time-based gradual reveal (1..ALL.length-1); snaps to full when the scan lands.
  const [revealed, setRevealed] = useState(1);
  useEffect(() => {
    if (done) {
      setRevealed(ALL.length);
      return;
    }
    const t = setInterval(() => setRevealed((r) => Math.min(r + 1, ALL.length - 1)), REVEAL_MS);
    return () => clearInterval(t);
  }, [done]);

  const progress = done ? ALL.length : revealed;
  const currentIndex = done ? -1 : Math.min(progress, ALL.length - 1);
  const current = currentIndex >= 0 ? ALL[currentIndex] : null;
  const pct = (progress / ALL.length) * 100;

  const statusOf = (id: CatalogId): SigStatus => {
    if (done) return "done";
    const i = INDEX_OF.get(id) ?? 0;
    if (i < progress) return "done";
    if (i === currentIndex) return "scanning";
    return "queued";
  };

  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="card-title">Scanning {ALL.length} signals</span>
        <span className="tnum secondary">{progress}/{ALL.length}</span>
      </div>

      {/* Pulsing progress bar with a sweeping shimmer. */}
      <div style={{ position: "relative", height: 8, borderRadius: 999, background: "var(--ia-offwhite)", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, width: `${pct}%`, background: "var(--ia-blue)", borderRadius: 999, overflow: "hidden", transition: "width 500ms cubic-bezier(.22,.61,.36,1)" }}>
          {!done && <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.55), transparent)", animation: "bar-shimmer 1.4s linear infinite" }} />}
        </div>
      </div>

      {/* Current signal callout. */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, minHeight: 20 }}>
        {current ? (
          <>
            <span aria-hidden style={{ width: 8, height: 8, borderRadius: 999, background: "var(--ia-blue)", animation: "pulse 1s ease-in-out infinite", flexShrink: 0 }} />
            <span className="secondary">Scanning <strong style={{ color: "var(--ia-black)" }}>{CATALOG[current].label}</strong>…</span>
          </>
        ) : (
          <span className="secondary">Finishing up…</span>
        )}
      </div>

      <div style={{ height: 14 }} />
      <Group title="Key signals" ids={KEY_SIGNALS} statusOf={statusOf} current={current} />
      <div style={{ height: 14 }} />
      <Group title="Supporting signals" ids={SUPPORTING_SIGNALS} statusOf={statusOf} current={current} />
    </div>
  );
}

function Group({ title, ids, statusOf, current }: { title: string; ids: CatalogId[]; statusOf: (id: CatalogId) => SigStatus; current: CatalogId | null }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 8 }}>{title}</div>
      <div style={{ display: "grid", gap: 2 }}>
        {ids.map((id) => (
          <Row key={id} id={id} status={statusOf(id)} active={id === current} />
        ))}
      </div>
    </div>
  );
}

function Row({ id, status, active }: { id: CatalogId; status: SigStatus; active: boolean }) {
  const entry = CATALOG[id];
  const scanning = status === "scanning";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 30, padding: "0 8px", borderRadius: 8, background: active ? "var(--ia-blue-soft)" : "transparent", transition: "background 220ms ease" }}>
      <span aria-hidden style={{
        width: 16, height: 16, borderRadius: 999, flexShrink: 0, fontSize: 11,
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        color: "var(--ia-white)",
        background: status === "done" ? "var(--ia-blue)" : "var(--ia-gray-2)",
        animation: scanning ? "pulse 1s ease-in-out infinite" : "none",
      }}>
        {status === "done" ? "✓" : ""}
      </span>
      <span aria-hidden style={{ flexShrink: 0, width: 16, textAlign: "center", color: "var(--ia-gray-3)" }}>{entry.glyph}</span>
      <span style={{ flex: 1, fontSize: 14, color: status === "queued" ? "var(--ia-gray-3)" : "var(--ia-black)" }}>{entry.label}</span>
      <span className="secondary" style={{ fontSize: 12 }}>
        {status === "done" ? "scanned" : scanning ? "scanning…" : "queued"}
      </span>
    </div>
  );
}
